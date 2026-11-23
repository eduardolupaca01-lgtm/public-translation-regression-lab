package main

// Migración verificable desde una instalación anterior, sólo dentro de
// una COPIA cerrada del juego. No ejecuta ni importa el motor anterior.
import(
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "io"
 "os"
 "path/filepath"
 "strings"
)

type oldOwner struct{
 Schema string `json:"schema"`
 Product string `json:"product"`
 WorkerSHA string `json:"worker_sha256"`
}
type oldPluginJournal struct{
 Schema string `json:"schema"`
 Engine string `json:"engine"`
 Status string `json:"status"`
 OriginalSHA string `json:"original_plugins_sha256"`
 UpdatedSHA string `json:"updated_plugins_sha256"`
 PluginSHA string `json:"plugin_sha256"`
}
type migrationPlan struct{
 OldRoot string
 OldPlugin string
 OriginalRegistry []byte
 PreviousRegistry []byte
 PreviousPlugin []byte
}
func verifiedOldMigration(game,content string,current []byte)(*migrationPlan,error){
 sidecar:=filepath.Join(game,"Tenshixgame-IA")
 st,err:=os.Lstat(sidecar)
 if err!=nil||!st.IsDir()||st.Mode()&os.ModeSymlink!=0{
  return nil,errors.New("IA_MIGRACION_NO_HAY_ORIGEN_VERIFICABLE")
 }
 ownerFile:=filepath.Join(sidecar,"portable-owner-v1.json")
 if !ordinary(ownerFile){return nil,errors.New("IA_MIGRACION_MARCADOR_FALTANTE")}
 var owner oldOwner
 raw,e:=os.ReadFile(ownerFile)
 if e!=nil||len(raw)>2048||json.Unmarshal(raw,&owner)!=nil||
 owner.Schema!="tenshixgame-rpg-portable-owner-v1"||owner.Product!="TENSHIXGAME-RPG"||
 len(owner.WorkerSHA)!=64{
  return nil,errors.New("IA_MIGRACION_MARCADOR_INVALIDO")
 }
 worker:=filepath.Join(sidecar,".local","TENSHIXGAME-RPG","engine","engine","TenshixgameAI.exe")
 if !ordinary(worker){return nil,errors.New("IA_MIGRACION_MOTOR_ORIGINAL_AUSENTE")}
 sum,err:=digestFile(worker)
 if err!=nil||sum!=owner.WorkerSHA{return nil,errors.New("IA_MIGRACION_FIRMA_ORIGINAL_INVALIDA")}
 oldPlugin:=filepath.Join(content,"js","plugins","TenshixgameRPGLive.js")
 if !ordinary(oldPlugin){return nil,errors.New("IA_MIGRACION_COMPLEMENTO_ANTIGUO_NO_VERIFICADO")}
 oldJS,err:=os.ReadFile(oldPlugin)
 if err!=nil||len(oldJS)>2*1024*1024{return nil,errors.New("IA_MIGRACION_PLUGIN_INVALIDO")}
 workspaces:=filepath.Join(sidecar,".local","TENSHIXGAME-RPG","game-workspaces")
 dirs,err:=os.ReadDir(workspaces)
 if err!=nil||len(dirs)>500{return nil,errors.New("IA_MIGRACION_RESPALDO_NO_DISPONIBLE")}
 var candidates []*migrationPlan
 for _,entry:=range dirs {
  if !entry.IsDir()||strings.HasPrefix(entry.Name(),".")||len(entry.Name())>128{continue}
  journalDir:=filepath.Join(workspaces,entry.Name(),"tx395-rpg-live")
  journalFile:=filepath.Join(journalDir,"manifest.json")
  backupFile:=filepath.Join(journalDir,"original-plugins.js")
  if !ordinary(journalFile)||!ordinary(backupFile){continue}
  receiptBytes,e:=os.ReadFile(journalFile)
  if e!=nil||len(receiptBytes)>4096{continue}
  var journal oldPluginJournal
  if json.Unmarshal(receiptBytes,&journal)!=nil||journal.Schema!="tenshixgame-rpg-live-plugin-v1"||journal.Engine!="mv"||
    journal.Status!="INSTALLED"||len(journal.PluginSHA)!=64||
    len(journal.OriginalSHA)!=64||len(journal.UpdatedSHA)!=64{continue}
  if hash(current)!=journal.UpdatedSHA||hash(oldJS)!=journal.PluginSHA{continue}
  backup,e:=os.ReadFile(backupFile)
  if e!=nil||hash(backup)!=journal.OriginalSHA{continue}
  // No aplicar una migración sobre un registro de usuario diferente.
  _,entries,e:=parseRegistry(backup)
  if e!=nil{continue}
  if already,e:=checkEntries(entries);e!=nil||already{continue}
  candidates=append(candidates,&migrationPlan{
    OldRoot:sidecar,OldPlugin:oldPlugin,OriginalRegistry:backup,
    PreviousRegistry:append([]byte{},current...),
    PreviousPlugin:append([]byte{},oldJS...),
  })
 }
 if len(candidates)!=1{return nil,errors.New("IA_MIGRACION_RESPALDO_AMBIGUO_O_MODIFICADO")}
 return candidates[0],nil
}
// Tras instalar la nueva versión, archivar el runtime antiguo fuera de la
// raíz visible del juego, con capacidad de rollback. Sin borrado destructivo.
func archiveOldMigration(plan *migrationPlan,newRoot,registry,newPlugin string)error{
 if plan==nil{return nil}
 backupDir:=filepath.Join(newRoot,"Respaldos")
 if err:=os.MkdirAll(backupDir,0700);err!=nil{return err}
 pluginBackup:=filepath.Join(backupDir,"plugin-anterior.js")
 runtimeBackup:=filepath.Join(backupDir,"runtime-anterior")
 if _,err:=os.Lstat(pluginBackup);!os.IsNotExist(err){
  return errors.New("IA_MIGRACION_DESTINO_OCUPADO")
 }
 if _,err:=os.Lstat(runtimeBackup);!os.IsNotExist(err){
  return errors.New("IA_MIGRACION_RUNTIME_DESTINO_OCUPADO")
 }
 if !ordinary(plan.OldPlugin)||hashMustRead(plan.OldPlugin)!=hash(plan.PreviousPlugin){
  return errors.New("IA_MIGRACION_PLUGIN_CAMBIO_ANTES_DE_ARCHIVAR")
 }
 if err:=os.Rename(plan.OldPlugin,pluginBackup);err!=nil{return err}
 if err:=os.Rename(plan.OldRoot,runtimeBackup);err!=nil{
  _=os.Rename(pluginBackup,plan.OldPlugin)
  return errors.New("IA_MIGRACION_RUNTIME_BLOQUEADO")
 }
 // Se conserva el registro anterior para poder volver a él sin perder nada.
 if err:=createNew(filepath.Join(backupDir,"registro-anterior.js"),plan.PreviousRegistry);err!=nil{
  _=os.Rename(runtimeBackup,plan.OldRoot)
  _=os.Rename(pluginBackup,plan.OldPlugin)
  return err
 }
 return nil
}
func hashMustRead(file string)string{
 b,err:=os.ReadFile(file);if err!=nil{return ""};return hash(b)
}


