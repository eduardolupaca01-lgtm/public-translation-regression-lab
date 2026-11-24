package main

// Verified in-place update of ONLY our own MV worker and plugin. Models that
// differ from the approved OPUS weights are never silently replaced.
import (
 "bytes"
 "encoding/json"
 "errors"
 "os"
 "path/filepath"
)

func iaUpgradeOwnPlugin(root,content string,registry []byte,pkg *packageReader)error{
 if e:=verifiedNewInstallation(root,content,registry);e!=nil{return e}
 sidecar:=filepath.Join(root,brandFolder)
 markerFile:=filepath.Join(sidecar,"owner-v1.json")
 receiptFile:=filepath.Join(sidecar,"install","receipt.json")
 pluginFile:=filepath.Join(content,"js","plugins",pluginName+".js")
 workerFile:=filepath.Join(sidecar,".local","Rpg","engine","IATraductora.exe")
 markerRaw,e:=os.ReadFile(markerFile);if e!=nil{return errors.New("IA_ACTUALIZACION_MARCADOR_INACCESIBLE")}
 receiptRaw,e:=os.ReadFile(receiptFile);if e!=nil{return errors.New("IA_ACTUALIZACION_RECIBO_INACCESIBLE")}
 var owner ownerManifest
 var receipt installReceipt
 if json.Unmarshal(markerRaw,&owner)!=nil||json.Unmarshal(receiptRaw,&receipt)!=nil{
  return errors.New("IA_ACTUALIZACION_DATOS_INVALIDOS")
 }
 // The new package may have different neural weights: reject those safely.
 for _,name:=range iaSortedFiles(pkg){
  if name=="IATraductora.exe"{continue}
  file:=filepath.Join(sidecar,".local","Rpg","engine",filepath.FromSlash(name))
  if !ordinary(file){return errors.New("IA_ACTUALIZACION_MODELO_FALTANTE")}
  sha,err:=digestFile(file)
  if err!=nil||sha!=pkg.manifest.Files[name]{
   return errors.New("IA_MOTOR_VERSION_DISTINTA_NO_ACTUALIZADA")
  }
 }
 wantWorker:=pkg.manifest.Files["IATraductora.exe"]
 wantPlugin:=pkg.manifest.Files["IATraductora.js"]
 changeWorker:=wantWorker!=owner.WorkerSHA
 changePlugin:=wantPlugin!=owner.PluginSHA
 if !changeWorker&&!changePlugin{return nil}

 var beforePlugin,afterPlugin,beforeWorker,afterWorker []byte
 if changePlugin{
  beforePlugin,e=os.ReadFile(pluginFile)
  if e!=nil||hash(beforePlugin)!=owner.PluginSHA{return errors.New("IA_ACTUALIZACION_PLUGIN_MODIFICADO")}
  afterPlugin,e=readZip(pkg.files["IATraductora.js"],1024*1024)
  if e!=nil||hash(afterPlugin)!=wantPlugin||
    !bytes.Contains(afterPlugin,[]byte("◆ IA Traductora · F10")){
   return errors.New("IA_ACTUALIZACION_PLUGIN_INVALIDO")
  }
 }
 if changeWorker{
  beforeWorker,e=os.ReadFile(workerFile)
  if e!=nil||hash(beforeWorker)!=owner.WorkerSHA{return errors.New("IA_ACTUALIZACION_MOTOR_MODIFICADO")}
  afterWorker,e=readZip(pkg.files["IATraductora.exe"],120*1024*1024)
  if e!=nil||hash(afterWorker)!=wantWorker{return errors.New("IA_ACTUALIZACION_MOTOR_INVALIDO")}
 }
 if e=iaMakeSafeDirs(sidecar,filepath.Join("install","updates"));e!=nil{return e}
 updates:=filepath.Join(sidecar,"install","updates")
 backup:=func(name string,data []byte,want string)error{
  file:=filepath.Join(updates,name)
  if ordinary(file){
   if hashMustRead(file)!=want{return errors.New("IA_ACTUALIZACION_BACKUP_NO_COINCIDE")}
   return nil
  }
  if e:=createNew(file,data);e!=nil{return errors.New("IA_ACTUALIZACION_BACKUP_BLOQUEADO")}
  return nil
 }
 if changePlugin{
  if e=backup(owner.PluginSHA+".js",beforePlugin,owner.PluginSHA);e!=nil{return e}
 }
 if changeWorker{
  if e=backup(owner.WorkerSHA+".exe",beforeWorker,owner.WorkerSHA);e!=nil{return e}
 }
 owner.PluginSHA=wantPlugin;owner.WorkerSHA=wantWorker
 receipt.PluginSHA=wantPlugin
 markerNew,_:=json.MarshalIndent(owner,"","  ")
 receiptNew,_:=json.MarshalIndent(receipt,"","  ")
 // Restoring both program-owned files + metadata is mandatory on failure.
 restore:=func()error{
  var a,b,c,d error
  if changeWorker{a=writeAtomic(workerFile,beforeWorker)}
  if changePlugin{b=writeAtomic(pluginFile,beforePlugin)}
  c=writeAtomic(markerFile,markerRaw)
  d=writeAtomic(receiptFile,receiptRaw)
  if a!=nil||b!=nil||c!=nil||d!=nil{return errors.New("IA_ACTUALIZACION_RESTAURAR_DESDE_BACKUP")}
  return nil
 }
 if changeWorker{
  if e=writeAtomic(workerFile,afterWorker);e!=nil{return errors.New("IA_ACTUALIZACION_MOTOR_BLOQUEADO")}
 }
 if changePlugin{
  if e=writeAtomic(pluginFile,afterPlugin);e!=nil{
   if rollback:=restore();rollback!=nil{return rollback}
   return errors.New("IA_ACTUALIZACION_PLUGIN_BLOQUEADO")
  }
 }
 if e=writeAtomic(markerFile,markerNew);e!=nil{
  if rollback:=restore();rollback!=nil{return rollback}
  return errors.New("IA_ACTUALIZACION_MARCADOR_BLOQUEADO")
 }
 if e=writeAtomic(receiptFile,receiptNew);e!=nil{
  if rollback:=restore();rollback!=nil{return rollback}
  return errors.New("IA_ACTUALIZACION_RECIBO_BLOQUEADO")
 }
 if e=verifiedNewInstallation(root,content,registry);e!=nil{
  if rollback:=restore();rollback!=nil{return rollback}
  return errors.New("IA_ACTUALIZACION_NO_VERIFICADA")
 }
 return nil
}
