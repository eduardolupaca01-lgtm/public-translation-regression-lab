//go:build !windows

package main

import (
	"errors"
	"os"
)

func vxaceReplaceOnce(source,destination string,expected os.FileInfo)error{
	current,err:=os.Lstat(destination)
	if err!=nil||!vxaceSameReplaceFile(expected,current){
		return errors.New("IA_VXACE_RECURSO_CAMBIO_DURANTE_REEMPLAZO")
	}
	return os.Rename(source,destination)
}
