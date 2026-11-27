package main

// Create-only copy of an already extracted, standalone web frontend.
// All executable components come exclusively from our verified package.
import (
 "encoding/json"
 "errors"
 "io/fs"
 "net"
 "os"
 "path/filepath"
 "strings"
)

const webCopyMarker="IA_COPIA_WEB_INCOMPLETA.txt"
const webCopyReceipt="web-copy-v1.json"
const webPlayer="Jugar-IA.exe"
var webHostFiles=[]string{webPlayer,"Jugar-IA.exe.config","Microsoft.Web.WebView2.Core.dll",
 "Microsoft.Web.WebView2.WinForms.dll","WebView2Loader.dll","WebView2-LICENSE.txt"}
var webAssetExtensions=map[string]bool{
 ".js":true,".mjs":true,".css":true,".json":true,".wasm":true,".txt":true,
 ".png":true,".jpg":true,".jpeg":true,".webp":true,".gif":true,".bmp":true,
 ".svg":true,".ico":true,".mp3":true,".wav":true,".ogg":true,".m4a":true,
 ".aac":true,".mp4":true,".webm":true,".ogv":true,".ttf":true,".otf":true,
 ".woff":true,".woff2":true,
}
type webCopyEntry struct{rel string;info os.FileInfo}
type webReceipt struct{
 Schema string `json:"schema"`
 Port int `json:"port"`
 IndexSHA string `json:"index_sha256"`
 EngineSHA map[string]string `json:"engine_sha256"`
 HostSHA map[string]string `json:"host_sha256"`
}
func webClonePlan(root string)([]webCopyEntry,uint64,error){
 root,e:=webValidateFolder(root)
 if e!=nil{return nil,0,e}
 index,e:=os.Lstat(filepath.Join(root,"index.html"))
 if e!=nil{return nil,0,errors.New("IA_WEB_INDEX_INVALIDO")}
 entries:=[]webCopyEntry{{"index.html",index}}
 total:=uint64(index.Size())
 seen:=map[string]bool{"index.html":true}
 e=filepath.WalkDir(filepath.Join(root,"assets"),func(path string,d fs.DirEntry,walkErr error)error{
  if walkErr!=nil{return errors.New("IA_WEB_COPIA_NO_LEIBLE")}
  info,err:=os.Lstat(path)
  if err!=nil||info.Mode()&os.ModeSymlink!=0||!vxaceCloneOrdinaryPath(path)||
     (!info.IsDir()&&!info.Mode().IsRegular()){
   return errors.New("IA_WEB_COPIA_RUTA_INSEGURA")
  }
  rel,err:=filepath.Rel(root,path)
  slash:=filepath.ToSlash(rel)
  if err!=nil||!safeFile(slash){return errors.New("IA_WEB_COPIA_RUTA_INSEGURA")}
  for _,part:=range strings.Split(slash,"/"){
   if strings.HasSuffix(part,".")||strings.HasSuffix(part," "){return errors.New("IA_WEB_COPIA_RUTA_INSEGURA")}
  }
  key:=strings.ToLower(slash)
  if seen[key]{return errors.New("IA_WEB_COPIA_RUTA_DUPLICADA")}
  seen[key]=true
  if !info.IsDir(){
   if !webAssetExtensions[strings.ToLower(filepath.Ext(path))]||info.Size()>2*1024*1024*1024{
    return errors.New("IA_WEB_COPIA_RECURSO_NO_ADMITIDO")
   }
   total+=uint64(info.Size())
  }
  if len(entries)>=20000||total>32*1024*1024*1024{return errors.New("IA_WEB_COPIA_TAMANO_EXCESIVO")}
  entries=append(entries,webCopyEntry{rel,info})
  return nil
 })
 if e!=nil{return nil,0,e}
 return entries,total,nil
}
func webCloneInstall(folder,parent string,pkg *packageReader)(string,error){
 root,e:=webValidateFolder(folder)
 if e!=nil{return "",e}
 if pkg==nil{return "",errors.New("IA_WEB_HOST_NO_INCLUIDO")}
 for _,name:=range webHostFiles{
  if pkg.files["webhost/"+name]==nil{return "",errors.New("IA_WEB_HOST_NO_INCLUIDO")}
 }
 if parent==""{parent=filepath.Dir(root)}
 parent,e=filepath.Abs(parent)
 if e!=nil||vxaceCloneCheckAncestors(parent)!=nil{return "",errors.New("IA_WEB_COPIA_DESTINO_INVALIDO")}
 a,e:=filepath.EvalSymlinks(root);if e!=nil{return "",errors.New("IA_WEB_COPIA_RUTA_INSEGURA")}
 b,e:=filepath.EvalSymlinks(parent);if e!=nil{return "",errors.New("IA_WEB_COPIA_DESTINO_INVALIDO")}
 rel,e:=filepath.Rel(strings.ToLower(a),strings.ToLower(b))
 if e==nil&&rel!=".."&&!strings.HasPrefix(rel,".."+string(filepath.Separator)){
  return "",errors.New("IA_WEB_COPIA_DESTINO_DENTRO_DEL_ORIGEN")
 }
 entries,total,e:=webClonePlan(root)
 if e!=nil{return "",e}
 if e=vxaceCheckDiskSpace(parent,total+2*1024*1024*1024);e!=nil{return "",e}
 dest,e:=os.MkdirTemp(parent,"Juego-IA-WEB-")
 if e!=nil{return "",errors.New("IA_WEB_COPIA_DESTINO_INVALIDO")}
 marker:=filepath.Join(dest,webCopyMarker)
 if e=createNew(marker,[]byte("Copia incompleta. No ejecutar. El origen permanece intacto.\n"));e!=nil{return "",e}
 for _,entry:=range entries{
  from,to:=filepath.Join(root,entry.rel),filepath.Join(dest,entry.rel)
  info,e:=os.Lstat(from)
  if e!=nil||!os.SameFile(info,entry.info)||!vxaceCloneOrdinaryPath(from){return "",errors.New("IA_WEB_COPIA_ORIGEN_CAMBIADO")}
  if entry.info.IsDir(){
   if !info.IsDir()||vxaceCloneCheckAncestors(from)!=nil{return "",errors.New("IA_WEB_COPIA_RUTA_INSEGURA")}
   if e=os.Mkdir(to,0700);e!=nil{return "",errors.New("IA_WEB_COPIA_DESTINO_INVALIDO")}
  }else{
   if !vxaceSameReplaceFile(info,entry.info){return "",errors.New("IA_WEB_COPIA_ORIGEN_CAMBIADO")}
   if e=vxaceCloneFile(from,to);e!=nil{return "",e}
   info,e=os.Lstat(from)
   if e!=nil||!vxaceSameReplaceFile(info,entry.info){return "",errors.New("IA_WEB_COPIA_ORIGEN_CAMBIADO")}
  }
 }
 _,engine,e:=webPrepare(dest,pkg)
 if e!=nil{return "",e}
 hostSHA:=map[string]string{}
 // The host executable is created last. No original game binary is copied.
 for _,name:=range webHostFiles[1:]{
  from,to:=filepath.Join(engine,"webhost",name),filepath.Join(dest,name)
  if e=vxaceCloneFile(from,to);e!=nil{return "",e}
  d,e:=digestFile(to);if e!=nil||d!=pkg.manifest.Files["webhost/"+name]{return "",errors.New("IA_WEB_HOST_SHA_INVALIDO")}
  hostSHA[name]=d
 }
 listener,e:=net.Listen("tcp4","127.0.0.1:0")
 if e!=nil{return "",errors.New("IA_WEB_PUERTO_NO_DISPONIBLE")}
 port:=listener.Addr().(*net.TCPAddr).Port
 listener.Close()
 indexSHA,e:=digestFile(filepath.Join(dest,"index.html"));if e!=nil{return "",e}
 hostSHA[webPlayer]=pkg.manifest.Files["webhost/"+webPlayer]
 engineSHA:=map[string]string{}
 for _,name:=range iaSortedFiles(pkg){engineSHA[name]=pkg.manifest.Files[name]}
 receipt:=webReceipt{"ia-web-desktop-v1",port,indexSHA,engineSHA,hostSHA}
 raw,e:=json.MarshalIndent(receipt,"","  ");if e!=nil{return "",e}
 if e=createNew(filepath.Join(dest,webCopyReceipt),raw);e!=nil{return "",e}
 launcher:=filepath.Join(dest,webPlayer)
 if e=vxaceCloneFile(filepath.Join(engine,"webhost",webPlayer),launcher);e!=nil{return "",e}
 if d,e:=digestFile(launcher);e!=nil||d!=hostSHA[webPlayer]{return "",errors.New("IA_WEB_HOST_SHA_INVALIDO")}
 if e=os.Remove(marker);e!=nil{return "",errors.New("IA_WEB_COPIA_MARCADOR_FALLO")}
 return launcher,nil
}
