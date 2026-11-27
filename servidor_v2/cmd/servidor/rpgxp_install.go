package main

// Experimental loose XP installation. The public selector stays blocked
// until the actual RGSS1 runtime is independently validated.
import (
 "bytes"
 "encoding/hex"
 "encoding/json"
 "errors"
 "flag"
 "fmt"
 "io"
 "os"
 "os/exec"
 "path/filepath"
 "runtime"
 "strconv"
 "strings"
)
const (
 xpPluginAsset="rpgxp/IATraductoraXP.rb"
 xpLauncherAsset="rpgxp-launcher.exe"
 xpLabBuild="RPGXP-RGSS1-R43-LAB-2"
)
type xpReceipt struct {
 Schema string `json:"schema"`
 Build string `json:"build"`
 Status string `json:"status"`
 Target string `json:"target_rel"`
 Before string `json:"before_sha256"`
 After string `json:"after_sha256"`
 Plugin string `json:"plugin_sha256"`
 Worker string `json:"worker_sha256"`
 Launcher string `json:"launcher_sha256"`
}
func xpError(code string)error{return errors.New("IA_RPGXP_"+code)}
func xpSHA(s string)bool{b,e:=hex.DecodeString(s);return e==nil&&len(b)==32&&s==strings.ToLower(s)}
func xpRead(file string,limit int64)([]byte,error){
 if e:=vxaceNoSymlinkAncestors(filepath.Dir(file));e!=nil{return nil,e}
 if !ordinary(file){return nil,xpError("ARCHIVO_NO_VERIFICADO")}
 f,e:=os.Open(file);if e!=nil{return nil,e};defer f.Close()
 b,e:=io.ReadAll(io.LimitReader(f,limit+1));if e!=nil||len(b)==0||int64(len(b))>limit{return nil,xpError("TAMANO_INVALIDO")}
 return b,nil
}
func xpTarget(exe string)(root,target string,e error){
 matched,e:=detectRPGXP(exe);if e!=nil{return "","",e};if !matched{return "","",xpError("RECURSOS_NO_VERIFICADOS")}
 root,e=filepath.Abs(filepath.Dir(exe));if e!=nil{return}
 if engineAt(root)!=""||engineAt(filepath.Join(root,"www"))!=""{return "","",xpError("RUTAS_AMBIGUAS")}
 dir,e:=vxaceDirectoryChild(root,"Data");if e!=nil{return "","",e}
 target,e=vxaceOrdinaryChild(dir,"Scripts.rxdata",xpMaxArchive);return
}
func xpPaths(root string)(sidecar,engine,journal,backup,receipt string){
 sidecar=filepath.Join(root,brandFolder)
 engine=filepath.Join(sidecar,".local","Rpg","engine")
 journal=filepath.Join(sidecar,"install","rpgxp")
 backup=filepath.Join(journal,"Scripts.original.rxdata")
 receipt=filepath.Join(journal,"receipt.json")
 return
}
func xpLock(dir string)(func(),error){
 if e:=vxaceNoSymlinkAncestors(dir);e!=nil{return nil,e}
 path:=filepath.Join(dir,"operation.lock")
 if e:=os.Mkdir(path,0700);e!=nil{return nil,xpError("OPERACION_ACTIVA_O_PENDIENTE")}
 return func(){_ = os.Remove(path)},nil
}
func xpNoSession(engine string)error{
 _,e:=os.Lstat(filepath.Join(filepath.Dir(engine),"rpgxp-session.txt"))
 if !os.IsNotExist(e){return xpError("SESION_ACTIVA_O_PENDIENTE")}
 return nil
}
func xpHashFile(file,want string)error{
 if !xpSHA(want)||vxaceNoSymlinkAncestors(filepath.Dir(file))!=nil||!ordinary(file){return xpError("SHA_NO_VERIFICADO")}
 digest,e:=digestFile(file);if e!=nil||digest!=want{return xpError("SHA_NO_COINCIDE")}
 return nil
}
func xpReadReceipt(file string)(xpReceipt,bool,error){
 var r xpReceipt
 if _,e:=os.Lstat(file);os.IsNotExist(e){return r,false,nil}else if e!=nil{return r,false,e}
 b,e:=xpRead(file,8192)
 if e!=nil||json.Unmarshal(b,&r)!=nil||r.Schema!="ia-rpgxp-install-v1"||r.Build!=xpLabBuild||
  r.Target!="Data/Scripts.rxdata"||!xpSHA(r.Before)||!xpSHA(r.After)||r.Before==r.After||
  !xpSHA(r.Plugin)||!xpSHA(r.Worker)||!xpSHA(r.Launcher)||
  (r.Status!="PREPARED"&&r.Status!="INSTALLED"&&r.Status!="RESTORED"){
  return r,false,xpError("RECIBO_INVALIDO")
 }
 return r,true,nil
}
func xpRecord(file string,r xpReceipt)error{
 b,e:=json.MarshalIndent(r,"","  ");if e!=nil{return e}
 if _,e=os.Lstat(file);os.IsNotExist(e){return createNew(file,b)}
 if e!=nil||!ordinary(file){return xpError("RECIBO_INVALIDO")}
 return writeAtomic(file,b)
}
func xpVerifiedAssets(root string,r xpReceipt)error{
 sidecar,engine,_,_,_:=xpPaths(root)
 if vxaceNoSymlinkAncestors(sidecar)!=nil{return xpError("RUTA_INSEGURA")}
 o,e:=iaReadOwner(filepath.Join(sidecar,"owner-v1.json"))
 if e!=nil||o.Product!="SERVIDOR-IA-TRADUCTORA"||o.WorkerSHA!=r.Worker{return xpError("PROPIEDAD_NO_VERIFICADA")}
 for _,item:=range []struct{name,sha string}{{xpPluginAsset,r.Plugin},{xpLauncherAsset,r.Launcher},{"IATraductora.exe",r.Worker}}{
  if e=xpHashFile(filepath.Join(engine,filepath.FromSlash(item.name)),item.sha);e!=nil{return e}
 }
 if !vxaceAMD64PE(filepath.Join(engine,xpLauncherAsset)){return xpError("LAUNCHER_NO_VERIFICADO")}
 return nil
}
func xpInstallLab(exe string,pkg *packageReader)error{
 root,target,e:=xpTarget(exe);if e!=nil{return e}
 if pkg==nil||pkg.files[xpPluginAsset]==nil||pkg.files[xpLauncherAsset]==nil{return xpError("PAQUETE_INCOMPLETO")}
 plugin,e:=readZip(pkg.files[xpPluginAsset],1024*1024)
 if e!=nil||hash(plugin)!=pkg.manifest.Files[xpPluginAsset]||!bytes.Contains(plugin,[]byte(xpLabBuild)){return xpError("PLUGIN_NO_VERIFICADO")}
 sidecar,engine,journal,backup,receiptFile:=xpPaths(root)
 // Inspect and validate an original archive before extracting a new sidecar.
 current,e:=xpRead(target,xpMaxArchive);if e!=nil{return e}
 if _,e=os.Lstat(receiptFile);os.IsNotExist(e){
  if _,e=xpPatchScripts(current,plugin);e!=nil{return e}
 }
 if _,e=iaPrepareAndPublishSidecar(root,pkg);e!=nil{return e}
 if e=iaCheckEngine(sidecar,pkg);e!=nil{return e}
 if e=iaMakeSafeDirs(sidecar,filepath.Join("install","rpgxp"));e!=nil{return e}
 unlock,e:=xpLock(journal);if e!=nil{return e};defer unlock()
 if e=xpNoSession(engine);e!=nil{return e}
 current,e=xpRead(target,xpMaxArchive);if e!=nil{return e}
 currentSHA:=hash(current)
 r,exists,e:=xpReadReceipt(receiptFile);if e!=nil{return e}
 original:=current
 if exists{
  if r.Plugin!=hash(plugin)||r.Worker!=pkg.manifest.Files["IATraductora.exe"]||r.Launcher!=pkg.manifest.Files[xpLauncherAsset]{return xpError("VERSION_DISTINTA")}
  if currentSHA!=r.Before&&currentSHA!=r.After{return xpError("RECURSO_MODIFICADO")}
  if r.Status=="RESTORED"&&currentSHA!=r.Before{return xpError("RECURSO_MODIFICADO")}
  if r.Status=="INSTALLED"&&currentSHA!=r.After{return xpError("RECURSO_MODIFICADO")}
  original,e=xpRead(backup,xpMaxArchive);if e!=nil||hash(original)!=r.Before{return xpError("RESPALDO_NO_VERIFICADO")}
 }
 patched,e:=xpPatchScripts(original,plugin);if e!=nil{return e}
 expected:=xpReceipt{"ia-rpgxp-install-v1",xpLabBuild,"PREPARED","Data/Scripts.rxdata",hash(original),hash(patched),hash(plugin),pkg.manifest.Files["IATraductora.exe"],pkg.manifest.Files[xpLauncherAsset]}
 if e=xpVerifiedAssets(root,expected);e!=nil{return e}
 if exists&&(r.Before!=expected.Before||r.After!=expected.After){return xpError("RECIBO_NO_COINCIDE")}
 if exists&&currentSHA==expected.After{
  expected.Status="INSTALLED";return xpRecord(receiptFile,expected)
 }
 if currentSHA!=expected.Before{return xpError("RECURSO_MODIFICADO")}
 if _,e=os.Lstat(backup);os.IsNotExist(e){
  if e=vxaceCopyFileNew(target,backup);e!=nil{return e}
 }else if e!=nil{return e}
 if e=xpHashFile(backup,expected.Before);e!=nil{return e}
 // Stage in the owned journal; exact original and both digests are durable
 // before the only game resource replacement.
 f,e:=os.CreateTemp(journal,"candidate-");if e!=nil{return e}
 candidate:=f.Name();defer os.Remove(candidate)
 if _,e=f.Write(patched);e!=nil{f.Close();return e}
 if e=f.Sync();e!=nil{f.Close();return e};if e=f.Close();e!=nil{return e}
 if e=xpHashFile(candidate,expected.After);e!=nil{return e}
 if e=xpRecord(receiptFile,expected);e!=nil{return e}
 if e=vxaceAtomicReplaceFrom(candidate,target,expected.After,expected.Before);e!=nil{return e}
 if e=xpHashFile(target,expected.After);e!=nil{return e}
 expected.Status="INSTALLED"
 return xpRecord(receiptFile,expected)
}
func xpRecoverLab(exe string)error{
 root,target,e:=xpTarget(exe);if e!=nil{return e}
 _,engine,journal,backup,receiptFile:=xpPaths(root)
 unlock,e:=xpLock(journal);if e!=nil{return e};defer unlock()
 if e=xpNoSession(engine);e!=nil{return e}
 r,ok,e:=xpReadReceipt(receiptFile);if e!=nil||!ok{return xpError("RECIBO_INVALIDO")}
 if e=xpHashFile(backup,r.Before);e!=nil{return e}
 current,e:=xpRead(target,xpMaxArchive);if e!=nil{return e}
 h:=hash(current)
 if h!=r.Before{
  if h!=r.After||r.Status=="RESTORED"{return xpError("RECURSO_MODIFICADO_NO_RESTAURADO")}
  if e=vxaceAtomicReplaceFrom(backup,target,r.Before,r.After);e!=nil{return e}
 }
 if e=xpHashFile(target,r.Before);e!=nil{return e}
 r.Status="RESTORED";return xpRecord(receiptFile,r)
}
func xpLaunch(parent int)error{
 if runtime.GOOS!="windows"||parent<=0{return xpError("PARENT_INVALIDO")}
 current,e:=os.Executable();if e!=nil{return e}
 if !strings.EqualFold(filepath.Base(current),xpLauncherAsset){return xpError("LAUNCHER_RUTA_INVALIDA")}
 root:=filepath.Dir(current)
 for _,name:=range []string{"engine","Rpg",".local",brandFolder}{
  if !strings.EqualFold(filepath.Base(root),name){return xpError("LAUNCHER_RUTA_INVALIDA")}
  root=filepath.Dir(root)
 }
 root,target,e:=xpTarget(filepath.Join(root,"Game.exe"));if e!=nil{return e}
 _,engine,journal,backup,receiptFile:=xpPaths(root)
 if !strings.EqualFold(filepath.Clean(current),filepath.Join(engine,xpLauncherAsset)){return xpError("LAUNCHER_RUTA_INVALIDA")}
 unlock,e:=xpLock(journal);if e!=nil{return e};defer unlock()
 if e=xpNoSession(engine);e!=nil{return e}
 r,ok,e:=xpReadReceipt(receiptFile);if e!=nil||!ok||r.Status!="INSTALLED"{return xpError("RECIBO_INVALIDO")}
 if e=xpVerifiedAssets(root,r);e!=nil{return e}
 if e=xpHashFile(target,r.After);e!=nil{return e}
 if e=xpHashFile(backup,r.Before);e!=nil{return e}
 // The frozen worker monitors the original game process handle. Keep
 // this launcher and the exclusive operation lock until the worker exits.
 cmd:=exec.Command(filepath.Join(engine,"IATraductora.exe"),"--game-root",root,"--rpgxp-lab","--parent-pid",strconv.Itoa(parent),
  "--diagnostic-file",filepath.Join(filepath.Dir(engine),"rpgxp-startup-"+strconv.Itoa(parent)+".json"))
 cmd.Dir=root
 return cmd.Run()
}
func xpLabCommand(install,recover bool,parent int,game,payload string)error{
 if flag.NArg()!=0{return xpError("ARGUMENTOS_INVALIDOS")}
 allowed:=map[string]bool{}
 if parent!=0&&!install&&!recover{allowed["xp-launch-parent"]=true}else if parent==0&&install!=recover&&game!=""{
  allowed["game"]=true
  if install{allowed["xp-lab-install"]=true;allowed["package"]=true}else{allowed["xp-lab-recover"]=true}
 }else{return xpError("ARGUMENTOS_INVALIDOS")}
 valid:=true;flag.Visit(func(f *flag.Flag){if !allowed[f.Name]{valid=false}})
 if !valid{return xpError("ARGUMENTOS_INVALIDOS")}
 if parent!=0{return xpLaunch(parent)}
 if recover{return xpRecoverLab(game)}
 if payload==""{var e error;payload,e=os.Executable();if e!=nil{return e}}
 pkg,e:=readPackage(payload);if e!=nil{return e};defer pkg.Close()
 if e=xpInstallLab(game,pkg);e!=nil{return e}
 fmt.Println("IA_RPGXP_LAB_INSTALADO_VERIFICADO")
 return nil
}
