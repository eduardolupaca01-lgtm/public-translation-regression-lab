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
