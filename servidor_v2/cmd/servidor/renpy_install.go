package main

import (
 _ "embed"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "io/fs"
 "os"
 "path/filepath"
 "sort"
 "strings"
)

// New, independent Ren'Py program. No game scripts, archives or saves are rewritten.
//go:embed renpy_assets/boot.rpy
var renpyBoot []byte
//go:embed renpy_assets/client.py
var renpyClient []byte

const renpySide="IA Traductora RenPy"
const renpySchema="ia-servidor-renpy-v1"
const renpyHook="ia_servidor_renpy"
type renpyDetection struct{Root string; RPY,RPYC,RPA int}
func (d renpyDetection)summary()string{return fmt.Sprintf("IA_RENPY_DETECTADO | .rpy=%d | .rpyc=%d | .rpa=%d | versión a verificar al ejecutar",d.RPY,d.RPYC,d.RPA)}
func renpyDir(p string)bool{return vxaceCloneCheckAncestors(p)==nil}
func renpyFile(p string)bool{return ordinary(p)&&vxaceCloneOrdinaryPath(p)&&renpyDir(filepath.Dir(p))}
func detectRenpy(exe string)(renpyDetection,error){
 var d renpyDetection
 p,e:=filepath.Abs(exe);if e!=nil||!strings.EqualFold(filepath.Ext(p),".exe")||!renpyFile(p){return d,errors.New("IA_RENPY_EXE_INVALIDO")}
 f,e:=os.Open(p);if e!=nil{return d,e};var magic [2]byte;_,e=io.ReadFull(f,magic[:]);f.Close()
 if e!=nil||string(magic[:])!="MZ"{return d,errors.New("IA_RENPY_EXE_INVALIDO")}
 d.Root=filepath.Dir(p)
 g:=filepath.Join(d.Root,"game");r:=filepath.Join(d.Root,"renpy")
 if !renpyDir(g)||!renpyDir(r)||!renpyDir(filepath.Join(d.Root,"lib")){return d,errors.New("IA_RENPY_ESTRUCTURA_NO_RECONOCIDA")}
 if !renpyFile(filepath.Join(r,"__init__.py"))&&!renpyFile(filepath.Join(r,"__init__.pyc")){return d,errors.New("IA_RENPY_ESTRUCTURA_NO_RECONOCIDA")}
 e=filepath.WalkDir(g,func(p string,n fs.DirEntry,e error)error{
  if e!=nil{return e}
  if p!=g&&n.IsDir()&&(n.Name()==renpyHook||strings.EqualFold(n.Name(),"saves")){return filepath.SkipDir}
  if !vxaceCloneOrdinaryPath(p){return errors.New("IA_RENPY_RUTA_INSEGURA")}
  if !n.IsDir(){switch strings.ToLower(filepath.Ext(p)){case ".rpy":d.RPY++;case ".rpyc":d.RPYC++;case ".rpa":d.RPA++}}
  return nil
 })
 if e!=nil{return d,e};if d.RPY+d.RPYC+d.RPA==0{return d,errors.New("IA_RENPY_SIN_RECURSOS")};return d,nil
}
type renpyReceipt struct{
 Schema string `json:"schema"`
 Client string `json:"client_sha256"`
 Boot string `json:"boot_sha256"`
 Engine map[string]string `json:"engine_sha256"`
}
func renpyPayload(p *packageReader)(map[string]string,error){
 out:=map[string]string{}
 for name,h:=range p.manifest.Files{
  if name=="IATraductora.exe"||strings.HasPrefix(name,"models/opus_en_es/")||strings.HasPrefix(name,"models/opus_ja_es/"){
   if !safeFile(name)||len(h)!=64||p.files[name]==nil{return nil,errors.New("IA_RENPY_PAQUETE_INVALIDO")}
   out[name]=h
  }
 }
 if out["IATraductora.exe"]==""{return nil,errors.New("IA_RENPY_SIN_MOTOR")}
 for _,l:=range []string{"opus_en_es","opus_ja_es"}{for _,n:=range []string{"model.bin","source.spm","target.spm","config.json"}{if out["models/"+l+"/"+n]==""{return nil,errors.New("IA_RENPY_SIN_MODELOS")}}}
 return out,nil
}
func renpyLock(root string)(func(),error){
 p:=filepath.Join(root,".ia-renpy-install.lock")
 f,e:=os.OpenFile(p,os.O_CREATE|os.O_EXCL|os.O_WRONLY,0600);if e!=nil{return nil,errors.New("IA_RENPY_OPERACION_BLOQUEADA")}
 return func(){f.Close();os.Remove(p)},nil
}
func renpyReadReceipt(side string)(renpyReceipt,error){
 var m renpyReceipt
 p:=filepath.Join(side,"owner-v1.json");if !renpyDir(side)||!renpyFile(p){return m,errors.New("IA_RENPY_PROPIEDAD_NO_VERIFICADA")}
 s,e:=os.Stat(p);if e!=nil||s.Size()>65536{return m,errors.New("IA_RENPY_PROPIEDAD_NO_VERIFICADA")}
 b,e:=os.ReadFile(p);if e!=nil||json.Unmarshal(b,&m)!=nil||m.Schema!=renpySchema||m.Client!=hash(renpyClient)||m.Boot!=hash(renpyBoot){return m,errors.New("IA_RENPY_PROPIEDAD_NO_VERIFICADA")}
 return m,nil
}
func renpyCheckSessions(side string)error{
 entries,e:=os.ReadDir(side);if e!=nil{return e}
 for _,n:=range entries{if strings.HasPrefix(n.Name(),"session-")&&strings.HasSuffix(n.Name(),".json"){return errors.New("IA_RENPY_SESION_PRESENTE_CERRAR_JUEGO")}}
 return nil
}
func renpyVerifySide(side string,m renpyReceipt,want map[string]string)error{
 if len(m.Engine)!=len(want){return errors.New("IA_RENPY_VERSION_DISTINTA")}
 p:=filepath.Join(side,"client.py");if !renpyFile(p){return errors.New("IA_RENPY_CLIENTE_INVALIDO")};h,e:=digestFile(p);if e!=nil||h!=m.Client{return errors.New("IA_RENPY_CLIENTE_INVALIDO")}
 for n,sha:=range want{if m.Engine[n]!=sha{return errors.New("IA_RENPY_VERSION_DISTINTA")};p:=filepath.Join(side,"engine",filepath.FromSlash(n));if !renpyFile(p){return errors.New("IA_RENPY_MOTOR_INVALIDO")};h,e:=digestFile(p);if e!=nil||h!=sha{return errors.New("IA_RENPY_MOTOR_INVALIDO")}}
 return nil
}
func renpyExtract(stage string,p *packageReader,want map[string]string)error{
 names:=make([]string,0,len(want));for n:=range want{names=append(names,n)};sort.Strings(names)
 for _,n:=range names{
  dest:=filepath.Join(stage,"engine",filepath.FromSlash(n));if e:=os.MkdirAll(filepath.Dir(dest),0700);e!=nil{return e}
  r,e:=p.files[n].Open();if e!=nil{return e}
  f,e:=os.OpenFile(dest,os.O_CREATE|os.O_EXCL|os.O_WRONLY,0600);if e!=nil{r.Close();return e}
  h:=sha256.New();_,e=io.Copy(io.MultiWriter(f,h),r);r.Close();syncErr:=f.Sync();closeErr:=f.Close()
  if e!=nil||syncErr!=nil||closeErr!=nil||hex.EncodeToString(h.Sum(nil))!=want[n]{return errors.New("IA_RENPY_MOTOR_SHA_NO_COINCIDE")}
 }
 if e:=createNew(filepath.Join(stage,"client.py"),renpyClient);e!=nil{return e}
 m:=renpyReceipt{renpySchema,hash(renpyClient),hash(renpyBoot),want};b,e:=json.Marshal(m);if e!=nil{return e};return createNew(filepath.Join(stage,"owner-v1.json"),b)
}
func renpyInstall(exe string,p *packageReader)error{
 d,e:=detectRenpy(exe);if e!=nil{return e}
 release,e:=renpyLock(d.Root);if e!=nil{return e};defer release()
 side:=filepath.Join(d.Root,renpySide);hook:=filepath.Join(d.Root,"game",renpyHook)
 if _,e:=os.Lstat(hook);!os.IsNotExist(e){return errors.New("IA_RENPY_HOOK_EXISTENTE_RESTAURAR")}
 want,e:=renpyPayload(p);if e!=nil{return e}
 if _,e:=os.Lstat(side);os.IsNotExist(e){
  stage,e:=os.MkdirTemp(d.Root,".ia-renpy-stage-");if e!=nil{return e};defer os.RemoveAll(stage)
  if e=renpyExtract(stage,p,want);e!=nil{return e}
  if _,e=os.Lstat(side);!os.IsNotExist(e){return errors.New("IA_RENPY_DESTINO_OCUPADO")}
  if e=os.Rename(stage,side);e!=nil{return e}
 }else if e!=nil{return e}
 m,e:=renpyReadReceipt(side);if e!=nil{return e}
 if e=renpyCheckSessions(side);e!=nil{return e}
 if e=renpyVerifySide(side,m,want);e!=nil{return e}
 stage,e:=os.MkdirTemp(d.Root,".ia-renpy-hook-");if e!=nil{return e};defer os.RemoveAll(stage)
 if e=createNew(filepath.Join(stage,"boot.rpy"),renpyBoot);e!=nil{return e}
 if _,e=os.Lstat(hook);!os.IsNotExist(e){return errors.New("IA_RENPY_DESTINO_OCUPADO")}
 return os.Rename(stage,hook)
}
func renpyRecover(exe string)error{
 d,e:=detectRenpy(exe);if e!=nil{return e}
 release,e:=renpyLock(d.Root);if e!=nil{return e};defer release()
 side:=filepath.Join(d.Root,renpySide);m,e:=renpyReadReceipt(side);if e!=nil{return e}
 if e=renpyCheckSessions(side);e!=nil{return e}
 hook:=filepath.Join(d.Root,"game",renpyHook)
 if !renpyDir(hook){return errors.New("IA_RENPY_HOOK_NO_VERIFICADO")}
 b:=filepath.Join(hook,"boot.rpy");if !renpyFile(b){return errors.New("IA_RENPY_HOOK_NO_VERIFICADO")}
 sha,e:=digestFile(b);if e!=nil||sha!=m.Boot{return errors.New("IA_RENPY_HOOK_ALTERADO")}
 entries,e:=os.ReadDir(hook);if e!=nil{return e}
 for _,n:=range entries{if (n.Name()!="boot.rpy"&&n.Name()!="boot.rpyc")||!renpyFile(filepath.Join(hook,n.Name())){return errors.New("IA_RENPY_ARCHIVO_AJENO")}}
 // Preserve all owned material outside game/; no destructive deletion.
 q,e:=os.MkdirTemp(side,"retired-");if e!=nil{return e}
 return os.Rename(hook,filepath.Join(q,renpyHook))
}
func renpyStatusText(exe string)(string,error){
 d,e:=detectRenpy(exe);if e!=nil{return "",e};side:=filepath.Join(d.Root,renpySide)
 if _,e=renpyReadReceipt(side);e!=nil{return "",e}
 p:=filepath.Join(side,"status.json");if !renpyFile(p){return "Todavía no hay sesión de traducción registrada.",nil}
 st,e:=os.Stat(p);if e!=nil||st.Size()>8192{return "",errors.New("IA_RENPY_ESTADO_INVALIDO")}
 b,e:=os.ReadFile(p);if e!=nil{return "",e}
 var s struct{Schema string;Translated,Cached,Rejected uint64}
 if json.Unmarshal(b,&s)!=nil||s.Schema!=renpySchema{return "",errors.New("IA_RENPY_ESTADO_INVALIDO")}
 return fmt.Sprintf("Último registro: traducciones nuevas=%d · reutilizadas=%d · rechazadas=%d",s.Translated,s.Cached,s.Rejected),nil
}
