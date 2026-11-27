package main

// An adapter-only migration intentionally retains the verified R43 worker,
// launcher, models and all game-local SQLite files. The protocol/build
// remains LAB-2. A durable journal allows exact rollback or resume after
// interruption between the two owned file replacements.
import (
 "bytes"
 "encoding/json"
 "os"
 "path/filepath"
 "strings"
)
const xpCoverageRevision="R43-XP-COVERAGE-1"
const xpTransitionName="adapter-update-v1.json"

// Digests of the public R43 LAB-2 adapter at the approved previous commit,
// LF and Windows CRLF checkout. Not game data or user-specific hashes.
var xpPriorAdapterAllowed=func(sha string)bool{
 return sha=="d0353ea11085018d59d289a84ba3692e66ee4e519515d857de73480a8a58ec81"||
  sha=="1245dc0d767f5f44b0ee3b8942d7307e63f9ba43694156c03a724448d4f2007d"
}
type xpTransition struct{
 Schema string `json:"schema"`
 From xpReceipt `json:"from"`
 To xpReceipt `json:"to"`
 OldPlugin []byte `json:"old_plugin"`
 NewPlugin []byte `json:"new_plugin"`
}
func xpSameReceipt(a,b xpReceipt)bool{
 a.Status="";b.Status="";return a==b
}
func xpCheckRetainedModels(root string,pkg *packageReader)error{
 _,engine,_,_,_:=xpPaths(root)
 seen:=0
 for name,want:=range pkg.manifest.Files{
  if !strings.HasPrefix(name,"models/"){continue}
  if !safeFile(name){return xpError("MODELO_NO_VERIFICADO")}
  if e:=xpHashFile(filepath.Join(engine,filepath.FromSlash(name)),want);e!=nil{return xpError("MODELO_NO_VERIFICADO")}
  seen++
 }
 if seen==0{return xpError("MODELO_NO_VERIFICADO")}
 return nil
}
func xpReadTransition(journal string)(xpTransition,bool,error){
 var t xpTransition
 file:=filepath.Join(journal,xpTransitionName)
 if _,e:=os.Lstat(file);os.IsNotExist(e){return t,false,nil}else if e!=nil{return t,false,e}
 b,e:=xpRead(file,4*1024*1024)
 if e!=nil||json.Unmarshal(b,&t)!=nil||t.Schema!="ia-rpgxp-adapter-update-v1"||
  !xpReceiptValid(t.From)||!xpReceiptValid(t.To)||
  t.From.Before!=t.To.Before||t.From.Worker!=t.To.Worker||t.From.Launcher!=t.To.Launcher||
  t.From.Plugin==t.To.Plugin||t.From.After==t.To.After||
  !xpPriorAdapterAllowed(t.From.Plugin)||
  len(t.OldPlugin)>1024*1024||len(t.NewPlugin)>1024*1024||
  hash(t.OldPlugin)!=t.From.Plugin||hash(t.NewPlugin)!=t.To.Plugin||
  !bytes.Contains(t.NewPlugin,[]byte(xpCoverageRevision)){
  return t,false,xpError("ACTUALIZACION_RECIBO_INVALIDO")
 }
 return t,true,nil
}
func xpReplaceBytes(journal,target string,body []byte,want,current string)error{
 if hash(body)!=want{return xpError("ACTUALIZACION_SHA_INVALIDO")}
 f,e:=os.CreateTemp(journal,"adapter-candidate-");if e!=nil{return e}
 candidate:=f.Name();defer os.Remove(candidate)
 if _,e=f.Write(body);e!=nil{f.Close();return e}
 if e=f.Sync();e!=nil{f.Close();return e}
 if e=f.Close();e!=nil{return e}
 if e=vxaceAtomicReplaceFrom(candidate,target,want,current);e!=nil{return e}
 return xpHashFile(target,want)
}
// Called under the operation lock, with no active translator session.
// The old and new candidate archives are regenerated from the unchanged
// original backup. Never trust a receipt to authorize unknown bytes.
func xpApplyTransition(root,target string,t xpTransition,restore bool)error{
 _,engine,journal,backup,receiptFile:=xpPaths(root)
 r,ok,e:=xpReadReceipt(receiptFile)
 if e!=nil||!ok||(!xpSameReceipt(r,t.From)&&!xpSameReceipt(r,t.To)){return xpError("ACTUALIZACION_RECIBO_INVALIDO")}
 original,e:=xpRead(backup,xpMaxArchive);if e!=nil||hash(original)!=t.From.Before{return xpError("RESPALDO_NO_VERIFICADO")}
 prior,e:=xpPatchScripts(original,t.OldPlugin);if e!=nil||hash(prior)!=t.From.After{return xpError("ACTUALIZACION_ORIGEN_NO_VERIFICADO")}
 next,e:=xpPatchScripts(original,t.NewPlugin);if e!=nil||hash(next)!=t.To.After{return xpError("ACTUALIZACION_DESTINO_NO_VERIFICADO")}
 current,e:=xpRead(target,xpMaxArchive);if e!=nil{return e}
 currentSHA:=hash(current)
 if currentSHA!=t.From.Before&&currentSHA!=t.From.After&&currentSHA!=t.To.After{return xpError("RECURSO_MODIFICADO")}
 pluginFile:=filepath.Join(engine,filepath.FromSlash(xpPluginAsset))
 currentPlugin,e:=xpRead(pluginFile,1024*1024);if e!=nil{return e}
 pluginSHA:=hash(currentPlugin)
 if pluginSHA!=t.From.Plugin&&pluginSHA!=t.To.Plugin{return xpError("PLUGIN_NO_VERIFICADO")}
 active:=r;active.Plugin=pluginSHA
 if e=xpVerifiedAssets(root,active);e!=nil{return e}
 // While PREPARED, even the older installed launcher/worker refuses to
 // start. The independent journal remembers both valid target hashes.
 prepared:=t.To;prepared.Status="PREPARED"
 if e=xpRecord(receiptFile,prepared);e!=nil{return e}
 desired:=t.To;body:=t.NewPlugin;script:=next;targetSHA:=t.To.After
 if restore{desired=t.From;body=t.OldPlugin;script=original;targetSHA=t.From.Before}
 if pluginSHA!=desired.Plugin{
  if e=xpReplaceBytes(journal,pluginFile,body,desired.Plugin,pluginSHA);e!=nil{return e}
 }
 if currentSHA!=targetSHA{
  if e=xpReplaceBytes(journal,target,script,targetSHA,currentSHA);e!=nil{return e}
 }
 if e=xpHashFile(pluginFile,desired.Plugin);e!=nil{return e}
 if e=xpHashFile(target,targetSHA);e!=nil{return e}
 if restore{desired.Status="RESTORED"}else{desired.Status="INSTALLED"}
 if e=xpRecord(receiptFile,desired);e!=nil{return e}
 return os.Remove(filepath.Join(journal,xpTransitionName))
}
func xpInstallExisting(root,target string,pkg *packageReader,plugin []byte)error{
 _,engine,journal,backup,receiptFile:=xpPaths(root)
 unlock,e:=xpLock(journal);if e!=nil{return e};defer unlock()
 if e=xpNoSession(engine);e!=nil{return e}
 if e=xpCheckRetainedModels(root,pkg);e!=nil{return e}
 if t,exists,e:=xpReadTransition(journal);e!=nil{return e}else if exists{
  if t.To.Plugin!=hash(plugin){return xpError("ACTUALIZACION_VERSION_DISTINTA")}
  return xpApplyTransition(root,target,t,false)
 }
 r,ok,e:=xpReadReceipt(receiptFile)
 if e!=nil||!ok{return xpError("RECIBO_INVALIDO")}
 if e=xpVerifiedAssets(root,r);e!=nil{return e}
 original,e:=xpRead(backup,xpMaxArchive);if e!=nil||hash(original)!=r.Before{return xpError("RESPALDO_NO_VERIFICADO")}
 current,e:=xpRead(target,xpMaxArchive);if e!=nil{return e}
 currentSHA:=hash(current)
 if (currentSHA!=r.Before&&currentSHA!=r.After)||(r.Status=="INSTALLED"&&currentSHA!=r.After)||(r.Status=="RESTORED"&&currentSHA!=r.Before){
  return xpError("RECURSO_MODIFICADO")
 }
 next,e:=xpPatchScripts(original,plugin);if e!=nil{return e}
 if r.Plugin==hash(plugin){
  if hash(next)!=r.After{return xpError("RECIBO_NO_COINCIDE")}
  if currentSHA==r.Before{
   r.Status="PREPARED";if e=xpRecord(receiptFile,r);e!=nil{return e}
   if e=xpReplaceBytes(journal,target,next,r.After,r.Before);e!=nil{return e}
  }
  r.Status="INSTALLED";return xpRecord(receiptFile,r)
 }
 if !xpPriorAdapterAllowed(r.Plugin)||!bytes.Contains(plugin,[]byte(xpCoverageRevision)){return xpError("VERSION_DISTINTA")}
 oldPlugin,e:=xpRead(filepath.Join(engine,filepath.FromSlash(xpPluginAsset)),1024*1024)
 if e!=nil||hash(oldPlugin)!=r.Plugin{return xpError("PLUGIN_NO_VERIFICADO")}
 previous,e:=xpPatchScripts(original,oldPlugin);if e!=nil||hash(previous)!=r.After{return xpError("ACTUALIZACION_ORIGEN_NO_VERIFICADO")}
 updated:=r;updated.Status="PREPARED";updated.Plugin=hash(plugin);updated.After=hash(next)
 t:=xpTransition{"ia-rpgxp-adapter-update-v1",r,updated,oldPlugin,plugin}
 encoded,e:=json.Marshal(t);if e!=nil{return e}
 // Publish the complete journal atomically. No file mutation precedes it.
 file:=filepath.Join(journal,xpTransitionName)
 if _,e=os.Lstat(file);!os.IsNotExist(e){return xpError("ACTUALIZACION_RECIBO_INVALIDO")}
 if e=writeAtomic(file,encoded);e!=nil{return e}
 return xpApplyTransition(root,target,t,false)
}
