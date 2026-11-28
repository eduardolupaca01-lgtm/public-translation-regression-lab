package main

// Explicit, opt-in localization of ordinary JSON resources only. No
// executable, script, binary loader, registry or integrity check is edited.
// The immutable intent and prepared receipt precede any target replacement.
// A partial two-file publication can be restored after process interruption.
import (
 "encoding/json"
 "errors"
 "fmt"
 "os"
 "path/filepath"
 "strings"
)

const mvJSONDirectSchema="ia-mv-json-direct-v1"
const mvJSONDirectDir="mv-json-direct"
const mvJSONDirectLimit=16*1024*1024

type mvJSONDirectProfile struct{
 Schema string `json:"schema"`
 Worker string `json:"worker_sha256"`
 Plugin string `json:"plugin_sha256"`
}
type mvJSONDirectIntent struct{
 Schema string `json:"schema"`
 Content string `json:"content"`
 Map string `json:"map"`
 Boot string `json:"boot_sha256"`
 MapBefore string `json:"map_before_sha256"`
 SystemBefore string `json:"system_before_sha256"`
}
type mvJSONDirectReceipt struct{
 Schema string `json:"schema"`
 Intent string `json:"intent_sha256"`
 MapAfter string `json:"map_after_sha256"`
 SystemAfter string `json:"system_after_sha256"`
 Report mvJSONReport `json:"translation"`
}
type mvJSONDirectFile struct{target,backup,candidate,before,after string}
type mvJSONReplace func(string,string,string,string)error

func mvJSONDirectWrite(file string,value any)error{
 b,e:=json.MarshalIndent(value,"","  ");if e!=nil{return e}
 return createNew(file,b)
}
func mvJSONDirectRead(file string,value any)([]byte,error){
 b,e:=mvJSONRead(file,16384)
 if e!=nil||json.Unmarshal(b,value)!=nil{return nil,mvJSONError("DIRECTO_DIARIO_INVALIDO")}
 return b,nil
}
func mvJSONDirectBase(root string)string{
 return filepath.Join(root,brandFolder,"install",mvJSONDirectDir)
}

// Check presence for UI routing only. Every actual operation revalidates
// owner, profile, journal, hashes and the original engine independently.
func mvJSONDirectNeedsRecovery(exe string)bool{
 p,e:=filepath.Abs(exe);if e!=nil||exe==""{return false}
 _,e=os.Lstat(filepath.Join(mvJSONDirectBase(filepath.Dir(p)),"active"))
 return !os.IsNotExist(e)
}

func mvJSONDirectOpen(root string,pkg *packageReader,create bool)(string,func(),error){
 noop:=func(){}
 sidecar:=filepath.Join(root,brandFolder)
 base:=mvJSONDirectBase(root)
 bad:=mvJSONError("DIRECTO_SIDECAR_NO_VERIFICADO")
 if vxaceCloneCheckAncestors(root)!=nil{return "",noop,bad}
 if _,e:=os.Lstat(sidecar);os.IsNotExist(e){
  if !create||pkg==nil{return "",noop,bad}
  if _,e=iaPrepareAndPublishSidecar(root,pkg);e!=nil{return "",noop,e}
 }else if e!=nil||vxaceCloneCheckAncestors(sidecar)!=nil{return "",noop,bad}
 if vxaceCloneCheckAncestors(sidecar)!=nil{return "",noop,bad}
 install:=filepath.Join(sidecar,"install")
 if vxaceCloneCheckAncestors(install)!=nil{return "",noop,bad}
 ownerFile:=filepath.Join(sidecar,"owner-v1.json")
 if !ordinary(ownerFile)||!vxaceCloneOrdinaryPath(ownerFile){return "",noop,bad}
 owner,e:=iaReadOwner(ownerFile)
 if e!=nil||owner.Product!="SERVIDOR-IA-TRADUCTORA"||!xpSHA(owner.WorkerSHA)||!xpSHA(owner.PluginSHA){return "",noop,bad}
 // Do not mix direct JSON with another installation journal.
 entries,e:=os.ReadDir(install);if e!=nil{return "",noop,bad}
 for _,item:=range entries{if item.Name()!=mvJSONDirectDir{return "",noop,bad}}
 if create{
  if pkg==nil{return "",noop,bad}
  engine:=filepath.Join(sidecar,".local","Rpg","engine")
  if vxaceCloneCheckAncestors(engine)!=nil{return "",noop,bad}
  for _,n:=range iaSortedFiles(pkg){
   f:=filepath.Join(engine,filepath.FromSlash(n))
   if vxaceCloneCheckAncestors(filepath.Dir(f))!=nil||!ordinary(f)||!vxaceCloneOrdinaryPath(f){return "",noop,bad}
  }
  if e=iaCheckEngine(sidecar,pkg);e!=nil{return "",noop,e}
  if e=os.Mkdir(base,0700);e!=nil&&!os.IsExist(e){return "",noop,bad}
 }
 if vxaceCloneCheckAncestors(base)!=nil{return "",noop,bad}
 unlock,e:=mvJSONDirectLock(base);if e!=nil{return "",noop,e}
 fail:=func(err error)(string,func(),error){unlock();return "",noop,err}
 profileFile:=filepath.Join(base,"profile.json")
 expected:=mvJSONDirectProfile{mvJSONDirectSchema,owner.WorkerSHA,owner.PluginSHA}
 if _,e=os.Lstat(profileFile);os.IsNotExist(e)&&create{
  es,er:=os.ReadDir(base);if er!=nil{return fail(bad)}
  for _,item:=range es{if item.Name()!="operation.lock"{return fail(bad)}}
  if e=mvJSONDirectWrite(profileFile,expected);e!=nil{return fail(bad)}
 }
 var profile mvJSONDirectProfile
 if _,e=mvJSONDirectRead(profileFile,&profile);e!=nil||profile!=expected{return fail(bad)}
 return base,unlock,nil
}

