package main

import (
 "context"
 "fmt"
 "os"
 "path/filepath"
 "syscall"
 "testing"
)

func r44RuntimeFixture()map[string][]byte{
 files:=map[string][]byte{}
 for _,name:=range mvJSONRequiredRuntime{files[name]=[]byte("synthetic runtime file, never executed")}
 return files
}

func TestR44JSONRuntimePackageIsolatedFromLegacy(t *testing.T){
 files:=r44RuntimeFixture()
 files["json-runtime/_internal/ctranslate2/py.typed"]=[]byte{}
 files["json-runtime/_internal/sample.dist-info/REQUESTED"]=[]byte{}
 files["json-runtime/_internal/sample.dist-info/license [extra].txt"]=[]byte("test license")
 for i:=0;i<80;i++{files[fmt.Sprintf("json-runtime/_internal/test/module%03d.pyd",i)]=[]byte("test-only")}
 pkg,e:=readPackage(fakePackageWith(t,[]byte("test plugin"),[]byte("test worker"),files))
 if e!=nil{t.Fatal(e)};defer pkg.Close()
 if len(pkg.files)>66||pkg.files[mvJSONRuntimeEXE]!=nil||len(pkg.jsonFiles)!=len(files){t.Fatal("legacy file set was changed")}
 offline,e:=mvJSONPackageForOffline(pkg);if e!=nil{t.Fatal(e)}
 if offline.files[mvJSONRuntimeEXE]==nil||len(offline.files)!=len(pkg.files)+len(files){t.Fatal("offline view incomplete")}
 if pkg.files[mvJSONRuntimeEXE]!=nil{t.Fatal("modified legacy manifest")}
 engine:=t.TempDir()
 for name,raw:=range files{
  path:=filepath.Join(engine,filepath.FromSlash(name))
  if e=os.MkdirAll(filepath.Dir(path),0700);e!=nil{t.Fatal(e)}
  if e=os.WriteFile(path,raw,0600);e!=nil{t.Fatal(e)}
 }
 if e=mvJSONVerifyRuntime(engine,offline);e!=nil{t.Fatal(e)}
 marker:=filepath.Join(engine,"json-runtime","_internal","ctranslate2","py.typed")
 if h,e:=digestFile(marker);e!=nil||h!=hash(nil){t.Fatal("empty marker hash",e)}
 if e=os.WriteFile(marker,[]byte("changed"),0600);e!=nil{t.Fatal(e)}
 if e=mvJSONVerifyRuntime(engine,offline);e==nil{t.Fatal("modified marker accepted")}
 if e=os.WriteFile(marker,nil,0600);e!=nil{t.Fatal(e)}
 foreign:=filepath.Join(engine,"json-runtime","_internal","foreign.dll")
 if e=os.WriteFile(foreign,[]byte("unexpected"),0600);e!=nil{t.Fatal(e)}
 if e=mvJSONVerifyRuntime(engine,offline);e==nil{t.Fatal("foreign runtime file accepted")}
 if e=os.Remove(foreign);e!=nil{t.Fatal(e)}
 if e=os.WriteFile(filepath.Join(engine,filepath.FromSlash(mvJSONRuntimeEXE)),[]byte("changed"),0600);e!=nil{t.Fatal(e)}
 if e=mvJSONVerifyRuntime(engine,offline);e==nil{t.Fatal("modified runtime accepted")}
}
func TestR44JSONRuntimeRejectsIncompleteOrUnsafePayload(t *testing.T){
 for _,name:=range []string{"json-runtime/extra.exe","json-runtime/_internal/CON.dll","json-runtime/_internal/a.dll.","JSON-RUNTIME/_internal/file.dll","json-runtime/_internal/../escape.dll"}{
  if mvJSONRuntimeName(name){t.Fatal("accepted unsafe bundle entry",name)}
 }
 files:=r44RuntimeFixture();delete(files,"json-runtime/_internal/python311.dll")
 if p,e:=readPackage(fakePackageWith(t,[]byte("test plugin"),[]byte("test worker"),files));e==nil{p.Close();t.Fatal("incomplete bundle accepted")}
 pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
 if _,e=mvJSONPackageForOffline(pkg);e==nil{t.Fatal("legacy payload enabled offline fallback")}
}

