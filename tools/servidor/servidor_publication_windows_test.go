//go:build windows

package main

import (
    "crypto/sha256"
    "encoding/hex"
    "os"
    "path/filepath"
    "strings"
    "syscall"
    "testing"
    "time"
)

func TestServidorPortablePublishedAppUsesActualVerifiedFallback(t *testing.T){
    root:=t.TempDir()
    stage:=filepath.Join(root,".tx771-onefile-stage-demo")
    apps:=filepath.Join(stage,"App")
    stagedApp:=filepath.Join(apps,".stage-verified-files")
    if err:=os.MkdirAll(stagedApp,0700);err!=nil{t.Fatal(err)}
    contents:=[]byte("V95 signed-payload fixture - no neural model")
    name:="TenshixgameHost.exe"
    if err:=os.WriteFile(filepath.Join(stagedApp,name),contents,0600);err!=nil{t.Fatal(err)}
    sum:=sha256.Sum256(contents)
    payload:=&appendedPayload{manifest:payloadManifest{Files:map[string]payloadFile{
        name:{Bytes:int64(len(contents)),SHA256:hex.EncodeToString(sum[:])},
    }}}
    key:=strings.Repeat("a",24)
    target:=filepath.Join(apps,key)
    previousRename:=renameRPGPrivateAppDirectory
    previousSleep:=rpgInstallRetrySleep
    renameRPGPrivateAppDirectory=func(string,string)error{return syscall.Errno(32)}
    rpgInstallRetrySleep=func(time.Duration){}
    defer func(){renameRPGPrivateAppDirectory=previousRename;rpgInstallRetrySleep=previousSleep}()
    selected,keep,err:=activateVerifiedRPGStage(apps,stagedApp,target,payload)
    if err!=nil||!keep||selected!=stagedApp{
        t.Fatalf("TX567 should retain SHA-verified App/.stage-* fallback: %q %v %v",selected,keep,err)
    }
    sidecar:=filepath.Join(root,"Tenshixgame-IA")
    actual,err:=servidorPublishedPortableApp(stage,selected,sidecar,key)
    if err!=nil{t.Fatal(err)}
    if err=os.Rename(stage,sidecar);err!=nil{t.Fatal(err)}
    if err=verifyDirectory(actual,payload);err!=nil{
        t.Fatalf("published fallback bytes should pass original V95 SHA checks: %v",err)
    }
    wrong:=filepath.Join(sidecar,"App",key)
    if err=verifyDirectory(wrong,payload);err==nil{
        t.Fatal("regression not reproduced: legacy App/<sha> incorrectly accepted")
    }
    if actual!=filepath.Join(sidecar,"App",".stage-verified-files"){
        t.Fatalf("lost verified fallback location: %q",actual)
    }
}
func TestServidorPortablePublishedAppNormalDigest(t *testing.T){
    root:=t.TempDir()
    stage:=filepath.Join(root,"random-stage")
    key:=strings.Repeat("a",24)
    app:=filepath.Join(stage,"App",key)
    if err:=os.MkdirAll(app,0700);err!=nil{t.Fatal(err)}
    published,err:=servidorPublishedPortableApp(stage,app,filepath.Join(root,"published"),key)
    if err!=nil||published!=filepath.Join(root,"published","App",key){
        t.Fatalf("normal committed app must keep its digest path: %q %v",published,err)
    }
}
func TestServidorPortablePublishedAppRefusesOtherData(t *testing.T){
    root:=t.TempDir()
    stage:=filepath.Join(root,"stage")
    sidecar:=filepath.Join(root,"sidecar")
    key:=strings.Repeat("b",24)
    for _,bad:=range []string{
        filepath.Join(root,"other-app"),
        filepath.Join(stage,"App","unknown-file"),
        filepath.Join(stage,"App",key,"other-game"),
        filepath.Join(stage,"App",".stage-"),
    }{
        if err:=os.MkdirAll(bad,0700);err!=nil{t.Fatal(err)}
        if _,err:=servidorPublishedPortableApp(stage,bad,sidecar,key);err==nil{
            t.Fatalf("unsafe source accepted: %q",bad)
        }
    }
}
