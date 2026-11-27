package main

import (
 "archive/zip"
 "bytes"
 "os"
 "path/filepath"
 "strings"
 "testing"
)
func xpLabTestPackage(t *testing.T)*packageReader{
 t.Helper()
 launcher:=vxacePEFixture()
 launcher[68]=0x64;launcher[69]=0x86
 launcher[88]=0x0b;launcher[89]=0x02
 files:=map[string][]byte{
  xpLauncherAsset:launcher,xpPluginAsset:xpTestPlugin(t),
  "IATraductora.exe":[]byte("synthetic worker"),
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
