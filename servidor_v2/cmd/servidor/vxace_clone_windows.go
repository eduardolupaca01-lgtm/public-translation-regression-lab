//go:build windows

package main

import "syscall"

func vxaceCloneOrdinaryPath(path string)bool{
	p,e:=vxaceWindowsPath(path)
	if e!=nil{return false}
	a,e:=syscall.GetFileAttributes(p)
	return e==nil&&a&vxaceReparseAttribute==0
}
