//go:build windows

package main

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

const vxaceReadOnly uint32=1
const vxaceNormalAttribute uint32=0x80
const vxaceReparseAttribute uint32=0x400

var vxaceMoveFileEx=syscall.NewLazyDLL("kernel32.dll").NewProc("MoveFileExW")

func vxaceWindowsPath(filename string)(*uint16,error){
	absolute,err:=filepath.Abs(filename)
	if err!=nil{return nil,err}
	// Both files reside in the same game directory. Support long Unicode
	// paths without falling back to copy/delete across volumes.
	if !strings.HasPrefix(absolute,"\\\\?\\"){
		if strings.HasPrefix(absolute,"\\\\"){
			absolute="\\\\?\\UNC\\"+strings.TrimPrefix(absolute,"\\\\")
		}else{absolute="\\\\?\\"+absolute}
	}
	return syscall.UTF16PtrFromString(absolute)
}

func vxaceReplaceOnce(source,destination string,expected os.FileInfo)error{
	current,err:=os.Lstat(destination)
	if err!=nil||!vxaceSameReplaceFile(expected,current){
		return errors.New("IA_VXACE_RECURSO_CAMBIO_DURANTE_REEMPLAZO")
	}
	src,err:=vxaceWindowsPath(source);if err!=nil{return err}
	dst,err:=vxaceWindowsPath(destination);if err!=nil{return err}
	srcAttrs,err:=syscall.GetFileAttributes(src);if err!=nil{return err}
	attrs,err:=syscall.GetFileAttributes(dst);if err!=nil{return err}
	if srcAttrs&vxaceReparseAttribute!=0||attrs&vxaceReparseAttribute!=0{
		return errors.New("IA_VXACE_REPLACE_TARGET_UNSAFE")
	}
	readonly:=attrs&vxaceReadOnly!=0
	// The user is installing into a closed copy. Change only the legacy
	// DOS read-only bit of this verified file, never its ACL or directory.
	// Restore the bit on both success and failure.
	if readonly{
		writable:=attrs &^ vxaceReadOnly
		if writable==0{writable=vxaceNormalAttribute}
		if err=syscall.SetFileAttributes(dst,writable);err!=nil{return err}
	}
	restoreOriginal:=func()error{
		if !readonly{return nil}
		now,e:=os.Lstat(destination)
		if e!=nil||!vxaceSameReplaceFile(expected,now){
			return errors.New("IA_VXACE_REPLACE_ATTR_RESTORE_FAILED")
		}
		a,e:=syscall.GetFileAttributes(dst)
		if e!=nil||a&vxaceReparseAttribute!=0{return errors.New("IA_VXACE_REPLACE_ATTR_RESTORE_FAILED")}
		if e=syscall.SetFileAttributes(dst,(a &^ vxaceNormalAttribute)|vxaceReadOnly);e!=nil{
			return errors.New("IA_VXACE_REPLACE_ATTR_RESTORE_FAILED")
		}
		return nil
	}
	// MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH. Deliberately
	// omit COPY_ALLOWED, DELAY_UNTIL_REBOOT and any destructive fallback.
	// A failure leaves the journal and original backup intact.
	ok,_,moveErr:=vxaceMoveFileEx.Call(uintptr(unsafe.Pointer(src)),uintptr(unsafe.Pointer(dst)),0x1|0x8)
	if ok==0{
		if e:=restoreOriginal();e!=nil{return e}
		if moveErr==nil||moveErr==syscall.Errno(0){return errors.New("IA_VXACE_REPLACE_ATOMIC_FAILED")}
		return moveErr
	}
	if readonly{
		a,e:=syscall.GetFileAttributes(dst)
		if e!=nil||a&vxaceReparseAttribute!=0{return errors.New("IA_VXACE_REPLACE_ATTR_RESTORE_FAILED")}
		if e=syscall.SetFileAttributes(dst,(a &^ vxaceNormalAttribute)|vxaceReadOnly);e!=nil{
			return errors.New("IA_VXACE_REPLACE_ATTR_RESTORE_FAILED")
		}
	}
	return nil
}
