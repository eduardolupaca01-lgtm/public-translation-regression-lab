package main
import (
 "bytes"
 "encoding/json"
 "errors"
 "os"
 "path/filepath"
 "strings"
 "testing"
)
func r44DirectFixture(t *testing.T)(string,string,[]byte,[]byte){
 t.Helper()
 root:=mvnwbinSingleFixture(t,false)
 content:=filepath.Join(root,"www")
 original:=[]byte(mvJSONFixtureMap)
 system:=[]byte(`{"startMapId":1,"terms":{"commands":["Item","Skill","Options","Save"]}}`)
 mvnwbinWrite(t,filepath.Join(content,"data","Map001.json"),string(original))
 mvnwbinWrite(t,filepath.Join(content,"data","System.json"),string(system))
 return root,filepath.Join(root,"Game.exe"),original,system
}
func r44DirectCandidate(engine,root,journal string)error{
 var req mvJSONRequest
 if _,e:=mvJSONDirectRead(filepath.Join(journal,"request.json"),&req);e!=nil{return e}
 raw,e:=mvJSONRead(filepath.Join(root,req.Content,"data",req.Map),mvJSONDirectLimit);if e!=nil{return e}
 after:=[]byte(strings.ReplaceAll(strings.ReplaceAll(strings.ReplaceAll(string(raw),"Please open the wooden gate.","Abre la puerta de madera."),"橋を渡ってください。","Cruza el puente."),"Yes","Sí"))
 // The source text also appears in a script. Only translate the first
 // display occurrence; restore the synthetic script field exactly.
 after=[]byte(strings.Replace(string(after),`"code":355,"indent":1,"parameters":["Abre la puerta de madera."]`,`"code":355,"indent":1,"parameters":["Please open the wooden gate."]`,1))
 changes,e:=mvJSONVerifyMapDetailed(raw,after);if e!=nil{return e}
 rep:=mvJSONReport{Schema:mvJSONSchema,Map:req.Map,Before:hash(raw),After:hash(after),Lines:changes.Lines,
  ChoiceGroups:changes.ChoiceGroups,ChoiceLabels:changes.ChoiceLabels,Wrapped:changes.Wrapped,Breaks:changes.Breaks,Units:2,New:2}
 if e=createNew(filepath.Join(journal,"candidate.json"),after);e!=nil{return e}
 b,_:=json.Marshal(rep)
 return createNew(filepath.Join(journal,"report.json"),b)
}
func r44DirectUnchanged(t *testing.T,root string,original,system []byte){
 t.Helper()
 for name,want:=range map[string][]byte{"Map001.json":original,"System.json":system}{
  raw,e:=os.ReadFile(filepath.Join(root,"www","data",name));if e!=nil||!bytes.Equal(raw,want){t.Fatal("original changed",name,e)}
 }
}
func TestR44JSONDirectInstallRecoverNoCopy(t *testing.T){
 root,exe,before,system:=r44DirectFixture(t)
 pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
 boot,e:=mvJSONBootFingerprint(exe,root,filepath.Join(root,"www"));if e!=nil{t.Fatal(e)}
 entries,e:=os.ReadDir(filepath.Dir(root));if e!=nil{t.Fatal(e)}
 rep,e:=mvJSONInstallDirectWith(exe,pkg,r44DirectCandidate,vxaceAtomicReplaceFrom)
 if e!=nil||rep.Lines!=2||rep.ChoiceLabels!=1||rep.Menu!=4{t.Fatalf("direct result %+v %v",rep,e)}
 after,e:=os.ReadDir(filepath.Dir(root));if e!=nil||len(after)!=len(entries){t.Fatal("direct mode created a sibling game")}
 if !mvJSONDirectNeedsRecovery(exe){t.Fatal("missing active journal")}
 if _,e=mvJSONInstallDirectWith(exe,pkg,r44DirectCandidate,vxaceAtomicReplaceFrom);e==nil||e.Error()!="IA_MV_JSON_DIRECTO_RECUPERAR_PRIMERO"{t.Fatal("repeat install",e)}
 if _,_,e=mvJSONCopyPilot(exe,pkg);e==nil||e.Error()!="IA_MV_JSON_DIRECTO_RECUPERAR_PRIMERO"{t.Fatal("copied active direct installation",e)}
 if h,e:=mvJSONBootFingerprint(exe,root,filepath.Join(root,"www"));e!=nil||h!=boot{t.Fatal("boot changed",e)}
 if e=RecoverGame(exe);e!=nil{t.Fatal(e)}
 r44DirectUnchanged(t,root,before,system)
 if mvJSONDirectNeedsRecovery(exe){t.Fatal("active journal not archived")}
 if e=RecoverGame(exe);e!=nil{t.Fatal("idempotent recovery",e)}
 skip,unlock,e:=mvJSONDirectCopyGuard(root);if e!=nil||!skip{t.Fatal("restored source not eligible for copy",e)}
 plan,_,e:=mvJSONClonePlan(root,exe,skip);unlock();if e!=nil{t.Fatal(e)}
 for _,entry:=range plan{if strings.HasPrefix(strings.ToLower(entry.rel),strings.ToLower(brandFolder)){t.Fatal("copied existing sidecar")}}
 if _,e=mvJSONInstallDirectWith(exe,pkg,r44DirectCandidate,vxaceAtomicReplaceFrom);e!=nil{t.Fatal("repeat after restoration",e)}
 if e=RecoverGame(exe);e!=nil{t.Fatal(e)}
 r44DirectUnchanged(t,root,before,system)
}
func TestR44JSONDirectPublicationRollbackAndPartialRecovery(t *testing.T){
 for _,restoreBlocked:=range []bool{false,true}{t.Run(map[bool]string{false:"rollback",true:"interrupted"}[restoreBlocked],func(t *testing.T){
  root,exe,before,system:=r44DirectFixture(t)
  pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
  target:=filepath.Join(root,"www","data","System.json")
  count:=0
  replace:=func(src,dst,srcSHA,dstSHA string)error{
   count++
   if dst==target||restoreBlocked&&count>1{return errors.New("synthetic write failure")}
   return vxaceAtomicReplaceFrom(src,dst,srcSHA,dstSHA)
  }
  _,e=mvJSONInstallDirectWith(exe,pkg,r44DirectCandidate,replace)
  if e==nil{t.Fatal("unexpected success")}
  if restoreBlocked{
   if e.Error()!="IA_MV_JSON_DIRECTO_RECUPERACION_PENDIENTE"||!mvJSONDirectNeedsRecovery(exe){t.Fatal("journal lost after partial write",e)}
   if e=RecoverGame(exe);e!=nil{t.Fatal(e)}
  }else if !strings.HasPrefix(e.Error(),"IA_MV_JSON_DIRECTO_REVERTIDO")||mvJSONDirectNeedsRecovery(exe){t.Fatal("rollback not verified",e)}
  r44DirectUnchanged(t,root,before,system)
 })}
}
func TestR44JSONDirectRejectsForeignEditBeforeRestore(t *testing.T){
 root,exe,before,system:=r44DirectFixture(t)
 pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
 if _,e=mvJSONInstallDirectWith(exe,pkg,r44DirectCandidate,vxaceAtomicReplaceFrom);e!=nil{t.Fatal(e)}
 m:=filepath.Join(root,"www","data","Map001.json")
 s:=filepath.Join(root,"www","data","System.json")
 translated,e:=os.ReadFile(m);if e!=nil{t.Fatal(e)}
 other:=[]byte(`{"startMapId":1,"terms":{"commands":["Externally changed"]}}`)
 if e=os.WriteFile(s,other,0600);e!=nil{t.Fatal(e)}
 if e=RecoverGame(exe);e==nil||e.Error()!="IA_MV_JSON_DIRECTO_DATOS_CAMBIADOS"{t.Fatal("foreign edit overwritten",e)}
 for f,want:=range map[string][]byte{m:translated,s:other}{
  raw,e:=os.ReadFile(f);if e!=nil||!bytes.Equal(raw,want){t.Fatal("recovery mutated either resource")}
 }
 if e=os.WriteFile(s,system,0600);e!=nil{t.Fatal(e)}
 if e=RecoverGame(exe);e!=nil{t.Fatal(e)}
 r44DirectUnchanged(t,root,before,system)
}
func TestR44JSONDirectWorkerFailureNeverPublishes(t *testing.T){
 root,exe,before,system:=r44DirectFixture(t)
 pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
 if _,e=mvJSONInstallDirectWith(exe,pkg,func(_,_,_ string)error{return errors.New("synthetic worker failure")},vxaceAtomicReplaceFrom);e==nil{t.Fatal("worker failure ignored")}
 r44DirectUnchanged(t,root,before,system)
 if e=RecoverGame(exe);e!=nil{t.Fatal("prepublication recovery",e)}
 r44DirectUnchanged(t,root,before,system)
}
func TestR44JSONDirectLockReleased(t *testing.T){
 base:=t.TempDir()
 unlock,e:=mvJSONDirectLock(base);if e!=nil{t.Fatal(e)}
 if again,e:=mvJSONDirectLock(base);e==nil{again();unlock();t.Fatal("second operation acquired lock")}
 unlock()
 again,e:=mvJSONDirectLock(base);if e!=nil{t.Fatal("stale filename blocked recovery",e)};again()
}
