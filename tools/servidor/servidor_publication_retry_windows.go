//go:build windows

package main

import(
    "errors"
    "os"
    "path/filepath"
    "syscall"
    "time"
)

// TX782: Windows antivirus can transiently hold a newly extracted V95
// executable and prevent renaming the parent stage. Retry only sharing
// and access errors. Never delete or overwrite an existing destination.
var servidorRenamePortableSidecar=os.Rename
var servidorRetryPortableSleep=time.Sleep

func servidorPublishPortableSidecar(stage,sidecar string)error{
    if !filepath.IsAbs(stage)||!filepath.IsAbs(sidecar)||
       filepath.Clean(filepath.Dir(stage))!=filepath.Clean(filepath.Dir(sidecar))||
       filepath.Clean(stage)==filepath.Clean(sidecar){
        return errors.New("TX782_PORTABLE_PUBLISH_PATH_INVALID")
    }
    source,err:=os.Lstat(stage)
    if err!=nil||!source.IsDir()||source.Mode()&os.ModeSymlink!=0{
        return errors.New("TX782_PORTABLE_SOURCE_NOT_REGULAR_DIRECTORY")
    }
    for attempt:=0;attempt<18;attempt++{
        if _,err:=os.Lstat(sidecar);err==nil{
            return errors.New("TX782_PORTABLE_DESTINATION_ALREADY_EXISTS")
        }else if !os.IsNotExist(err){
            return errors.New("TX782_PORTABLE_DESTINATION_CANNOT_BE_VERIFIED")
        }
        err=servidorRenamePortableSidecar(stage,sidecar)
        if err==nil{return nil}
        if !errors.Is(err,syscall.Errno(5)) &&
           !errors.Is(err,syscall.Errno(32)) &&
           !errors.Is(err,syscall.Errno(33)){
            return err
        }
        if attempt<17{
            servidorRetryPortableSleep(time.Duration(250+attempt*95)*time.Millisecond)
        }
    }
    return errors.New("TX782_WINDOWS_PUBLICATION_LOCK_EXHAUSTED")
}
