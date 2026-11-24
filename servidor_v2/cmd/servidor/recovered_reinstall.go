package main

// A recovered game retains our signed sidecar and original receipt but its
// plugins.js is byte-identical to the game's original. Reinstalling must
// never overwrite a foreign file or pretend it succeeded.
import(
  "encoding/json"
  "errors"
  "os"
  "path/filepath"
)

func iaReinstallAfterRecovery(root,content string,current,desired []byte,pkg *packageReader)error{
 sidecar:=filepath.Join(root,brandFolder)
 registryFile:=filepath.Join(content,"js","plugins.js")
 backupFile:=filepath.Join(sidecar,"install","original-plugins.js")
 ownerFile:=filepath.Join(sidecar,"owner-v1.json")
 receiptFile:=filepath.Join(sidecar,"install","receipt.json")
 pluginFile:=filepath.Join(content,"js","plugins",pluginName+".js")
 workerFile:=filepath.Join(sidecar,".local","Rpg","engine","IATraductora.exe")
 if !ordinary(backupFile)||!ordinary(ownerFile)||!ordinary(receiptFile)||
    !ordinary(pluginFile)||!ordinary(workerFile){
  return errors.New("IA_REINSTALACION_PROPIEDAD_NO_VERIFICADA")
 }
 ownerData,e:=os.ReadFile(ownerFile)
 if e!=nil||len(ownerData)>2048{return errors.New("IA_REINSTALACION_PROPIEDAD_NO_VERIFICADA")}
 receiptData,e:=os.ReadFile(receiptFile)
 if e!=nil||len(receiptData)>4096{return errors.New("IA_REINSTALACION_RECIBO_INVALIDO")}
 backup,e:=os.ReadFile(backupFile)
 if e!=nil||len(backup)>4*1024*1024{return errors.New("IA_REINSTALACION_BACKUP_INVALIDO")}
 var owner ownerManifest
 var receipt installReceipt
 if json.Unmarshal(ownerData,&owner)!=nil||owner.Schema!=ownerSchema||
    json.Unmarshal(receiptData,&receipt)!=nil||
    receipt.Schema!="ia-traductora-install-v1"||
    receipt.Status!="INSTALLED"||owner.PluginSHA!=receipt.PluginSHA{
  return errors.New("IA_REINSTALACION_PROPIEDAD_NO_VERIFICADA")
 }
 if hash(current)!=receipt.BeforeSHA||hash(backup)!=receipt.BeforeSHA||
    hash(desired)!=receipt.AfterSHA{
  return errors.New("IA_REINSTALACION_REGISTRO_MODIFICADO")
 }
 if hashMustRead(pluginFile)!=owner.PluginSHA{
  return errors.New("IA_REINSTALACION_COMPLEMENTO_MODIFICADO")
 }
 workerSha,e:=digestFile(workerFile)
 if e!=nil||workerSha!=owner.WorkerSHA{
  return errors.New("IA_REINSTALACION_MOTOR_MODIFICADO")
 }
 // Restore only the exactly known installed registry and then use the normal
 // verified in-place package upgrade. No game assets, saves or models deleted.
 if e=writeAtomic(registryFile,desired);e!=nil{
  return errors.New("IA_REINSTALACION_REGISTRO_BLOQUEADO")
 }
 restoreOriginal:=func()error{
  if e=writeAtomic(registryFile,current);e!=nil{
   return errors.New("IA_REINSTALACION_RESTAURAR_REGISTRO_MANUAL")
  }
  return nil
 }
 if e=iaUpgradeOwnPlugin(root,content,desired,pkg);e!=nil{
  if restore:=restoreOriginal();restore!=nil{return restore}
  return e
 }
 if e=verifiedNewInstallation(root,content,desired);e!=nil{
  if restore:=restoreOriginal();restore!=nil{return restore}
  return errors.New("IA_REINSTALACION_POSTCONDICION_FALLIDA")
 }
 return nil
}