func r44DeniedWorker(engine,dest,journal string)error{
 return mvJSONWorkerFailure(context.Background(),&os.PathError{Op:"CreateProcess",Path:"private",Err:syscall.Errno(5)},filepath.Join(journal,"status.json"))
}
func TestR44JSONCopyButtonAccessDeniedNeverPublishes(t *testing.T){
 root,exe,before,system:=r44DirectFixture(t)
 original:=mvnwbinOfflineSnapshot(t,root)
 pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
 if _,_,e=mvJSONCopyPilotWith(exe,pkg,r44DeniedWorker);e==nil||e.Error()!="IA_MV_JSON_MOTOR_INICIO_OS_5"{t.Fatal("lost access denial",e)}
 r44DirectUnchanged(t,root,before,system);mvnwbinSame(t,original)
 dest:=filepath.Join(filepath.Dir(root),filepath.Base(root)+" - IA JSON")
 if !ordinary(filepath.Join(dest,mvJSONMarker)){t.Fatal("incomplete copy marker missing")}
 if _,e=os.Lstat(filepath.Join(dest,"Game.exe"));!os.IsNotExist(e){t.Fatal("published incomplete executable",e)}
 r44DirectUnchanged(t,dest,before,system)
}
func TestR44JSONDirectAccessDeniedKeepsOriginalAndRecovery(t *testing.T){
 root,exe,before,system:=r44DirectFixture(t)
 original:=mvnwbinOfflineSnapshot(t,root)
 pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
 if _,e=mvJSONInstallDirectWith(exe,pkg,r44DeniedWorker,vxaceAtomicReplaceFrom);e==nil||e.Error()!="IA_MV_JSON_MOTOR_INICIO_OS_5"{t.Fatal("lost access denial",e)}
 r44DirectUnchanged(t,root,before,system);mvnwbinSame(t,original)
 if !mvJSONDirectNeedsRecovery(exe){t.Fatal("lost prepared backups")}
 if e=RecoverGame(exe);e!=nil{t.Fatal(e)}
 if mvJSONDirectNeedsRecovery(exe){t.Fatal("recovery did not retire failed operation")}
 r44DirectUnchanged(t,root,before,system);mvnwbinSame(t,original)
}

func TestR44JSONRuntimeEmptyDataPreservedDuringInstallation(t *testing.T){
 files:=r44RuntimeFixture()
 marker:="json-runtime/_internal/ctranslate2/py.typed"
 files[marker]=[]byte{}
 pkg,e:=readPackage(fakePackageWith(t,[]byte("test plugin"),[]byte("test worker"),files))
 if e!=nil{t.Fatal(e)};defer pkg.Close()
 offline,e:=mvJSONPackageForOffline(pkg);if e!=nil{t.Fatal(e)}
 root:=t.TempDir()
 sidecar,e:=iaPrepareAndPublishSidecar(root,offline);if e!=nil{t.Fatal(e)}
 engine:=filepath.Join(sidecar,".local","Rpg","engine")
 if e=mvJSONVerifyRuntime(engine,offline);e!=nil{t.Fatal(e)}
 st,e:=os.Stat(filepath.Join(engine,filepath.FromSlash(marker)))
 if e!=nil||st.Size()!=0{t.Fatal("empty data was not preserved",e)}
}
func TestR44JSONRuntimeRejectsEmptyNativeAndPathCollisions(t *testing.T){
 for _,name:=range []string{mvJSONRuntimeEXE,"json-runtime/_internal/python311.dll","json-runtime/_internal/base_library.zip","json-runtime/_internal/mod.PYD","json-runtime/_internal/lib.dll","json-runtime/_internal/archive.zip"}{
  files:=r44RuntimeFixture();files[name]=[]byte{}
  if p,e:=readPackage(fakePackageWith(t,[]byte("test plugin"),[]byte("test worker"),files));e==nil{p.Close();t.Fatal("accepted empty native or essential file",name)}
 }
 for _,names:=range [][2]string{
  {"json-runtime/_internal/Package/a.txt","json-runtime/_internal/package/b.txt"},
  {"json-runtime/_internal/file","json-runtime/_internal/file/child.txt"},
  {"json-runtime/_internal/CON .txt","json-runtime/_internal/good.txt"},
  {"json-runtime/_internal/a?.txt","json-runtime/_internal/good.txt"},
 }{
  files:=r44RuntimeFixture()
  for _,name:=range names{files[name]=[]byte("test")}
  if p,e:=readPackage(fakePackageWith(t,[]byte("test plugin"),[]byte("test worker"),files));e==nil{p.Close();t.Fatal("accepted unsafe names",names)}
 }
}
