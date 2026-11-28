package main

import (
 _ "embed"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "crypto/rand"
 "strconv"
 "os"
 "os/exec"
 "path/filepath"
 "sort"
 "strings"
)

// New, independent Ren'Py program. No game scripts, archives or saves are rewritten.
//go:embed renpy_assets/boot.rpy
var renpyBoot []byte
//go:embed renpy_assets/client.py
var renpyClient []byte
//go:embed renpy_assets/classic_client.py
var renpyClassicClient []byte
//go:embed renpy_assets/classic_start.py
var renpyClassicStart []byte
//go:embed renpy_assets/classic_entry.py
var renpyClassicEntry []byte

const renpySide="IA Traductora RenPy"
const renpySchema="ia-servidor-renpy-v1"
const renpyHook="ia_servidor_renpy"
func renpyDir(p string)bool{return vxaceCloneCheckAncestors(p)==nil}
func renpyFile(p string)bool{return ordinary(p)&&vxaceCloneOrdinaryPath(p)&&renpyDir(filepath.Dir(p))}
func detectRenpy(exe string)(renpyDetection,error){
 var d renpyDetection
 p,e:=filepath.Abs(exe);if e!=nil||!strings.EqualFold(filepath.Ext(p),".exe")||!renpyFile(p){return d,errors.New("IA_RENPY_EXE_INVALIDO")}
 f,e:=os.Open(p);if e!=nil{return d,e};var magic [2]byte;_,e=io.ReadFull(f,magic[:]);f.Close()
 if e!=nil||string(magic[:])!="MZ"{return d,errors.New("IA_RENPY_EXE_INVALIDO")}
 root:=filepath.Dir(p)
 evidence,e:=renpyRuntimeAt(root);if e!=nil{return d,e}
 profile,e:=renpyProfile(evidence,root);if e!=nil{return d,e}
 d,e=renpyFindGame(root,p,profile);if e!=nil{return d,e}
 d.Version=evidence.version;d.Release=renpyCatalogMatch(d.Version);return d,nil
}
// Classic Ren'Py 4's parser requires nested init:/python: and its script
// loader enumerates only top-level files. Embed our original ASCII client
// into the added script so no JSON/hashlib/import of an external script is
// required in a Python 2.3 game. Source and installed bytes are SHA-verified.
func renpyAssets(profile string)(client,boot []byte){
 if profile!=renpyClassicProfile{return renpyClient,renpyBoot}
 code:=strconv.Quote(string(renpyClassicClient))
 boot=[]byte("# IA_SERVIDOR_RENPY_CLASSIC_OWNED\ninit 999:\n    python hide:\n        try:\n            import renpy as _ia_engine\n            import types as _ia_types\n            import sys as _ia_sys\n            _ia_module = _ia_types.ModuleType('_ia_servidor_classic')\n            _ia_sys.modules['_ia_servidor_classic'] = _ia_module\n            eval(compile("+code+", 'ia_classic_client.py', 'exec'), _ia_module.__dict__)\n            _ia_module.install(_ia_engine)\n        except Exception:\n            try:\n                _ia_engine.log('IA_RENPY_CLASICO_ARRANQUE_NO_DISPONIBLE')\n            except Exception:\n                pass\n")
 return renpyClassicClient,boot
}
func renpyHookAt(d renpyDetection)string{
 if d.Profile==renpyClassicProfile{return filepath.Join(d.gameDir(),renpyClassicHook)}
 return filepath.Join(d.gameDir(),renpyHook)
}
func renpyHookExists(d renpyDetection)bool{
 p:=renpyHookAt(d)
 if _,e:=os.Lstat(p);!os.IsNotExist(e){return true}
 if d.Profile==renpyClassicProfile{if _,e:=os.Lstat(p+"c");!os.IsNotExist(e){return true}}
 return false
}
type renpyReceipt struct{
 Schema string `json:"schema"`
 Client string `json:"client_sha256"`
 Boot string `json:"boot_sha256"`
 Engine map[string]string `json:"engine_sha256"`
 Profile string `json:"profile,omitempty"`
 GameRel string `json:"game_rel,omitempty"`
 ClassicKey string `json:"classic_key_sha256,omitempty"`
 ClassicStart string `json:"classic_start_sha256,omitempty"`
 ClassicEntry string `json:"classic_entry_sha256,omitempty"`
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
 b,e:=os.ReadFile(p);if e!=nil||json.Unmarshal(b,&m)!=nil||m.Schema!=renpySchema{return m,errors.New("IA_RENPY_PROPIEDAD_NO_VERIFICADA")}
 if m.Profile==""{m.Profile=renpyModernProfile};if m.GameRel==""{m.GameRel="game"}
 if (m.Profile!=renpyModernProfile&&m.Profile!=renpyClassicProfile)||!renpyGameRelValid(m.GameRel){return m,errors.New("IA_RENPY_PROPIEDAD_NO_VERIFICADA")}
 client,boot:=renpyAssets(m.Profile)
 if m.Client!=hash(client)||m.Boot!=hash(boot){return m,errors.New("IA_RENPY_PROPIEDAD_NO_VERIFICADA")}
 if m.Profile==renpyClassicProfile{
  p:=filepath.Join(side,"classic-key.txt");if !renpyFile(p){return m,errors.New("IA_RENPY_CLAVE_INVALIDA")}
  st,e:=os.Stat(p);if e!=nil||st.Size()!=32{return m,errors.New("IA_RENPY_CLAVE_INVALIDA")}
  raw,e:=os.ReadFile(p);if e!=nil||hash(raw)!=m.ClassicKey{return m,errors.New("IA_RENPY_CLAVE_INVALIDA")}
  if _,e=hex.DecodeString(string(raw));e!=nil{return m,errors.New("IA_RENPY_CLAVE_INVALIDA")}
 }
 return m,nil
}
func renpyCheckSessions(side string)error{
 entries,e:=os.ReadDir(side);if e!=nil{return e}
 for _,n:=range entries{if (strings.HasPrefix(n.Name(),"session-")&&strings.HasSuffix(n.Name(),".json"))||strings.HasPrefix(n.Name(),"classic-session-"){return errors.New("IA_RENPY_SESION_PRESENTE_CERRAR_JUEGO")}}
 return nil
}
func renpyVerifyClassicStart(side string,m renpyReceipt)error{
 for _,a:=range []struct{name,want string;data []byte}{
  {"classic_start.py",m.ClassicStart,renpyClassicStart},{"classic_entry.py",m.ClassicEntry,renpyClassicEntry},
 }{
  p:=filepath.Join(side,a.name);if a.want!=hash(a.data)||!renpyFile(p){return errors.New("IA_RENPY_INICIO_CLASICO_NO_VERIFICADO")}
  h,e:=digestFile(p);if e!=nil||h!=a.want{return errors.New("IA_RENPY_INICIO_CLASICO_NO_VERIFICADO")}
 }
 return nil
}
func renpyVerifySide(side string,m renpyReceipt,want map[string]string)error{
 if m.Profile==renpyClassicProfile{if e:=renpyVerifyClassicStart(side,m);e!=nil{return e}}
 if len(m.Engine)!=len(want){return errors.New("IA_RENPY_VERSION_DISTINTA")}
 p:=filepath.Join(side,"client.py");if !renpyFile(p){return errors.New("IA_RENPY_CLIENTE_INVALIDO")};h,e:=digestFile(p);if e!=nil||h!=m.Client{return errors.New("IA_RENPY_CLIENTE_INVALIDO")}
 for n,sha:=range want{if m.Engine[n]!=sha{return errors.New("IA_RENPY_VERSION_DISTINTA")};p:=filepath.Join(side,"engine",filepath.FromSlash(n));if !renpyFile(p){return errors.New("IA_RENPY_MOTOR_INVALIDO")};h,e:=digestFile(p);if e!=nil||h!=sha{return errors.New("IA_RENPY_MOTOR_INVALIDO")}}
 return nil
}
func renpyExtract(stage string,p *packageReader,want map[string]string,d renpyDetection)error{
 names:=make([]string,0,len(want));for n:=range want{names=append(names,n)};sort.Strings(names)
 for _,n:=range names{
  dest:=filepath.Join(stage,"engine",filepath.FromSlash(n));if e:=os.MkdirAll(filepath.Dir(dest),0700);e!=nil{return e}
  r,e:=p.files[n].Open();if e!=nil{return e}
  f,e:=os.OpenFile(dest,os.O_CREATE|os.O_EXCL|os.O_WRONLY,0600);if e!=nil{r.Close();return e}
  h:=sha256.New();_,e=io.Copy(io.MultiWriter(f,h),r);r.Close();syncErr:=f.Sync();closeErr:=f.Close()
  if e!=nil||syncErr!=nil||closeErr!=nil||hex.EncodeToString(h.Sum(nil))!=want[n]{return errors.New("IA_RENPY_MOTOR_SHA_NO_COINCIDE")}
 }
 client,boot:=renpyAssets(d.Profile)
 if e:=createNew(filepath.Join(stage,"client.py"),client);e!=nil{return e}
 m:=renpyReceipt{Schema:renpySchema,Client:hash(client),Boot:hash(boot),Engine:want,Profile:d.Profile,GameRel:d.GameRel}
 if d.Profile==renpyClassicProfile{
  key:=make([]byte,16);if _,e:=rand.Read(key);e!=nil{return e}
  raw:=[]byte(hex.EncodeToString(key));m.ClassicKey=hash(raw)
  if e:=createNew(filepath.Join(stage,"classic-key.txt"),raw);e!=nil{return e}
  m.ClassicStart=hash(renpyClassicStart);m.ClassicEntry=hash(renpyClassicEntry)
  if e:=createNew(filepath.Join(stage,"classic_start.py"),renpyClassicStart);e!=nil{return e}
  if e:=createNew(filepath.Join(stage,"classic_entry.py"),renpyClassicEntry);e!=nil{return e}
 }
 b,e:=json.Marshal(m);if e!=nil{return e};return createNew(filepath.Join(stage,"owner-v1.json"),b)
}
func renpyInstall(exe string,p *packageReader)error{
 d,e:=detectRenpy(exe);if e!=nil{return e}
 release,e:=renpyLock(d.Root);if e!=nil{return e};defer release()
 side:=filepath.Join(d.Root,renpySide);hook:=renpyHookAt(d)
 if renpyHookExists(d){return errors.New("IA_RENPY_HOOK_EXISTENTE_RESTAURAR")}
 want,e:=renpyPayload(p);if e!=nil{return e}
 if _,e:=os.Lstat(side);os.IsNotExist(e){
  stage,e:=os.MkdirTemp(d.Root,".ia-renpy-stage-");if e!=nil{return e};defer os.RemoveAll(stage)
  if e=renpyExtract(stage,p,want,d);e!=nil{return e}
  if _,e=os.Lstat(side);!os.IsNotExist(e){return errors.New("IA_RENPY_DESTINO_OCUPADO")}
  if e=os.Rename(stage,side);e!=nil{return e}
 }else if e!=nil{return e}
 m,e:=renpyReadReceipt(side);if e!=nil{return e}
 if m.Profile!=d.Profile||m.GameRel!=d.GameRel{return errors.New("IA_RENPY_PERFIL_DISTINTO")}
 if e=renpyCheckSessions(side);e!=nil{return e}
 if e=renpyVerifySide(side,m,want);e!=nil{return e}
 _,boot:=renpyAssets(d.Profile)
 if d.Profile==renpyClassicProfile{
  stage,e:=os.MkdirTemp(d.Root,".ia-renpy-flat-");if e!=nil{return e};defer os.RemoveAll(stage)
  candidate:=filepath.Join(stage,renpyClassicHook)
  if e=createNew(candidate,boot);e!=nil{return e}
  // Exclusive publication of an added file, never overwriting a game script.
  if renpyHookExists(d){return errors.New("IA_RENPY_DESTINO_OCUPADO")}
  if e=os.Link(candidate,hook);e!=nil{return errors.New("IA_RENPY_PUBLICACION_PLANA_FALLO")}
  return nil
 }
 stage,e:=os.MkdirTemp(d.Root,".ia-renpy-hook-");if e!=nil{return e};defer os.RemoveAll(stage)
 if e=createNew(filepath.Join(stage,"boot.rpy"),boot);e!=nil{return e}
 if _,e=os.Lstat(hook);!os.IsNotExist(e){return errors.New("IA_RENPY_DESTINO_OCUPADO")}
 return os.Rename(stage,hook)
}
func renpyRecover(exe string)error{
 d,e:=detectRenpy(exe);if e!=nil{return e}
 release,e:=renpyLock(d.Root);if e!=nil{return e};defer release()
 side:=filepath.Join(d.Root,renpySide);m,e:=renpyReadReceipt(side);if e!=nil{return e}
 if e=renpyCheckSessions(side);e!=nil{return e}
 if m.Profile!=d.Profile||m.GameRel!=d.GameRel{return errors.New("IA_RENPY_PERFIL_DISTINTO")}
 hook:=renpyHookAt(d)
 if d.Profile==renpyClassicProfile{
  if !renpyFile(hook){return errors.New("IA_RENPY_HOOK_NO_VERIFICADO")}
  sha,e:=digestFile(hook);if e!=nil||sha!=m.Boot{return errors.New("IA_RENPY_HOOK_ALTERADO")}
  compiled:=hook+"c";_,e=os.Lstat(compiled)
  if e!=nil&&!os.IsNotExist(e){return e}
  if e==nil&&!renpyFile(compiled){return errors.New("IA_RENPY_ARCHIVO_AJENO")}
  q,e:=os.MkdirTemp(side,"retired-");if e!=nil{return e}
  if renpyFile(compiled){if e=os.Rename(compiled,filepath.Join(q,renpyClassicHook+"c"));e!=nil{return e}}
  return os.Rename(hook,filepath.Join(q,renpyClassicHook))
 }
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

func renpyNeedsLegacyStart(d renpyDetection)bool{
 if d.Profile!=renpyClassicProfile{return false}
 if strings.HasPrefix(d.Version,"4")||strings.HasPrefix(d.Version,"5"){return true}
 // Frozen early releases may not expose a readable version literal.
 return d.Version==""&&(renpyFile(filepath.Join(d.Root,"python23.dll"))||renpyFile(filepath.Join(d.Root,"lib","python23.dll")))
}
func renpyLaunchCommand(exe string)(*exec.Cmd,error){
 d,e:=detectRenpy(exe);if e!=nil{return nil,e}
 abs,e:=filepath.Abs(exe);if e!=nil{return nil,e}
 side:=filepath.Join(d.Root,renpySide);m,e:=renpyReadReceipt(side);if e!=nil{return nil,e}
 if m.Profile!=d.Profile||m.GameRel!=d.GameRel{return nil,errors.New("IA_RENPY_PERFIL_DISTINTO")}
 hook:=renpyHookAt(d);if d.Profile!=renpyClassicProfile{hook=filepath.Join(hook,"boot.rpy")}
 if !renpyFile(hook){return nil,errors.New("IA_RENPY_HOOK_NO_VERIFICADO")}
 h,e:=digestFile(hook);if e!=nil||h!=m.Boot{return nil,errors.New("IA_RENPY_HOOK_ALTERADO")}
 if e=renpyCheckSessions(side);e!=nil{return nil,e}
 cmd:=exec.Command(abs)
 if renpyNeedsLegacyStart(d){
  if e=renpyVerifyClassicStart(side,m);e!=nil{return nil,e}
  cmd=exec.Command(abs,"--python",filepath.Join(side,"classic_entry.py"))
  for _,v:=range os.Environ(){
   k:=strings.ToUpper(strings.SplitN(v,"=",2)[0])
   if !strings.HasPrefix(k,"IA_RENPY_CLASSIC_")&&k!="PYTHONHOME"&&k!="PYTHONPATH"{cmd.Env=append(cmd.Env,v)}
  }
  cmd.Env=append(cmd.Env,"IA_RENPY_CLASSIC_ROOT="+d.Root,"IA_RENPY_CLASSIC_GAME="+d.gameDir())
 }
 cmd.Dir=d.Root;return cmd,nil
}
func renpyPlay(exe string)error{
 cmd,e:=renpyLaunchCommand(exe);if e!=nil{return e}
 if e=cmd.Start();e!=nil{return errors.New("IA_RENPY_INICIO_FALLO")}
 go func(){_ = cmd.Wait()}()
 return nil
}
