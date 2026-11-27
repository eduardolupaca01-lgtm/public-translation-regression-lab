package main

// Explicit experimental mode for a user's already-extracted, self-contained
// web frontend. No extraction, executable patch, injection into a process,
// network listener outside localhost, or modification of game assets.
import(
 "encoding/json"
 "errors"
 "fmt"
 "os"
 "os/exec"
 "path/filepath"
 "regexp"
 "strconv"
 "strings"
)

var webModuleSource=regexp.MustCompile("(?is)<script\\b[^>]*\\bsrc\\s*=\\s*[\"']/?(assets/[A-Za-z0-9_./-]+\\.js)[\"']")

func webValidateFolder(folder string)(string,error){
 root,e:=filepath.Abs(folder)
 if e!=nil||vxaceCloneCheckAncestors(root)!=nil{return "",errors.New("IA_WEB_RUTA_INVALIDA")}
 assets:=filepath.Join(root,"assets")
 if vxaceCloneCheckAncestors(assets)!=nil{return "",errors.New("IA_WEB_RECURSOS_INCOMPLETOS")}
 index:=filepath.Join(root,"index.html")
 st,e:=os.Lstat(index)
 if e!=nil||!st.Mode().IsRegular()||!vxaceCloneOrdinaryPath(index)||st.Size()<=0||st.Size()>1024*1024{
  return "",errors.New("IA_WEB_INDEX_INVALIDO")
 }
 raw,e:=os.ReadFile(index)
 if e!=nil||len(raw)>1024*1024{return "",errors.New("IA_WEB_INDEX_INVALIDO")}
 modules:=webModuleSource.FindAllStringSubmatch(string(raw),9)
 if len(modules)<1||len(modules)>8{return "",errors.New("IA_WEB_MODULO_NO_ADMITIDO")}
 for _,m:=range modules{
  name:=m[1]
  if !safeFile(name)||!strings.HasPrefix(name,"assets/"){return "",errors.New("IA_WEB_MODULO_NO_ADMITIDO")}
  file:=filepath.Join(root,filepath.FromSlash(name))
  st,e:=os.Lstat(file)
  if e!=nil||!st.Mode().IsRegular()||!vxaceCloneOrdinaryPath(file)||vxaceCloneCheckAncestors(filepath.Dir(file))!=nil||st.Size()<=0||st.Size()>16*1024*1024{
   return "",errors.New("IA_WEB_RECURSOS_INCOMPLETOS")
  }
 }
 return root,nil
}

func webPrepare(folder string,pkg *packageReader)(string,string,error){
 root,e:=webValidateFolder(folder)
 if e!=nil{return "","",e}
 sidecar,e:=iaPrepareAndPublishSidecar(root,pkg)
 if e!=nil{return "","",e}
 if e=iaCheckEngine(sidecar,pkg);e!=nil{return "","",e}
 engine:=filepath.Join(sidecar,".local","Rpg","engine")
 if vxaceCloneCheckAncestors(engine)!=nil{return "","",errors.New("IA_WEB_RUTA_INVALIDA")}
 return root,engine,nil
}

func webLaunch(folder string,port int,noBrowser bool,pkg *packageReader)error{
 if port<1024||port>65535{return errors.New("IA_WEB_ARGUMENTOS_INVALIDOS")}
 root,engine,e:=webPrepare(folder,pkg)
 if e!=nil{return e}
 status:=filepath.Join(filepath.Dir(engine),"web-startup-status.json")
 if info,err:=os.Lstat(status);err==nil&&(!info.Mode().IsRegular()||!vxaceCloneOrdinaryPath(status)||info.Size()>1024){
  return errors.New("IA_WEB_DIAGNOSTICO_INVALIDO")
 }else if err!=nil&&!os.IsNotExist(err){return errors.New("IA_WEB_DIAGNOSTICO_INVALIDO")}
 args:=[]string{"--web-root",root,"--web-port",strconv.Itoa(port),"--parent-pid",strconv.Itoa(os.Getpid()),"--diagnostic-file",status}
 if noBrowser{args=append(args,"--web-no-browser")}
 cmd:=exec.Command(filepath.Join(engine,"IATraductora.exe"),args...)
 cmd.Dir=root
 fmt.Println("IA_WEB_PREPARANDO")
 if e=cmd.Run();e!=nil{
  // No raw paths or error messages from a child in the public diagnostic.
  if st,err:=os.Lstat(status);err==nil&&st.Mode().IsRegular()&&vxaceCloneOrdinaryPath(status)&&st.Size()<=1024{
   raw,err:=os.ReadFile(status)
   var record struct{Schema string; Code string}
   if err==nil&&json.Unmarshal(raw,&record)==nil&&record.Schema=="ia-traductora-startup-v1"&&
      regexp.MustCompile("^IA_[A-Z0-9_]{4,86}$").MatchString(record.Code){
    return errors.New(record.Code)
   }
  }
  return errors.New("IA_WEB_INICIO_FALLO")
 }
 fmt.Println("IA_WEB_SESION_CERRADA")
 return nil
}
