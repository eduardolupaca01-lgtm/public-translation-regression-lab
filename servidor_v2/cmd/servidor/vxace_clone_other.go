//go:build !windows

package main

import "os"

func vxaceCloneOrdinaryPath(path string)bool{
	st,e:=os.Lstat(path)
	return e==nil&&st.Mode()&os.ModeSymlink==0
}