// Reinstalación idempotente sólo si todos los bytes ya coinciden con el
// manifiesto que escribió esta aplicación. Nunca confundir nombre con firma.
func verifiedNewInstallation(root,content string,registry []byte)error{
    folder:=filepath.Join(root,brandFolder)
    ownerFile:=filepath.Join(folder,"owner-v1.json")
    journalFile:=filepath.Join(folder,"install","receipt.json")
    if !ordinary(ownerFile)||!ordinary(journalFile){
        return errors.New("IA_NUEVA_INSTALACION_SIN_MARCADOR_VERIFICABLE")
    }
    var marker ownerManifest
    raw,e:=os.ReadFile(ownerFile)
    if e!=nil||len(raw)>2048||json.Unmarshal(raw,&marker)!=nil||
       marker.Schema!=ownerSchema{return errors.New("IA_NUEVA_PROPIEDAD_NO_VERIFICADA")}
    var receipt installReceipt
    raw,e=os.ReadFile(journalFile)
    if e!=nil||json.Unmarshal(raw,&receipt)!=nil||
       receipt.Schema!="ia-traductora-install-v1"||receipt.Status!="INSTALLED"||
       hash(registry)!=receipt.AfterSHA||marker.PluginSHA!=receipt.PluginSHA{
        return errors.New("IA_INSTALACION_CAMBIO_REGISTRO")
    }
    _,entries,e:=parseRegistry(registry)
    if e!=nil{return errors.New("IA_INSTALACION_REGISTRO_NO_VALIDO")}
    active,e:=checkEntries(entries)
    if e!=nil||!active{return errors.New("IA_INSTALACION_PLUGIN_NO_ACTIVO")}
    plugin:=filepath.Join(content,"js","plugins",pluginName+".js")
    engine:=filepath.Join(folder,".local","Rpg","engine","IATraductora.exe")
    if !ordinary(plugin)||!ordinary(engine)||hashMustRead(plugin)!=marker.PluginSHA{
        return errors.New("IA_INSTALACION_COMPLEMENTO_NO_VERIFICADO")
    }
    workerSum,err:=digestFile(engine)
    if err!=nil||workerSum!=marker.WorkerSHA{
        return errors.New("IA_INSTALACION_MOTOR_NO_VERIFICADO")
    }
    if _,err=os.Lstat(filepath.Join(root,"Tenshixgame-IA"));err==nil{
        return errors.New("IA_MIGRACION_ANTERIOR_AUN_VISIBLE")
    }
    return nil
}

func digestFile(filename string)(string,error){
    in,e:=os.Open(filename);if e!=nil{return "",e};defer in.Close()
    h:=sha256.New()
    if _,e=io.CopyBuffer(h,in,make([]byte,256*1024));e!=nil{return "",e}
    return hex.EncodeToString(h.Sum(nil)),nil
}
