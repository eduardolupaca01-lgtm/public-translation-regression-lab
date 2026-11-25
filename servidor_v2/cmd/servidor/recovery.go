package main

// Recuperacion MV: revierte exclusivamente el registro que esta version
// modifico, siempre que journal, respaldo y bytes del registro coincidan.
// No elimina complementos, modelos, partidas, archivos ajenos ni el worker.
import(
  "encoding/json"
  "errors"
  "os"
  "path/filepath"
)

func RecoverGame(gameEXE string)error{
 root,content,err:=detectGame(gameEXE)
 if err!=nil{
  if packed,ok:=halvaRootFromDetection(gameEXE,err);ok{return recoverHalva(packed)}
  return err
 }
 sidecar:=filepath.Join(root,brandFolder)
 ownerFile:=filepath.Join(sidecar,"owner-v1.json")
 receiptFile:=filepath.Join(sidecar,"install","receipt.json")
 backupFile:=filepath.Join(sidecar,"install","original-plugins.js")
 registryFile:=filepath.Join(content,"js","plugins.js")
 if !ordinary(ownerFile)||!ordinary(receiptFile)||!ordinary(backupFile)||!ordinary(registryFile){
  return errors.New("IA_RECUPERACION_ESTADO_NO_VERIFICADO")
 }
 ownerRaw,e:=os.ReadFile(ownerFile)
 if e!=nil||len(ownerRaw)>2048{return errors.New("IA_RECUPERACION_ESTADO_NO_VERIFICADO")}
 var owner ownerManifest
 if json.Unmarshal(ownerRaw,&owner)!=nil||owner.Schema!=ownerSchema{
  return errors.New("IA_RECUPERACION_ESTADO_NO_VERIFICADO")
 }
 receiptRaw,e:=os.ReadFile(receiptFile)
 if e!=nil||len(receiptRaw)>4096{return errors.New("IA_RECUPERACION_ESTADO_NO_VERIFICADO")}
 var receipt installReceipt
 if json.Unmarshal(receiptRaw,&receipt)!=nil||
   receipt.Schema!="ia-traductora-install-v1"||receipt.Status!="INSTALLED"||
   receipt.PluginSHA!=owner.PluginSHA{
  return errors.New("IA_RECUPERACION_ESTADO_NO_VERIFICADO")
 }
 original,e:=os.ReadFile(backupFile)
 if e!=nil||len(original)>4*1024*1024||hash(original)!=receipt.BeforeSHA{
  return errors.New("IA_RECUPERACION_RESPALDO_ALTERADO")
 }
 current,e:=os.ReadFile(registryFile)
 if e!=nil||len(current)>4*1024*1024{return errors.New("IA_RECUPERACION_REGISTRO_NO_LEIBLE")}
 // Cuando el registro ya es el original, la recuperacion es idempotente.
 if hash(current)==receipt.BeforeSHA{return nil}
 if hash(current)!=receipt.AfterSHA{
  return errors.New("IA_RECUPERACION_REGISTRO_CAMBIADO")
 }
 // Nunca sobrescribir una copia existente y nunca restaurar sin snapshot.
 if e=iaMakeSafeDirs(sidecar,filepath.Join("install","recovery"));e!=nil{return e}
 snapshot:=filepath.Join(sidecar,"install","recovery",receipt.AfterSHA+".plugins.js")
 if ordinary(snapshot){
  if hashMustRead(snapshot)!=receipt.AfterSHA{return errors.New("IA_RECUPERACION_COPIA_AJENA")}
 }else{
  if e=createNew(snapshot,current);e!=nil{return errors.New("IA_RECUPERACION_NO_PUDO_RESPALDAR")}
 }
 if e=writeAtomic(registryFile,original);e!=nil{
  return errors.New("IA_RECUPERACION_NO_PUDO_PUBLICAR")
 }
 if hashMustRead(registryFile)!=receipt.BeforeSHA{
  return errors.New("IA_RECUPERACION_POSTCONDICION_NO_VERIFICADA")
 }
 return nil
}
