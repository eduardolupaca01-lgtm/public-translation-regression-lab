//go:build windows

package main

// Servidor keeps the EXACT verified App location chosen by the original
// TX567 Windows sharing-lock fallback. It must not assume App/<payload-sha>
// when Windows forced verified files to stay in App/.stage-*.
import (
    "errors"
    "os"
    "path/filepath"
    "strings"
    "syscall"
    "time"
)

func servidorPublishedPortableApp(stageRoot,stagedApp,sidecar,key string)(string,error){
    if !filepath.IsAbs(stageRoot)||!filepath.IsAbs(stagedApp)||!filepath.IsAbs(sidecar){
        return "",errors.New("SERVIDOR_PORTABLE_APP_NONABSOLUTE")
    }
    appRoot:=filepath.Join(stageRoot,"App")
    rel,err:=filepath.Rel(appRoot,stagedApp)
    if err!=nil||rel=="."||rel==""||rel==".."||filepath.IsAbs(rel)||
        strings.Contains(rel,string(filepath.Separator)){
        return "",errors.New("SERVIDOR_PORTABLE_APP_NOT_DIRECT_CHILD")
    }
    // TX567 only allows the exact payload digest or its OWN verified stage.
    if rel!=key&&!(strings.HasPrefix(rel,".stage-")&&len(rel)>len(".stage-")){
        return "",errors.New("SERVIDOR_PORTABLE_APP_UNKNOWN_NAME")
    }
    info,err:=os.Lstat(stagedApp)
    if err!=nil||!info.IsDir()||info.Mode()&os.ModeSymlink!=0{
        return "",errors.New("SERVIDOR_PORTABLE_APP_UNSAFE_SOURCE")
    }
    return filepath.Join(sidecar,"App",rel),nil
}


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
