//go:build windows

package main

import(
    "errors"
    "os"
    "path/filepath"
    "syscall"
    "testing"
    "time"
)

func tx782Fixture(t *testing.T)(string,string){
    t.Helper()
    root:=t.TempDir()
    stage:=filepath.Join(root,".tx771-onefile-stage-example")
    dest:=filepath.Join(root,"portable-traductora")
    if err:=os.Mkdir(stage,0700);err!=nil{t.Fatal(err)}
    if err:=os.WriteFile(filepath.Join(stage,"sha-protected-model.bin"),[]byte("verified"),0600);err!=nil{t.Fatal(err)}
    return stage,dest
}
func TestServidorPortablePublishRetriesSharingLockWithoutOverwriting(t *testing.T){
    stage,dest:=tx782Fixture(t)
    previousRename,previousSleep:=servidorRenamePortableSidecar,servidorRetryPortableSleep
    defer func(){servidorRenamePortableSidecar=previousRename;servidorRetryPortableSleep=previousSleep}()
    tries:=0
    servidorRetryPortableSleep=func(time.Duration){}
    servidorRenamePortableSidecar=func(from,to string)error{
        tries++
        if tries<=3{return syscall.Errno(32)}
        return os.Rename(from,to)
    }
    if err:=servidorPublishPortableSidecar(stage,dest);err!=nil{t.Fatal(err)}
    if tries!=4{t.Fatalf("transient lock retry count=%d",tries)}
    data,err:=os.ReadFile(filepath.Join(dest,"sha-protected-model.bin"))
    if err!=nil||string(data)!="verified"{t.Fatal("published model bytes changed")}
}
func TestServidorPortablePublishRefusesForeignDestination(t *testing.T){
    stage,dest:=tx782Fixture(t)
    if err:=os.Mkdir(dest,0700);err!=nil{t.Fatal(err)}
    if err:=os.WriteFile(filepath.Join(dest,"save.rpgsave"),[]byte("KEEP"),0600);err!=nil{t.Fatal(err)}
    if err:=servidorPublishPortableSidecar(stage,dest);err==nil{t.Fatal("foreign destination overwritten")}
    data,_:=os.ReadFile(filepath.Join(dest,"save.rpgsave"))
    if string(data)!="KEEP"{t.Fatal("existing save altered")}
    if _,err:=os.Stat(filepath.Join(stage,"sha-protected-model.bin"));err!=nil{t.Fatal(err)}
}
func TestServidorPortablePublishFailsClosedOnDiskFull(t *testing.T){
    stage,dest:=tx782Fixture(t)
    previousRename,previousSleep:=servidorRenamePortableSidecar,servidorRetryPortableSleep
    defer func(){servidorRenamePortableSidecar=previousRename;servidorRetryPortableSleep=previousSleep}()
    tries:=0
    servidorRenamePortableSidecar=func(string,string)error{tries++;return syscall.Errno(112)}
    servidorRetryPortableSleep=func(time.Duration){t.Fatal("non transient error retried")}
    err:=servidorPublishPortableSidecar(stage,dest)
    if !errors.Is(err,syscall.Errno(112))||tries!=1{t.Fatalf("disk error must fail closed: %v %d",err,tries)}
}
func TestServidorPortablePublishBoundedRetryPreservesStage(t *testing.T){
    stage,dest:=tx782Fixture(t)
    previousRename,previousSleep:=servidorRenamePortableSidecar,servidorRetryPortableSleep
    defer func(){servidorRenamePortableSidecar=previousRename;servidorRetryPortableSleep=previousSleep}()
    tries:=0
    servidorRenamePortableSidecar=func(string,string)error{tries++;return syscall.Errno(33)}
    servidorRetryPortableSleep=func(time.Duration){}
    if err:=servidorPublishPortableSidecar(stage,dest);err==nil||tries!=18{
        t.Fatalf("unbounded retry or false success, attempts=%d err=%v",tries,err)
    }
    if _,err:=os.Stat(filepath.Join(stage,"sha-protected-model.bin"));err!=nil{t.Fatal(err)}
    if _,err:=os.Lstat(dest);!os.IsNotExist(err){t.Fatal("bad destination created")}
}
