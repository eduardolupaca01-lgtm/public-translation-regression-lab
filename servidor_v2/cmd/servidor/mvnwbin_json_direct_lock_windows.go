//go:build windows

package main

import(
 "os"
 "path/filepath"
 "syscall"
)

// A nonsharing handle is released by Windows even if Servidor crashes.
// The lock file itself remains, so a stale pathname cannot block recovery.
func mvJSONDirectLock(base string)(func(),error){
 file:=filepath.Join(base,"operation.lock")
 if _,e:=os.Lstat(file);e==nil&&(!ordinary(file)||!vxaceCloneOrdinaryPath(file)){return nil,mvJSONError("DIRECTO_DIARIO_INVALIDO")}else if e!=nil&&!os.IsNotExist(e){return nil,mvJSONError("DIRECTO_DIARIO_INVALIDO")}
 name,e:=vxaceWindowsPath(file);if e!=nil{return nil,mvJSONError("DIRECTO_DIARIO_INVALIDO")}
 h,e:=syscall.CreateFile(name,syscall.GENERIC_READ|syscall.GENERIC_WRITE,0,nil,syscall.OPEN_ALWAYS,0x80|0x00200000,0)
 if e!=nil{return nil,mvJSONError("DIRECTO_OPERACION_ACTIVA")}
 var info syscall.ByHandleFileInformation
 if e=syscall.GetFileInformationByHandle(h,&info);e!=nil||info.FileAttributes&(0x10|0x400)!=0{
  syscall.CloseHandle(h);return nil,mvJSONError("DIRECTO_DIARIO_INVALIDO")
 }
 return func(){_ =syscall.CloseHandle(h)},nil
}