// Preserve the current copy behavior on a clean source. A direct
// installation must be restored before copying; its verified sidecar and
// cache stay in the source and are never copied over the fresh sidecar.
func mvJSONDirectCopyGuard(root string)(bool,func(),error){
 noop:=func(){}
 _,e:=os.Lstat(filepath.Join(root,brandFolder))
 if os.IsNotExist(e){return false,noop,nil}
 if e!=nil{return false,noop,mvJSONError("COPIA_PREVIA_NO_ADMITIDA")}
 base,unlock,e:=mvJSONDirectOpen(root,nil,false)
 if e!=nil{return false,noop,mvJSONError("COPIA_PREVIA_NO_ADMITIDA")}
 if _,e=os.Lstat(filepath.Join(base,"active"));!os.IsNotExist(e){unlock();return false,noop,mvJSONError("DIRECTO_RECUPERAR_PRIMERO")}
 return true,unlock,nil
}

func mvJSONBootFingerprint(exe,root,content string)(string,error){
 files:=map[string]string{}
 required:=[]string{exe,filepath.Join(root,"package.json"),filepath.Join(content,"index.html"),
  filepath.Join(content,"js","main.js"),filepath.Join(content,"js","plugins.bin"),
  filepath.Join(content,"data","Actors.json"),filepath.Join(content,"data","CommonEvents.json"),
  filepath.Join(content,"data","MapInfos.json")}
 for _,n:=range mvnwbinCore{required=append(required,filepath.Join(content,"js",n))}
 for _,n:=range []string{"guard.bin","plugins.js"}{
  p:=filepath.Join(content,"js",n)
  if _,e:=os.Lstat(p);os.IsNotExist(e){
   rel,er:=filepath.Rel(root,p);if er!=nil{return "",er}
   files[filepath.ToSlash(rel)]="absent";continue
  }else if e!=nil{return "",e}
  required=append(required,p)
 }
 for _,p:=range required{
  if !ordinary(p)||!vxaceCloneOrdinaryPath(p)||vxaceCloneCheckAncestors(filepath.Dir(p))!=nil{return "",mvJSONError("DIRECTO_ARRANQUE_CAMBIADO")}
  rel,e:=filepath.Rel(root,p)
  if e!=nil||!safeFile(filepath.ToSlash(rel)){return "",mvJSONError("DIRECTO_ARRANQUE_CAMBIADO")}
  h,e:=digestFile(p);if e!=nil{return "",e}
  files[filepath.ToSlash(rel)]=h
 }
 b,e:=json.Marshal(files);if e!=nil{return "",e}
 return hash(b),nil
}
func mvJSONDirectReadIntent(exe,root,content,active string)(mvJSONDirectIntent,[]byte,error){
 var in mvJSONDirectIntent
 raw,e:=mvJSONDirectRead(filepath.Join(active,"intent.json"),&in)
 if e!=nil{return in,nil,e}
 rel,e:=filepath.Rel(root,content)
 if e!=nil||in.Schema!=mvJSONDirectSchema||in.Content!=rel||
  (rel!="www"&&rel!=".")||!mvJSONName.MatchString(in.Map)||
  !xpSHA(in.Boot)||!xpSHA(in.MapBefore)||!xpSHA(in.SystemBefore){
  return in,nil,mvJSONError("DIRECTO_DIARIO_INVALIDO")
 }
 currentMap,e:=mvJSONStart(content)
 if e!=nil||currentMap!=in.Map{return in,nil,mvJSONError("DIRECTO_ORIGEN_CAMBIADO")}
 fingerprint,e:=mvJSONBootFingerprint(exe,root,content)
 if e!=nil||fingerprint!=in.Boot{return in,nil,mvJSONError("DIRECTO_ARRANQUE_CAMBIADO")}
 return in,raw,nil
}
func mvJSONDirectFiles(content,active string,in mvJSONDirectIntent,rec *mvJSONDirectReceipt)[]mvJSONDirectFile{
 data:=filepath.Join(content,"data")
 files:=[]mvJSONDirectFile{
  {filepath.Join(data,in.Map),filepath.Join(active,"original-"+in.Map),filepath.Join(active,"candidate.json"),in.MapBefore,in.MapBefore},
  {filepath.Join(data,"System.json"),filepath.Join(active,"original-System.json"),filepath.Join(active,"candidate-System.json"),in.SystemBefore,in.SystemBefore},
 }
 if rec!=nil{files[0].after=rec.MapAfter;files[1].after=rec.SystemAfter}
 return files
}

