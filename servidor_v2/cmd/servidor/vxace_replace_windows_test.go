//go:build windows

package main

import(
	"os"
	"path/filepath"
	"syscall"
	"testing"
	"time"
)

func vxaceTestAttrs(t *testing.T,file string)uint32{
	t.Helper()
	p,e:=vxaceWindowsPath(file);if e!=nil{t.Fatal(e)}
	a,e:=syscall.GetFileAttributes(p);if e!=nil{t.Fatal(e)}
	return a
}

func TestVXAceWindowsReadOnlyArchiveReplacementAndRecovery(t *testing.T){
	dir:=filepath.Join(t.TempDir(),"Juego 日本語")
	if e:=os.Mkdir(dir,0700);e!=nil{t.Fatal(e)}
	dst:=filepath.Join(dir,"Game.rgss3a")
	src:=filepath.Join(dir,"prepared")
	backup:=filepath.Join(dir,"backup")
	before,after:=[]byte("original archive"),[]byte("new archive")
	for f,b:=range map[string][]byte{dst:before,src:after,backup:before}{
		if e:=os.WriteFile(f,b,0600);e!=nil{t.Fatal(e)}
	}
	t.Cleanup(func(){_ =os.Chmod(dst,0600)})
	if e:=os.Chmod(dst,0400);e!=nil{t.Fatal(e)}
	if vxaceTestAttrs(t,dst)&vxaceReadOnly==0{t.Fatal("read-only fixture invalid")}
	if e:=vxaceAtomicReplaceFrom(src,dst,hash(after),hash(before));e!=nil{t.Fatal(e)}
	if vxaceTestAttrs(t,dst)&vxaceReadOnly==0{t.Fatal("read-only flag lost after install")}
	if raw,_:=os.ReadFile(dst);string(raw)!=string(after){t.Fatal("install content mismatch")}
	if e:=vxaceAtomicReplaceFrom(backup,dst,hash(before),hash(after));e!=nil{t.Fatal(e)}
	if raw,_:=os.ReadFile(dst);string(raw)!=string(before){t.Fatal("recovery content mismatch")}
	if vxaceTestAttrs(t,dst)&vxaceReadOnly==0{t.Fatal("read-only flag lost after recovery")}
}

func TestVXAceWindowsRealFileSharingLock(t *testing.T){
	for _,release:=range []bool{false,true}{
		t.Run(map[bool]string{false:"persistent",true:"released"}[release],func(t *testing.T){
			dir:=t.TempDir()
			dst,src:=filepath.Join(dir,"Game.rgss3a"),filepath.Join(dir,"prepared")
			before,after:=[]byte("original archive"),[]byte("new archive")
			if e:=os.WriteFile(dst,before,0600);e!=nil{t.Fatal(e)}
			if e:=os.WriteFile(src,after,0600);e!=nil{t.Fatal(e)}
			p,e:=vxaceWindowsPath(dst);if e!=nil{t.Fatal(e)}
			// A genuine Win32 open handle with no FILE_SHARE_DELETE.
			h,e:=syscall.CreateFile(p,syscall.GENERIC_READ,syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE,nil,syscall.OPEN_EXISTING,syscall.FILE_ATTRIBUTE_NORMAL,0)
			if e!=nil{t.Fatal(e)}
			defer func(){if h!=0{_ =syscall.CloseHandle(h)}}()
			sleep:=vxaceReplacementSleep
			defer func(){vxaceReplacementSleep=sleep}()
			retries:=0
			vxaceReplacementSleep=func(time.Duration){
				retries++
				if release&&h!=0{
					if e:=syscall.CloseHandle(h);e!=nil{t.Fatal(e)}
					h=0
				}
			}
			e=vxaceAtomicReplaceFrom(src,dst,hash(after),hash(before))
			if release{
				if e!=nil||retries<1{t.Fatalf("real lock not recovered: %v (%d retries)",e,retries)}
				if raw,_:=os.ReadFile(dst);string(raw)!=string(after){t.Fatal("wrong replacement")}
			}else{
				if e==nil||retries!=5{t.Fatalf("persistent lock not reported: %v (%d retries)",e,retries)}
				if e.Error()!="IA_VXACE_REPLACE_SHARING_WIN32_32"&&e.Error()!="IA_VXACE_REPLACE_ACCESS_DENIED_WIN32_5"&&e.Error()!="IA_VXACE_REPLACE_LOCKED_WIN32_33"{t.Fatalf("lost Windows error: %v",e)}
				if raw,_:=os.ReadFile(dst);string(raw)!=string(before){t.Fatal("original changed despite lock")}
			}
			tmp,e:=filepath.Glob(filepath.Join(dir,".ia-vxace-replace-*"))
			if e!=nil||len(tmp)!=0{t.Fatal("temporary file left behind")}
		})
	}
}
