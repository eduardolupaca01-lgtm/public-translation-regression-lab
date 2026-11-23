package main

import(
 "errors"
 "os"
 "path/filepath"
 "strings"
 "testing"
 "time"
)

func iaTestPublicationHooks(t *testing.T){
 t.Helper()
 originalRename:=iaRenameStage
 originalMkdir:=iaMkdirDestination
 originalSleep:=iaRetrySleep
 iaRetrySleep=func(time.Duration){}
 t.Cleanup(func(){
  iaRenameStage=originalRename
  iaMkdirDestination=originalMkdir
  iaRetrySleep=originalSleep
 })
}
func iaTestPrepared(t *testing.T)(string,*packageReader){
 t.Helper()
 game:=createFixture(t)
 f,e:=readPackage(fakePackage(t))
 if e!=nil{t.Fatal(e)}
 t.Cleanup(f.Close)
 return game,f
}
func TestPublicationRenameAccessDeniedFallsBackToOwnedCopy(t *testing.T){
 iaTestPublicationHooks(t)
 game,pkg:=iaTestPrepared(t)
 attempts:=0
 iaRenameStage=func(from,to string)error{
  attempts++
  return &os.LinkError{Op:"rename",Old:from,New:to,Err:os.ErrPermission}
 }
 original,_:=os.ReadFile(filepath.Join(game,"www","js","plugins.js"))
 if err:=Install(filepath.Join(game,"Game.exe"),pkg);err!=nil{t.Fatalf("fallback install should succeed: %s",err)}
 if attempts!=4{t.Fatalf("expected bounded retries, got %d",attempts)}
 folder:=filepath.Join(game,brandFolder)
 if err:=iaCheckEngine(folder,pkg);err!=nil{t.Fatalf("installed models do not match: %s",err)}
 prior,_:=os.ReadFile(filepath.Join(folder,"install","original-plugins.js"))
 if string(prior)!=string(original){t.Fatal("original game plugin registry was not preserved")}
 for _,name:=range []string{"www/data/System.json","Game.exe"}{
  if !ordinary(filepath.Join(game,filepath.FromSlash(name))){t.Fatalf("game file modified/missing: %s",name)}
 }
 if err:=Install(filepath.Join(game,"Game.exe"),pkg);err!=nil{
  t.Fatalf("reinstall must remain idempotent: %s",err)
 }
}
func TestPublicationAccessDeniedPreservesVerifiedStageForRetry(t *testing.T){
 iaTestPublicationHooks(t)
 game,pkg:=iaTestPrepared(t)
 iaRenameStage=func(from,to string)error{
  return &os.LinkError{Op:"rename",Old:from,New:to,Err:os.ErrPermission}
 }
 iaMkdirDestination=func(string,os.FileMode)error{return os.ErrPermission}
 original,_:=os.ReadFile(filepath.Join(game,"www","js","plugins.js"))
 err:=Install(filepath.Join(game,"Game.exe"),pkg)
 if err==nil||!strings.Contains(err.Error(),"IA_DESTINO_CREACION_DENEGADA"){
  t.Fatalf("expected sanitized destination-denied reason, got %v",err)
 }
 after,_:=os.ReadFile(filepath.Join(game,"www","js","plugins.js"))
 if string(after)!=string(original){t.Fatal("failed publication changed game plugin registry")}
 staged,e:=iaFindVerifiedStage(game,pkg)
 if e!=nil||staged==""{t.Fatalf("verified staging models must survive: %v",e)}
 // A future normal retry (after Windows releases the lock) reuses the
 // existing verified stage; it never downloads/extracts weights again.
 iaRenameStage=os.Rename
 iaMkdirDestination=os.Mkdir
 if err:=Install(filepath.Join(game,"Game.exe"),pkg);err!=nil{t.Fatalf("verified retry failed: %s",err)}
 if !ordinary(filepath.Join(game,brandFolder,"owner-v1.json")){t.Fatal("owner marker not published")}
 if _,err:=os.Stat(staged);!errors.Is(err,os.ErrNotExist){t.Fatal("renamed source stage remains unexpectedly")}
}
func TestPublicationDetectsForeignDestinationCreatedDuringRename(t *testing.T){
 iaTestPublicationHooks(t)
 game,pkg:=iaTestPrepared(t)
 dest:=filepath.Join(game,brandFolder)
 original,_:=os.ReadFile(filepath.Join(game,"www","js","plugins.js"))
 iaRenameStage=func(from,to string)error{
  if err:=os.Mkdir(dest,0700);err!=nil&&!errors.Is(err,os.ErrExist){return err}
  _=os.WriteFile(filepath.Join(dest,"foreign.txt"),[]byte("USER MUST KEEP"),0600)
  return &os.LinkError{Op:"rename",Old:from,New:to,Err:os.ErrPermission}
 }
 err:=Install(filepath.Join(game,"Game.exe"),pkg)
 if err==nil||!strings.Contains(err.Error(),"IA_DESTINO_EXISTENTE_NO_SOBRESCRITO"){
  t.Fatalf("foreign destination was not protected: %v",err)
 }
 foreign,_:=os.ReadFile(filepath.Join(dest,"foreign.txt"))
 if string(foreign)!="USER MUST KEEP"{t.Fatal("foreign file was overwritten")}
 if _,err:=os.Stat(filepath.Join(dest,"owner-v1.json"));!errors.Is(err,os.ErrNotExist){
  t.Fatal("owner marker improperly written into foreign destination")
 }
 after,_:=os.ReadFile(filepath.Join(game,"www","js","plugins.js"))
 if string(after)!=string(original){t.Fatal("failed publication changed game registry")}
}
func TestPublicationResumesIncompleteOwnedFallbackWithoutOverwrite(t *testing.T){
 iaTestPublicationHooks(t)
 game,pkg:=iaTestPrepared(t)
 iaRenameStage=func(from,to string)error{
  return &os.LinkError{Op:"rename",Old:from,New:to,Err:os.ErrPermission}
 }
 dest:=filepath.Join(game,brandFolder)
 stage,err:=iaPrepareStage(game,pkg)
 if err!=nil{t.Fatal(err)}
 if err=os.Mkdir(dest,0700);err!=nil{t.Fatal(err)}
 owner,_:=os.ReadFile(filepath.Join(stage,"owner-v1.json"))
 if err=createNew(filepath.Join(dest,"owner-v1.json"),owner);err!=nil{t.Fatal(err)}
 if err=iaMakeSafeDirs(dest,filepath.Join(".local","Rpg","engine"));err!=nil{t.Fatal(err)}
 // Same-version marker permits filling ONLY missing files.
 if err=Install(filepath.Join(game,"Game.exe"),pkg);err!=nil{t.Fatalf("safe resume failed: %s",err)}
 if err=iaCheckEngine(dest,pkg);err!=nil{t.Fatalf("resume failed verification: %s",err)}
}