func mvJSONDirectCheckedHash(file string)(string,error){
 b,e:=mvJSONRead(file,mvJSONDirectLimit);if e!=nil{return "",e}
 return hash(b),nil
}

// Check BOTH targets and BOTH backups before making any change. A
// foreign edit, game update, missing backup or malformed receipt must
// never cause restoration of either target.
func mvJSONDirectValidateFiles(files []mvJSONDirectFile)([]string,error){
 states:=make([]string,len(files))
 for i,f:=range files{
  b,e:=mvJSONDirectCheckedHash(f.backup)
  if e!=nil||b!=f.before{return nil,mvJSONError("DIRECTO_RESPALDO_ALTERADO")}
  now,e:=mvJSONDirectCheckedHash(f.target)
  if e!=nil||now!=f.before&&now!=f.after{return nil,mvJSONError("DIRECTO_DATOS_CAMBIADOS")}
  states[i]=now
 }
 return states,nil
}

func mvJSONDirectRestoreFiles(files []mvJSONDirectFile,replace mvJSONReplace)error{
 states,e:=mvJSONDirectValidateFiles(files);if e!=nil{return e}
 for i,f:=range files{
  if states[i]==f.before{continue}
  if e=replace(f.backup,f.target,f.before,states[i]);e!=nil{return e}
  if now,e:=mvJSONDirectCheckedHash(f.target);e!=nil||now!=f.before{return mvJSONError("DIRECTO_RECUPERACION_PENDIENTE")}
 }
 _,e=mvJSONDirectValidateFiles(files)
 return e
}
func mvJSONDirectArchive(base,active string)error{
 // Reserve a unique archive directory and move the entire journal into
 // it. No user data or previous backup is deleted or overwritten.
 archive,e:=os.MkdirTemp(base,"restored-");if e!=nil{return mvJSONError("DIRECTO_ARCHIVO_FALLO")}
 if e=os.Rename(active,filepath.Join(archive,"transaction"));e!=nil{return mvJSONError("DIRECTO_ARCHIVO_FALLO")}
 return nil
}
func mvJSONDirectRecoverLocked(exe,root,content,base string,replace mvJSONReplace)error{
 active:=filepath.Join(base,"active")
 if _,e:=os.Lstat(active);os.IsNotExist(e){return nil}
 if vxaceCloneCheckAncestors(active)!=nil{return mvJSONError("DIRECTO_DIARIO_INVALIDO")}
 in,raw,e:=mvJSONDirectReadIntent(exe,root,content,active);if e!=nil{return e}
 var receipt *mvJSONDirectReceipt
 recFile:=filepath.Join(active,"prepared.json")
 if _,e=os.Lstat(recFile);!os.IsNotExist(e){
  var rec mvJSONDirectReceipt
  if _,e=mvJSONDirectRead(recFile,&rec);e!=nil||rec.Schema!=mvJSONDirectSchema||rec.Intent!=hash(raw)||
    !xpSHA(rec.MapAfter)||!xpSHA(rec.SystemAfter){return mvJSONError("DIRECTO_DIARIO_INVALIDO")}
  receipt=&rec
 }
 files:=mvJSONDirectFiles(content,active,in,receipt)
 if e=mvJSONDirectRestoreFiles(files,replace);e!=nil{return e}
 // Prove restored byte hashes, not just membership in before/after.
 for _,f:=range files{if h,e:=mvJSONDirectCheckedHash(f.target);e!=nil||h!=f.before{return mvJSONError("DIRECTO_RECUPERACION_PENDIENTE")}}
 return mvJSONDirectArchive(base,active)
}
func mvJSONRecoverDirect(exe string)error{
 root,content,e:=mvJSONSource(exe);if e!=nil{return e}
 exe,e=filepath.Abs(exe);if e!=nil{return e}
 base,unlock,e:=mvJSONDirectOpen(root,nil,false);if e!=nil{return e};defer unlock()
 return mvJSONDirectRecoverLocked(exe,root,content,base,vxaceAtomicReplaceFrom)
}

