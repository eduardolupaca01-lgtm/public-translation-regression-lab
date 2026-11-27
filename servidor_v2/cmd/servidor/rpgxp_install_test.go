package main

import (
 "archive/zip"
 "bytes"
 "errors"
 "os"
 "path/filepath"
 "strings"
 "testing"
)
func xpLabTestPackage(t *testing.T)*packageReader{
 return xpLabTestPackageWith(t,xpTestPlugin(t),[]byte("synthetic worker"),0)
}
func xpLabTestPackageWith(t *testing.T,plugin,worker []byte,variant byte)*packageReader{
 t.Helper()
 launcher:=vxacePEFixture()
 launcher[100]=variant
 launcher[68]=0x64;launcher[69]=0x86
 launcher[88]=0x0b;launcher[89]=0x02
 files:=map[string][]byte{
  xpLauncherAsset:launcher,xpPluginAsset:plugin,
  "IATraductora.exe":worker,
  "IATraductora.js":[]byte("synthetic JS"),
  "models/opus_en_es/model.bin":[]byte("synthetic weight"),
 }
 var buf bytes.Buffer
 z:=zip.NewWriter(&buf)
 manifest:=packageManifest{Schema:packageSchema,Files:map[string]string{}}
 for name,raw:=range files{
  w,e:=z.Create(name);if e!=nil{t.Fatal(e)}
  if _,e=w.Write(raw);e!=nil{t.Fatal(e)}
  manifest.Files[name]=hash(raw)
 }
 if e:=z.Close();e!=nil{t.Fatal(e)}
 r,e:=zip.NewReader(bytes.NewReader(buf.Bytes()),int64(buf.Len()));if e!=nil{t.Fatal(e)}
 items:=map[string]*zip.File{}
 for _,f:=range r.File{items[f.Name]=f}
 return &packageReader{archive:r,files:items,manifest:manifest}
}
func TestRPGXPOrdinaryInstallerActivationAndExactRestore(t *testing.T){
 exe:=rpgxpFixture(t);root:=filepath.Dir(exe)
 target:=filepath.Join(root,"Data","Scripts.rxdata")
 original:=xpTestOriginal(t);if e:=os.WriteFile(target,original,0600);e!=nil{t.Fatal(e)}
 pkg:=xpLabTestPackage(t)
 if e:=Install(exe,pkg);e!=nil{t.Fatal(e)}
 _,engine,journal,backup,receiptFile:=xpPaths(root)
 r,ok,e:=xpReadReceipt(receiptFile)
 if e!=nil||!ok||r.Status!="INSTALLED"||r.Before!=hash(original){t.Fatalf("receipt failed: %v",e)}
 if e=xpHashFile(target,r.After);e!=nil{t.Fatal(e)}
 if e=xpHashFile(backup,r.Before);e!=nil{t.Fatal(e)}
 if got,e:=installedPackageIdentity(exe,pkg);e!=nil||!strings.HasPrefix(got,xpLabBuild+" SHA256="){t.Fatalf("XP ordinary identity %q %v",got,e)}
 if e=Install(exe,pkg);e!=nil{t.Fatal("idempotent install",e)}
 cache:=filepath.Join(filepath.Dir(engine),"cache")
 if e=os.Mkdir(cache,0700);e!=nil{t.Fatal(e)}
 sentinel:=filepath.Join(cache,"keep.txt");if e=os.WriteFile(sentinel,[]byte("saved memory"),0600);e!=nil{t.Fatal(e)}
 unlock,e:=xpLock(journal);if e!=nil{t.Fatal(e)}
 if e=RecoverGame(exe);e==nil{t.Fatal("restore during active operation")}
 unlock()
 if e=RecoverGame(exe);e!=nil{t.Fatal(e)}
 actual,e:=os.ReadFile(target);if e!=nil||!bytes.Equal(actual,original){t.Fatal("restore changed bytes")}
 if !ordinary(sentinel){t.Fatal("cache lost")}
 if _,e=installedPackageIdentity(exe,pkg);e==nil{t.Fatal("restored XP incorrectly reported installed")}
 if e=RecoverGame(exe);e!=nil{t.Fatal("idempotent restore",e)}
 if e=Install(exe,pkg);e!=nil{t.Fatal("reinstall",e)}
 if e=os.WriteFile(target,append(original,7),0600);e!=nil{t.Fatal(e)}
 if _,e=installedPackageIdentity(exe,pkg);e==nil{t.Fatal("changed XP incorrectly reported installed")}
 if e=RecoverGame(exe);e==nil{t.Fatal("foreign changes overwritten")}
 actual,e=os.ReadFile(target);if e!=nil||!bytes.Equal(actual,append(original,7)){t.Fatal("foreign changes lost")}
}

