package main

import (
 "errors"
 "os"
 "os/exec"
 "path/filepath"
 "runtime"
 "strings"
)

func prepareScreen(gameEXE,cacheRoot string,pkg *packageReader)(profile,worker string,err error){
 _,_,e:=detectGame(gameEXE)
 if e==nil||!strings.HasPrefix(e.Error(),cookToolPackedCode+":"){return "","",errors.New("IA_OCR_FORMATO_NO_ADMITIDO")}
 abs,e:=filepath.Abs(gameEXE);if e!=nil{return "","",e}
 root:=filepath.Dir(abs)
 if runtime.GOOS=="windows"{root=strings.ToLower(root)}
 st,e:=os.Lstat(cacheRoot)
 if e!=nil||!st.IsDir()||st.Mode()&os.ModeSymlink!=0{return "","",errors.New("IA_OCR_CACHE_NO_DISPONIBLE")}
 rel:=filepath.Join(brandFolder,"RpgScreen",hash([]byte(root)))
 profile=filepath.Join(cacheRoot,rel)
 ver:=hash([]byte(pkg.manifest.Files["IATraductora.exe"]+":"+pkg.manifest.Files["IATraductora.js"]))
 versionRoot:=filepath.Join(profile,"versions",ver)
 if e=iaMakeSafeDirs(cacheRoot,filepath.Join(rel,"versions",ver));e!=nil{return "","",e}
 if e=iaMakeSafeDirs(cacheRoot,filepath.Join(rel,brandFolder,".local","Rpg"));e!=nil{return "","",e}
 sidecar,e:=prepareSidecar(versionRoot,pkg);if e!=nil{return "","",e}
 if e=iaCheckEngine(sidecar,pkg);e!=nil{return "","",e}
 worker=filepath.Join(sidecar,".local","Rpg","engine","IATraductora.exe")
 return profile,worker,nil
}

func launchScreen(gameEXE string,pkg *packageReader)error{
 if runtime.GOOS!="windows"{return errors.New("IA_OCR_WINDOWS_REQUERIDO")}
 cacheRoot,e:=os.UserCacheDir();if e!=nil{return errors.New("IA_OCR_CACHE_NO_DISPONIBLE")}
 profile,worker,e:=prepareScreen(gameEXE,cacheRoot,pkg);if e!=nil{return e}
 cmd:=exec.Command(worker,"--screen-root",profile)
 cmd.Dir=filepath.Dir(worker)
 if e=cmd.Start();e!=nil{return errors.New("IA_OCR_NO_SE_PUEDE_LANZAR")}
 go func(){_ =cmd.Wait()}()
 return nil
}