func mvJSONInstallDirect(exe string,pkg *packageReader)(mvJSONReport,error){
 return mvJSONInstallDirectWith(exe,pkg,mvJSONRunDirectWorker,vxaceAtomicReplaceFrom)
}

func mvJSONInstallDirectWith(exe string,pkg *packageReader,run func(string,string,string)error,replace mvJSONReplace)(mvJSONReport,error){
 var report mvJSONReport
 root,content,e:=mvJSONSource(exe);if e!=nil{return report,e}
 if pkg==nil{return report,mvJSONError("PAQUETE_INCOMPLETO")}
 exe,e=filepath.Abs(exe);if e!=nil{return report,e}
 // No full game clone. Require space only for the verified payload and
 // bounded original/candidate JSON files, not for graphics or audio.
 needed:=uint64(128*1024*1024)
 if _,e=os.Lstat(filepath.Join(root,brandFolder));os.IsNotExist(e){
  for _,name:=range iaSortedFiles(pkg){f:=pkg.files[name];if f==nil{return report,mvJSONError("PAQUETE_INCOMPLETO")};needed+=f.UncompressedSize64}
 }
 if e=vxaceCheckDiskSpace(root,needed);e!=nil{return report,e}
 base,unlock,e:=mvJSONDirectOpen(root,pkg,true);if e!=nil{return report,e};defer unlock()
 active:=filepath.Join(base,"active")
 if _,e=os.Lstat(active);!os.IsNotExist(e){return report,mvJSONError("DIRECTO_RECUPERAR_PRIMERO")}
 // Recheck the original engine after taking the operation lock.
 rr,cc,e:=mvJSONSource(exe);if e!=nil||rr!=root||cc!=content{return report,mvJSONError("DIRECTO_ARRANQUE_CAMBIADO")}
 rel,e:=filepath.Rel(root,content);if e!=nil||rel!="www"&&rel!="."{return report,mvJSONError("RUTA_NO_VERIFICADA")}
 name,e:=mvJSONStart(content);if e!=nil{return report,e}
 mapFile:=filepath.Join(content,"data",name)
 systemFile:=filepath.Join(content,"data","System.json")
 before,e:=mvJSONRead(mapFile,mvJSONDirectLimit);if e!=nil{return report,e}
 tree,e:=mvJSONDecode(before);if e!=nil{return report,e}
 if _,e=mvJSONDisplay(tree);e!=nil{return report,e}
 sysBefore,e:=mvJSONRead(systemFile,mvJSONDirectLimit);if e!=nil{return report,e}
 sysAfter,menu,e:=mvJSONLocalizeSystem(sysBefore);if e!=nil{return report,e}
 fingerprint,e:=mvJSONBootFingerprint(exe,root,content);if e!=nil{return report,e}
 in:=mvJSONDirectIntent{mvJSONDirectSchema,rel,name,fingerprint,hash(before),hash(sysBefore)}
 stage,e:=os.MkdirTemp(base,"prepare-");if e!=nil{return report,mvJSONError("DIRECTO_DIARIO_INVALIDO")}
 // Stage the exact original resources and the immutable intent before
 // making the operation active. Interrupted preparation cannot touch
 // either target and leaves all existing game data unchanged.
 if e=createNew(filepath.Join(stage,"original-"+name),before);e!=nil{return report,e}
 if e=createNew(filepath.Join(stage,"original-System.json"),sysBefore);e!=nil{return report,e}
 if e=mvJSONDirectWrite(filepath.Join(stage,"intent.json"),in);e!=nil{return report,e}
 if e=mvJSONDirectWrite(filepath.Join(stage,"request.json"),mvJSONRequest{mvJSONSchema,rel,name,in.MapBefore});e!=nil{return report,e}
 if e=os.Rename(stage,active);e!=nil{return report,mvJSONError("DIRECTO_DIARIO_INVALIDO")}
 engine:=filepath.Join(root,brandFolder,".local","Rpg","engine")
 if e=run(engine,root,active);e!=nil{return report,e} // originals still intact
 report,e=mvJSONValidateCandidate(active,name,before);if e!=nil{return report,e}
 report.Menu=menu
 if e=createNew(filepath.Join(active,"candidate-System.json"),sysAfter);e!=nil{return report,e}
 verified,intentRaw,e:=mvJSONDirectReadIntent(exe,root,content,active)
 if e!=nil||verified!=in{return report,mvJSONError("DIRECTO_ORIGEN_CAMBIADO")}
 rec:=mvJSONDirectReceipt{mvJSONDirectSchema,hash(intentRaw),report.After,hash(sysAfter),report}
 files:=mvJSONDirectFiles(content,active,in,&rec)
 states,e:=mvJSONDirectValidateFiles(files);if e!=nil{return report,e}
 for i,f:=range files{
  if states[i]!=f.before{return report,mvJSONError("DIRECTO_DATOS_CAMBIADOS")}
  if h,e:=mvJSONDirectCheckedHash(f.candidate);e!=nil||h!=f.after{return report,mvJSONError("RESULTADO_INVALIDO")}
 }
 // Immutable prepared record is flushed before either resource changes.
 if e=mvJSONDirectWrite(filepath.Join(active,"prepared.json"),rec);e!=nil{return report,e}
 rollback:=func(cause error)(mvJSONReport,error){
  // If a concurrent writer changed a resource, do not overwrite it.
  // Retain the journal and backups for a later verified recovery.
  if er:=mvJSONDirectRecoverLocked(exe,root,content,base,replace);er!=nil{return report,mvJSONError("DIRECTO_RECUPERACION_PENDIENTE")}
  var osErr *os.PathError
  if errors.As(cause,&osErr){return report,mvJSONError("DIRECTO_REVERTIDO")}
  return report,fmt.Errorf("IA_MV_JSON_DIRECTO_REVERTIDO: %w",cause)
 }
 for _,f:=range files{
  if f.before==f.after{continue}
  if e=replace(f.candidate,f.target,f.after,f.before);e!=nil{return rollback(e)}
  if h,e:=mvJSONDirectCheckedHash(f.target);e!=nil||h!=f.after{return rollback(mvJSONError("RESULTADO_INVALIDO"))}
 }
 if h,e:=mvJSONBootFingerprint(exe,root,content);e!=nil||h!=in.Boot{return rollback(mvJSONError("DIRECTO_ARRANQUE_CAMBIADO"))}
 for _,f:=range files{if h,e:=mvJSONDirectCheckedHash(f.target);e!=nil||h!=f.after{return rollback(mvJSONError("RESULTADO_INVALIDO"))}}
 if e=mvJSONDirectWrite(filepath.Join(active,"installed.json"),struct{Schema string `json:"schema"`;Receipt string `json:"intent_sha256"`}{mvJSONDirectSchema,rec.Intent});e!=nil{return rollback(e)}
 return report,nil
}