func TestRPGXPAdapterUpdateRetainsEngineAndRecoversInterruptedMigration(t *testing.T){
 exe:=rpgxpFixture(t);root:=filepath.Dir(exe)
 target:=filepath.Join(root,"Data","Scripts.rxdata")
 original:=xpTestOriginal(t)
 if e:=os.WriteFile(target,original,0600);e!=nil{t.Fatal(e)}
 oldPlugin:=[]byte(xpScriptMarker+"\n# "+xpLabBuild+"\n# synthetic previous adapter\n")
 allowed:=xpPriorAdapterAllowed
 xpPriorAdapterAllowed=func(s string)bool{return s==hash(oldPlugin)}
 defer func(){xpPriorAdapterAllowed=allowed}()
 oldPkg:=xpLabTestPackageWith(t,oldPlugin,[]byte("old verified worker"),1)
 newPkg:=xpLabTestPackageWith(t,xpTestPlugin(t),[]byte("rebuilt worker"),2)
 if e:=Install(exe,oldPkg);e!=nil{t.Fatal(e)}
 _,engine,journal,backup,receiptFile:=xpPaths(root)
 previous,_,e:=xpReadReceipt(receiptFile);if e!=nil{t.Fatal(e)}
 cache:=filepath.Join(filepath.Dir(engine),"cache")
 if e=os.Mkdir(cache,0700);e!=nil{t.Fatal(e)}
 memory:=filepath.Join(cache,"translation-memory-v2.sqlite3")
 sentinel:=[]byte("synthetic cache bytes")
 if e=os.WriteFile(memory,sentinel,0600);e!=nil{t.Fatal(e)}
 replace:=vxaceMoveReplacement
 vxaceMoveReplacement=func(source,destination string,expected os.FileInfo)error{
  if destination==target{return errors.New("IA_RPGXP_TEST_INTERRUPT")}
  return replace(source,destination,expected)
 }
 failed:=Install(exe,newPkg)
 vxaceMoveReplacement=replace
 if failed==nil{t.Fatal("expected interrupted migration")}
 if _,ok,e:=xpReadTransition(journal);e!=nil||!ok{t.Fatalf("missing transition: %v",e)}
 if e=RecoverGame(exe);e!=nil{t.Fatal("interrupted update recovery",e)}
 if e=xpHashFile(target,previous.Before);e!=nil{t.Fatal(e)}
 if e=xpHashFile(filepath.Join(engine,filepath.FromSlash(xpPluginAsset)),previous.Plugin);e!=nil{t.Fatal(e)}
 if e=Install(exe,newPkg);e!=nil{t.Fatal("upgrade from restored copy",e)}
 got,ok,e:=xpReadReceipt(receiptFile);if e!=nil||!ok||got.Status!="INSTALLED"||got.Plugin!=newPkg.manifest.Files[xpPluginAsset]{t.Fatal("new receipt missing",e)}
 if got.Worker!=previous.Worker||got.Launcher!=previous.Launcher||got.Before!=previous.Before{t.Fatal("engine or original replaced")}
 if identity,e:=installedPackageIdentity(exe,newPkg);e!=nil||!strings.Contains(identity,"MOTOR=CONSERVADO"){t.Fatalf("identity %q %v",identity,e)}
 if e=xpHashFile(backup,previous.Before);e!=nil{t.Fatal(e)}
 if e=xpHashFile(filepath.Join(engine,"IATraductora.exe"),previous.Worker);e!=nil{t.Fatal(e)}
 if e=Install(exe,newPkg);e!=nil{t.Fatal("repeat",e)}
 if e=RecoverGame(exe);e!=nil{t.Fatal("restore new adapter",e)}
 if e=Install(exe,newPkg);e!=nil{t.Fatal("reinstall new adapter",e)}
 if b,e:=os.ReadFile(memory);e!=nil||!bytes.Equal(b,sentinel){t.Fatal("cache changed")}
}
