package main

// Publication v2: staged, SHA-verified, resumable and fail-closed.
// Only the named IA Traductora directory in the selected CLOSED RPG MV copy.
// Never overwrites foreign files, game data, saves or an unrelated runtime.
import (
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "io"
 "io/fs"
 "os"
 "path/filepath"
 "runtime"
 "sort"
 "strings"
 "syscall"
 "time"
)

var iaRenameStage=os.Rename
var iaMkdirDestination=os.Mkdir
var iaRetrySleep=time.Sleep

func iaPathIsPresent(path string)(bool,error){
 st,err:=os.Lstat(path)
 if err==nil{
  if st.Mode()&os.ModeSymlink!=0{return false,errors.New("IA_DESTINO_ES_ENLACE")}
  return true,nil
 }
 if errors.Is(err,fs.ErrNotExist){return false,nil}
 if errors.Is(err,fs.ErrPermission){return false,errors.New("IA_DESTINO_SIN_PERMISO")}
 return false,errors.New("IA_DESTINO_NO_SE_PUEDE_INSPECCIONAR")
}
func iaIsTransientRename(err error)bool{
 if errors.Is(err,fs.ErrPermission){return true}
 if runtime.GOOS!="windows"{return false}
 var errno syscall.Errno
 if errors.As(err,&errno){
  return errno==syscall.Errno(5)||errno==syscall.Errno(32)||
         errno==syscall.Errno(33)
 }
 return false
}
func iaReadOwner(filename string)(ownerManifest,error){
 var o ownerManifest
 if !ordinary(filename){return o,errors.New("IA_IDENTIDAD_NO_VERIFICADA")}
 bytes,err:=os.ReadFile(filename)
 if err!=nil||len(bytes)>4096||json.Unmarshal(bytes,&o)!=nil||
  o.Schema!=ownerSchema||len(o.WorkerSHA)!=64||len(o.PluginSHA)!=64{
  return o,errors.New("IA_IDENTIDAD_NO_VERIFICADA")
 }
 if (o.VXACEHelperSHA=="")!=(o.VXACEPluginSHA=="") {
  return o,errors.New("IA_IDENTIDAD_NO_VERIFICADA")
 }
 if o.VXACEHelperSHA!=""&&(len(o.VXACEHelperSHA)!=64||len(o.VXACEPluginSHA)!=64||
  o.VXACEPluginBuild!=vxacePluginBuildID) {
  return o,errors.New("IA_IDENTIDAD_NO_VERIFICADA")
 }
 return o,nil
}
func iaCheckOwner(root string,pkg *packageReader)error{
 o,err:=iaReadOwner(filepath.Join(root,"owner-v1.json"))
 if err!=nil{return err}
 if o.WorkerSHA!=pkg.manifest.Files["IATraductora.exe"]||
  o.PluginSHA!=pkg.manifest.Files["IATraductora.js"]{
  return errors.New("IA_PROPIEDAD_O_VERSION_DIFERENTE")
 }
 return nil
}
func iaSortedFiles(pkg *packageReader)[]string{
 result:=make([]string,0,len(pkg.manifest.Files))
 for name:=range pkg.manifest.Files{
  if name!="IATraductora.js"{result=append(result,name)}
 }
 sort.Strings(result)
 return result
}
func iaCheckEngine(root string,pkg *packageReader)error{
 if err:=iaCheckOwner(root,pkg);err!=nil{return err}
 if helper:=pkg.manifest.Files["vxace-helper.exe"];helper!="" {
  owner,err:=iaReadOwner(filepath.Join(root,"owner-v1.json"))
  if err!=nil||owner.VXACEHelperSHA!=helper||
   owner.VXACEPluginSHA!=pkg.manifest.Files["vxace/TenshixgameVXACELive.rb"]||
   owner.VXACEPluginBuild!=vxacePluginBuildID {
   return errors.New("IA_VXACE_PROPIEDAD_NO_VERIFICADA")
  }
 }
 for _,name:=range iaSortedFiles(pkg){
  filename:=filepath.Join(root,".local","Rpg","engine",filepath.FromSlash(name))
  if !ordinary(filename){return errors.New("IA_MODELO_NO_VERIFICADO")}
  digest,err:=digestFile(filename)
  if err!=nil||digest!=pkg.manifest.Files[name]{
   return errors.New("IA_MODELO_SHA_NO_COINCIDE")
  }
 }
 return nil
}
func iaMakeSafeDirs(root,relative string)error{
 current:=root
 for _,component:=range strings.Split(filepath.Clean(relative),string(filepath.Separator)){
  if component==""||component=="."{continue}
  if component==".."||strings.Contains(component,":"){return errors.New("IA_RUTA_NO_PERMITIDA")}
  current=filepath.Join(current,component)
  if err:=os.Mkdir(current,0700);err!=nil&&!errors.Is(err,fs.ErrExist){
   if errors.Is(err,fs.ErrPermission){return errors.New("IA_ESCRITURA_BLOQUEADA")}
   return errors.New("IA_NO_SE_PUEDE_CREAR_DIRECTORIO")
  }
  stat,err:=os.Lstat(current)
  if err!=nil||!stat.IsDir()||stat.Mode()&os.ModeSymlink!=0{
   return errors.New("IA_DIRECTORIO_EXISTENTE_INSEGURO")
  }
 }
 return nil
}
func iaCopyFileOnlyIfMissing(from,to,want string)error{
 if ordinary(to){
  sum,err:=digestFile(to)
  if err!=nil||sum!=want{return errors.New("IA_ARCHIVO_EXISTENTE_NO_COINCIDE")}
  return nil
 }
 if present,err:=iaPathIsPresent(to);err!=nil{return err}else if present{
  return errors.New("IA_ARCHIVO_EXISTENTE_NO_COINCIDE")
 }
 input,err:=os.Open(from)
 if err!=nil{return errors.New("IA_ETAPA_ARCHIVO_INACCESIBLE")}
 defer input.Close()
 output,err:=os.OpenFile(to,os.O_WRONLY|os.O_CREATE|os.O_EXCL,0600)
 if err!=nil{
  if errors.Is(err,fs.ErrPermission){return errors.New("IA_ESCRITURA_BLOQUEADA")}
  if errors.Is(err,fs.ErrExist){return errors.New("IA_ARCHIVO_APARECIO_MIENTRAS_COPIABA")}
  return errors.New("IA_NO_SE_PUEDE_CREAR_ARCHIVO")
 }
 ok:=false
 defer func(){if !ok{_ =os.Remove(to)}}() // removes ONLY this attempt's newly created file
 h:=sha256.New()
 _,err=io.CopyBuffer(io.MultiWriter(output,h),input,make([]byte,256*1024))
 if err!=nil{_ =output.Close();return errors.New("IA_COPIA_MODELO_FALLIDA")}
 if err=output.Sync();err!=nil{_ =output.Close();return errors.New("IA_COPIA_MODELO_NO_SINCRONIZADA")}
 if err=output.Close();err!=nil{return errors.New("IA_COPIA_MODELO_NO_CERRADA")}
 if hex.EncodeToString(h.Sum(nil))!=want{return errors.New("IA_COPIA_SHA_NO_COINCIDE")}
 ok=true
 return nil
}
func iaCopyVerifiedStage(stage,folder string,pkg *packageReader)error{
 if err:=iaCheckEngine(stage,pkg);err!=nil{return err}
 present,err:=iaPathIsPresent(folder)
 if err!=nil{return err}
 if !present{
  if err=iaMkdirDestination(folder,0700);err!=nil{
   if errors.Is(err,fs.ErrPermission){return errors.New("IA_DESTINO_CREACION_DENEGADA")}
   if errors.Is(err,fs.ErrExist){return errors.New("IA_DESTINO_APARECIO")}
   return errors.New("IA_DESTINO_NO_SE_PUEDE_CREAR")
  }
 }else{
  if err=iaCheckOwner(folder,pkg);err!=nil{return errors.New("IA_DESTINO_AJENO_NO_MODIFICADO")}
  // A completed journal is never silently replaced or treated as new.
  if exists,_:=iaPathIsPresent(filepath.Join(folder,"install","receipt.json"));exists{
   return errors.New("IA_INSTALACION_EXISTENTE_REVISAR")
  }
 }
 // Journal of ownership FIRST: interrupted direct copies can resume, but
 // only when exact hashes of this version match and foreign files are intact.
 own:=filepath.Join(folder,"owner-v1.json")
 if !ordinary(own){
  bytes,err:=os.ReadFile(filepath.Join(stage,"owner-v1.json"))
  if err!=nil{return errors.New("IA_ETAPA_MARCADOR_INACCESIBLE")}
  if err=createNew(own,bytes);err!=nil{return errors.New("IA_NO_SE_PUEDE_REGISTRAR_PROPIEDAD")}
 }
 if err=iaCheckOwner(folder,pkg);err!=nil{return err}
 relative:=filepath.Join(".local","Rpg","engine")
 if err=iaMakeSafeDirs(folder,relative);err!=nil{return err}
 for _,name:=range iaSortedFiles(pkg){
  rel:=filepath.Join(relative,filepath.FromSlash(name))
  if err=iaMakeSafeDirs(folder,filepath.Dir(rel));err!=nil{return err}
  src:=filepath.Join(stage,rel);dest:=filepath.Join(folder,rel)
  if err=iaCopyFileOnlyIfMissing(src,dest,pkg.manifest.Files[name]);err!=nil{return err}
 }
 if helper:=pkg.manifest.Files["vxace-helper.exe"];helper!="" {
  owner,readErr:=iaReadOwner(own)
  if readErr!=nil{return readErr}
  wantPlugin:=pkg.manifest.Files["vxace/TenshixgameVXACELive.rb"]
  if owner.VXACEHelperSHA!=""&&(owner.VXACEHelperSHA!=helper||owner.VXACEPluginSHA!=wantPlugin) {
   return errors.New("IA_VXACE_PROPIEDAD_NO_VERIFICADA")
  }
  owner.Product="TENSHIXGAME-SERVIDOR"
  owner.VXACEHelperSHA=helper
  owner.VXACEPluginSHA=wantPlugin
  owner.VXACEPluginBuild=vxacePluginBuildID
  marker,_:=json.MarshalIndent(owner,"","  ")
  if err=writeAtomic(own,marker);err!=nil{return errors.New("IA_VXACE_MARCADOR_NO_PUBLICADO")}
 }
 if err=iaCheckEngine(folder,pkg);err!=nil{return err}
 if err=iaMakeSafeDirs(folder,"install");err!=nil{return err}
 return nil
}
func iaFindVerifiedStage(game string,pkg *packageReader)(string,error){
 dirs,err:=os.ReadDir(game)
 if err!=nil{return "",errors.New("IA_CARPETA_JUEGO_NO_SE_PUEDE_ENUMERAR")}
 stages:=[]string{}
 for _,entry:=range dirs{
  if !entry.IsDir()||!strings.HasPrefix(entry.Name(),".ia-traductora-stage-"){continue}
  name:=filepath.Join(game,entry.Name())
  stat,err:=os.Lstat(name)
  if err!=nil||stat.Mode()&os.ModeSymlink!=0{continue}
  if iaCheckEngine(name,pkg)==nil{stages=append(stages,name)}
 }
 if len(stages)>1{return "",errors.New("IA_VARIAS_ETAPAS_VALIDAS_REVISAR")}
 if len(stages)==1{return stages[0],nil}
 return "",nil
}
func iaPrepareStage(game string,pkg *packageReader)(string,error){
 stage,err:=os.MkdirTemp(game,".ia-traductora-stage-")
 if err!=nil{
  if errors.Is(err,fs.ErrPermission){return "",errors.New("IA_JUEGO_ESCRITURA_DENEGADA")}
  return "",errors.New("IA_NO_SE_PUEDE_CREAR_ETAPA")
 }
 complete:=false
 defer func(){if !complete{_ =os.RemoveAll(stage)}}()
 engine:=filepath.Join(".local","Rpg","engine")
 if err=iaMakeSafeDirs(stage,engine);err!=nil{return "",err}
 for _,name:=range iaSortedFiles(pkg){
  zipFile:=pkg.files[name]
  if zipFile==nil{return "",errors.New("IA_PAQUETE_INCOMPLETO")}
  rel:=filepath.Join(engine,filepath.FromSlash(name))
  if err=iaMakeSafeDirs(stage,filepath.Dir(rel));err!=nil{return "",err}
  output,err:=os.OpenFile(filepath.Join(stage,rel),os.O_CREATE|os.O_EXCL|os.O_WRONLY,0600)
  if err!=nil{return "",errors.New("IA_ETAPA_ESCRITURA_BLOQUEADA")}
  input,err:=zipFile.Open()
  if err!=nil{_ =output.Close();return "",errors.New("IA_PAQUETE_ARCHIVO_NO_LEIBLE")}
  h:=sha256.New()
  _,copyError:=io.CopyBuffer(io.MultiWriter(output,h),io.LimitReader(input,maxArchive+1),make([]byte,256*1024))
  _=input.Close()
  syncError:=output.Sync()
  closeError:=output.Close()
  if copyError!=nil||syncError!=nil||closeError!=nil||hex.EncodeToString(h.Sum(nil))!=pkg.manifest.Files[name]{
   return "",errors.New("IA_ETAPA_MODELO_SHA_NO_COINCIDE")
  }
 }
 own:=ownerManifest{Schema:ownerSchema,WorkerSHA:pkg.manifest.Files["IATraductora.exe"],
  PluginSHA:pkg.manifest.Files["IATraductora.js"],Product:"TENSHIXGAME-SERVIDOR",
  VXACEHelperSHA:pkg.manifest.Files["vxace-helper.exe"],
  VXACEPluginSHA:pkg.manifest.Files["vxace/TenshixgameVXACELive.rb"]}
 if own.VXACEHelperSHA!=""{own.VXACEPluginBuild=vxacePluginBuildID}
 bytes,_:=json.MarshalIndent(own,"","  ")
 if err=createNew(filepath.Join(stage,"owner-v1.json"),bytes);err!=nil{return "",errors.New("IA_ETAPA_NO_SE_PUEDE_MARCAR")}
 if err=iaMakeSafeDirs(stage,"install");err!=nil{return "",err}
 if err=iaCheckEngine(stage,pkg);err!=nil{return "",err}
 complete=true
 return stage,nil
}
func iaPublishStage(stage,folder string,pkg *packageReader)error{
 for attempt:=0;attempt<4;attempt++{
  present,err:=iaPathIsPresent(folder)
  if err!=nil{return err}
  if present{return errors.New("IA_DESTINO_EXISTENTE_NO_SOBRESCRITO")}
  err=iaRenameStage(stage,folder)
  if err==nil{return iaCheckEngine(folder,pkg)}
  if !iaIsTransientRename(err){return errors.New("IA_PUBLICACION_CAMBIO_NOMBRE_FALLIDO")}
  if attempt<3{iaRetrySleep(time.Duration(100*(1<<attempt))*time.Millisecond)}
 }
 // Rename can be denied by Windows file handles even if the directory is writable.
 // Use a verified, exclusive, create-only copy rather than asking for admin.
 if err:=iaCopyVerifiedStage(stage,folder,pkg);err!=nil{return err}
 _=os.RemoveAll(stage) // only the verified, app-owned staging directory; never user files
 return nil
}
func iaPrepareAndPublishSidecar(game string,pkg *packageReader)(string,error){
 folder:=filepath.Join(game,brandFolder)
 present,err:=iaPathIsPresent(folder)
 if err!=nil{return "",err}
 if present {
  if err=iaCheckOwner(folder,pkg);err!=nil{return "",errors.New("IA_DESTINO_AJENO_NO_MODIFICADO")}
  if err=iaCheckEngine(folder,pkg);err==nil{
   if receipt,_:=iaPathIsPresent(filepath.Join(folder,"install","receipt.json"));receipt{
    return "",errors.New("IA_INSTALACION_EXISTENTE_REVISAR")
   }
   if err=iaMakeSafeDirs(folder,"install");err!=nil{return "",err}
   return folder,nil
  }
  // May be our own interrupted fallback: no overwrites, only missing files.
 }
 stage,err:=iaFindVerifiedStage(game,pkg)
 if err!=nil{return "",err}
 if stage==""{
  stage,err=iaPrepareStage(game,pkg)
  if err!=nil{return "",err}
 }
 if present{
  if err=iaCopyVerifiedStage(stage,folder,pkg);err!=nil{
   return "",err // original stage and files survive for a safe retry
  }
  _=os.RemoveAll(stage)
  return folder,nil
 }
 if err=iaPublishStage(stage,folder,pkg);err!=nil{
  return "",err // verified staging data is retained for repeat attempt
 }
 return folder,nil
}
