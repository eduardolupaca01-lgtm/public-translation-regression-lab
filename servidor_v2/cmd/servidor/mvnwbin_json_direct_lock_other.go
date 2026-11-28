//go:build !windows

package main

import(
 "os"
 "path/filepath"
 "syscall"
)

func mvJSONDirectLock(base string)(func(),error){
 file:=filepath.Join(base,"operation.lock")
 fd,e:=syscall.Open(file,syscall.O_CREAT|syscall.O_RDWR|syscall.O_NOFOLLOW,0600)
 if e!=nil{return nil,mvJSONError("DIRECTO_DIARIO_INVALIDO")}
 f:=os.NewFile(uintptr(fd),file)
 st,e:=f.Stat()
 if e!=nil||!st.Mode().IsRegular(){f.Close();return nil,mvJSONError("DIRECTO_DIARIO_INVALIDO")}
 if e=syscall.Flock(fd,syscall.LOCK_EX|syscall.LOCK_NB);e!=nil{f.Close();return nil,mvJSONError("DIRECTO_OPERACION_ACTIVA")}
 return func(){_ =syscall.Flock(fd,syscall.LOCK_UN);_ =f.Close()},nil
}
