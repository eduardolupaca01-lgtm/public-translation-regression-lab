package main

// Native, reversible modification of plaintext Brotli/ZIP Halva packages
// in an authorized CLOSED COPY. Never decrypt, change the publisher's
// configuration, bypass cache verification, or change the original launcher.
import (
 "archive/zip"
 "bytes"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "os"
 "path/filepath"
 "regexp"
 "strings"
 "unicode/utf8"

 "github.com/andybalholm/brotli"
)

const halvaMax = 64*1024*1024
const halvaReceiptSchema = "ia-traductora-halva-install-v1"
type plainHalva struct{
 original []byte
 z *zip.Reader
 entries map[string]*zip.File
}
type halvaReceipt struct{
 Schema string `json:"schema"`
 BeforeSHA string `json:"before_sha256"`
 AfterSHA string `json:"after_sha256"`
 PluginSHA string `json:"plugin_sha256"`
}
var halvaMainSetup=regexp.MustCompile(`PluginManager\s*\.\s*setup\s*\(\s*\$plugins\s*\)`)

func halvaReadFile(file string,limit int64)([]byte,error){
 if !ordinary(file){return nil,errors.New("IA_HALVA_ARCHIVO_NO_ORDINARIO")}
 f,e:=os.Open(file);if e!=nil{return nil,e};defer f.Close()
 info,e:=f.Stat();if e!=nil||info.Size()<1||info.Size()>limit{return nil,errors.New("IA_HALVA_TAMANO")}
 b,e:=io.ReadAll(io.LimitReader(f,limit+1))
 if e!=nil||int64(len(b))>limit{return nil,errors.New("IA_HALVA_LECTURA")}
 return b,nil
}

func halvaName(name string) (string,bool) {
 normalized:=strings.ReplaceAll(name,"\\","/")
 trimmed:=strings.TrimSuffix(normalized,"/")
 if !utf8.ValidString(trimmed)||!safeFile(trimmed)||trimmed=="."||strings.ContainsAny(trimmed,"\x00\r\n") {return "",false}
 for _,p:=range strings.Split(trimmed,"/"){
  if strings.HasSuffix(p,".")||strings.HasSuffix(p," ")||p==""{return "",false}
 }
 return strings.ToLower(trimmed),true
}

func halvaDecode(raw []byte)(*plainHalva,error){
 if len(raw)==0||len(raw)>halvaMax{return nil,errors.New("IA_HALVA_TAMANO")}
 unpacked,e:=io.ReadAll(io.LimitReader(brotli.NewReader(bytes.NewReader(raw)),halvaMax+1))
 if e!=nil||len(unpacked)>halvaMax||!bytes.HasPrefix(unpacked,[]byte{'P','K',3,4}){
  return nil,errors.New("IA_HALVA_NO_ES_BROTLI_ZIP_PLANO")
 }
 z,e:=zip.NewReader(bytes.NewReader(unpacked),int64(len(unpacked)))
 // Windows .NET writes backslashes in historical archives. Accept only
 // after independently validating every normalized entry.
 if (e!=nil&&!errors.Is(e,zip.ErrInsecurePath))||z==nil||len(z.File)==0||len(z.File)>12000{
  return nil,errors.New("IA_HALVA_ZIP_INVALIDO")
 }
 entries:=map[string]*zip.File{};var total uint64
 for _,item:=range z.File{
  key,ok:=halvaName(item.Name)
  if !ok||entries[key]!=nil||item.Flags&1!=0||item.Mode()&os.ModeSymlink!=0||
     (item.Method!=zip.Store&&item.Method!=zip.Deflate)||item.UncompressedSize64>halvaMax{
   return nil,errors.New("IA_HALVA_ENTRADA_NO_ADMITIDA")
  }
  total+=item.UncompressedSize64;if total>halvaMax{return nil,errors.New("IA_HALVA_EXPANSION")}
  entries[key]=item
 }
 return &plainHalva{original:raw,z:z,entries:entries},nil
}
func halvaOpen(file string)(*plainHalva,error){
 raw,e:=halvaReadFile(file,halvaMax);if e!=nil{return nil,e}
 return halvaDecode(raw)
}
func halvaRead(a *plainHalva,name string,limit int64)([]byte,error){
 return readZip(a.entries[strings.ToLower(name)],limit)
}
func halvaPackDir(root string)string{return filepath.Join(root,"GamePackages")}
func halvaEngineFile(root string)string{return filepath.Join(halvaPackDir(root),"EnginePackage.halva")}
func halvaRecordDir(root string)string{return filepath.Join(root,brandFolder,"install","halva")}

func halvaRootFromDetection(gameEXE string,e error)(string,bool){
 if e==nil||!strings.HasPrefix(e.Error(),cookToolPackedCode+":"){return "",false}
 abs,err:=filepath.Abs(gameEXE);if err!=nil{return "",false}
 root:=filepath.Dir(abs)
 // Reject directory symlinks/junctions in every ancestor before resolving.
 // Windows may expand an ordinary 8.3 name (RUNNER~1) to its long name;
 // compare physical directory identity rather than the spelling.
 for p:=root;;p=filepath.Dir(p){
  info,e:=os.Lstat(p)
  if e!=nil||!info.IsDir()||info.Mode()&os.ModeSymlink!=0{return "",false}
  if filepath.Dir(p)==p{break}
 }
 real,err:=filepath.EvalSymlinks(root)
 if err!=nil{return "",false}
 original,e:=os.Lstat(root);if e!=nil{return "",false}
 canonical,e:=os.Lstat(real)
 if e!=nil||!canonical.IsDir()||canonical.Mode()&os.ModeSymlink!=0||!os.SameFile(original,canonical){return "",false}
 return real,true
}

// Only the original two small, plain archives are inspected. Unsupported
// layouts (including Halva2 or encrypted payloads) stay rejected.
func halvaInspect(root string)(string,*plainHalva,error){
 engine,e:=halvaOpen(halvaEngineFile(root));if e!=nil{return "",nil,e}
 db,e:=halvaOpen(filepath.Join(halvaPackDir(root),"DatabasePackage.halva"));if e!=nil{return "",nil,e}
 mv,mz:=engine.entries["js/rpg_core.js"]!=nil,engine.entries["js/rmmz_core.js"]!=nil
 if mv==mz{return "",nil,errors.New("IA_HALVA_MOTOR_AMBIGUO")}
 kind,prefix:="MV","rpg_";if mz{kind,prefix="MZ","rmmz_"}
 for _,suffix:=range []string{"core.js","managers.js","objects.js","scenes.js","windows.js"}{
  if engine.entries["js/"+prefix+suffix]==nil{return "",nil,errors.New("IA_HALVA_MOTOR_INCOMPLETO")}
 }
 main,e:=halvaRead(engine,"js/main.js",1024*1024)
 if e!=nil||!utf8.Valid(main)||!halvaMainSetup.Match(main){return "",nil,errors.New("IA_HALVA_ARRANQUE_NO_ESTANDAR")}
 registry,e:=halvaRead(engine,"js/plugins.js",4*1024*1024)
 if e!=nil{return "",nil,e}
 _,entries,e:=parseRegistry(registry);if e!=nil{return "",nil,e}
 if _,e=checkEntries(entries);e!=nil{return "",nil,e}
 system,e:=halvaRead(db,"data/system.json",4*1024*1024)
 var obj map[string]json.RawMessage
 if e!=nil||json.Unmarshal(bytes.TrimPrefix(system,[]byte{0xef,0xbb,0xbf}),&obj)!=nil||obj==nil{
  return "",nil,errors.New("IA_HALVA_DB_NO_ADMITIDA")
 }
 return kind,engine,nil
}

func detectInstallTarget(gameEXE string)(string,error){
 if _,matched,vxErr:=detectVXAce(gameEXE);matched{
  if vxErr!=nil{return "",vxErr}
  return "VX Ace",nil
 }
 root,content,e:=detectGame(gameEXE)
 if e==nil{return engineAt(content),nil}
 if packed,ok:=halvaRootFromDetection(gameEXE,e);ok{
  root=packed
  if kind,_,probe:=halvaInspect(root);probe==nil{return kind+" Halva",nil}
 }
 return "",e
}

// No extraction or execution of game source. Preserve all original entries,
// names (including Windows separators), raw compressed bytes and order.
// Append exactly one owned plugin; leave all other parameters untouched.
func halvaPatched(engine *plainHalva,root string,script []byte)([]byte,error){
 registry,e:=halvaRead(engine,"js/plugins.js",4*1024*1024);if e!=nil{return nil,e}
 if engine.entries["js/plugins/iatraductora.js"]!=nil{return nil,errors.New("IA_HALVA_COMPLEMENTO_EXISTENTE")}
 updated,e:=appendRegistryParams(registry,map[string]string{"iaHalvaRoot":root});if e!=nil{return nil,e}
 var plain bytes.Buffer
 zw:=zip.NewWriter(&plain)
 if e=zw.SetComment(engine.z.Comment);e!=nil{return nil,e}
 originalRegistry:=engine.entries["js/plugins.js"]
 for _,item:=range engine.z.File{
  if item==originalRegistry{
   hdr:=item.FileHeader
   hdr.Method=zip.Store;hdr.Extra=nil
   out,e:=zw.CreateHeader(&hdr);if e!=nil{return nil,e}
   if _,e=out.Write(updated);e!=nil{return nil,e}
  }else if e=zw.Copy(item);e!=nil{return nil,e}
 }
 pluginPath:="js/plugins/IATraductora.js"
 if strings.Contains(originalRegistry.Name,"\\"){pluginPath=strings.ReplaceAll(pluginPath,"/","\\")}
 out,e:=zw.CreateHeader(&zip.FileHeader{Name:pluginPath,Method:zip.Store})
 if e!=nil{return nil,e}
 if _,e=out.Write(script);e!=nil{return nil,e}
 if e=zw.Close();e!=nil{return nil,e}
 if plain.Len()>halvaMax{return nil,errors.New("IA_HALVA_EXPANSION")}
 var encoded bytes.Buffer
 bw:=brotli.NewWriterLevel(&encoded,5)
 if _,e=bw.Write(plain.Bytes());e!=nil{_ =bw.Close();return nil,e}
 if e=bw.Close();e!=nil{return nil,e}
 result:=encoded.Bytes()
 after,e:=halvaDecode(result);if e!=nil{return nil,e}
 if len(after.entries)!=len(engine.entries)+1{return nil,errors.New("IA_HALVA_REEMPAQUETADO_INVALIDO")}
 for key,before:=range engine.entries{
  next:=after.entries[key]
  if next==nil||next.Name!=before.Name{return nil,errors.New("IA_HALVA_ENTRADA_ALTERADA")}
  if key!="js/plugins.js"&&(next.CRC32!=before.CRC32||next.UncompressedSize64!=before.UncompressedSize64){
   return nil,errors.New("IA_HALVA_ENTRADA_ALTERADA")
  }
 }
 got,e:=halvaRead(after,"js/plugins.js",4*1024*1024)
 if e!=nil||!bytes.Equal(got,updated){return nil,errors.New("IA_HALVA_REGISTRO_NO_VERIFICADO")}
 got,e=halvaRead(after,"js/plugins/iatraductora.js",1024*1024)
 if e!=nil||!bytes.Equal(got,script){return nil,errors.New("IA_HALVA_JS_NO_VERIFICADO")}
 return result,nil
}

func halvaSHAValid(s string)bool{
 if len(s)!=64{return false}
 for _,c:=range s{if !(c>='0'&&c<='9'||c>='a'&&c<='f'){return false}}
 return true
}
func readHalvaReceipt(root string)(halvaReceipt,error){
 var r halvaReceipt
 dir:=halvaRecordDir(root)
 for _,p:=range []string{filepath.Join(root,brandFolder),filepath.Join(root,brandFolder,"install"),dir}{
  info,e:=os.Lstat(p);if e!=nil||!info.IsDir()||info.Mode()&os.ModeSymlink!=0{return r,errors.New("IA_HALVA_RECIBO_NO_VERIFICADO")}
 }
 b,e:=halvaReadFile(filepath.Join(dir,"receipt.json"),4096)
 if e!=nil||json.Unmarshal(b,&r)!=nil||r.Schema!=halvaReceiptSchema||
    !halvaSHAValid(r.BeforeSHA)||!halvaSHAValid(r.AfterSHA)||!halvaSHAValid(r.PluginSHA)||r.BeforeSHA==r.AfterSHA{
  return r,errors.New("IA_HALVA_RECIBO_NO_VERIFICADO")
 }
 return r,nil
}
func halvaKeep(file string,want []byte)error{
 if _,e:=os.Lstat(file);os.IsNotExist(e){return createNew(file,want)}
 b,e:=halvaReadFile(file,halvaMax)
 if e!=nil||!bytes.Equal(b,want){return errors.New("IA_HALVA_RESPALDO_EXISTENTE_DISTINTO")}
 return nil
}
func halvaSaved(root string,r halvaReceipt)([]byte,[]byte,error){
 dir:=halvaRecordDir(root)
 before,e:=halvaReadFile(filepath.Join(dir,"original.halva"),halvaMax)
 if e!=nil||hash(before)!=r.BeforeSHA{return nil,nil,errors.New("IA_HALVA_RESPALDO_ALTERADO")}
 after,e:=halvaReadFile(filepath.Join(dir,"traducido.halva"),halvaMax)
 if e!=nil||hash(after)!=r.AfterSHA{return nil,nil,errors.New("IA_HALVA_COPIA_ALTERADA")}
 return before,after,nil
}

func installHalva(root string,pkg *packageReader)error{
 _,engine,e:=halvaInspect(root);if e!=nil{return e}
 // All state is prepared and verified before the one game-file publication.
 script,e:=readZip(pkg.files["IATraductora.js"],1024*1024)
 if e!=nil||hash(script)!=pkg.manifest.Files["IATraductora.js"]||!bytes.Contains(script,[]byte("◆ IA Traductora · F10")){
  return errors.New("IA_PLUGIN_SHA_INCORRECTO")
 }
 folder:=filepath.Join(root,brandFolder)
 receiptPath:=filepath.Join(halvaRecordDir(root),"receipt.json")
 var r halvaReceipt;var after []byte
 if _,e=os.Lstat(receiptPath);!os.IsNotExist(e){
  r,e=readHalvaReceipt(root);if e!=nil{return e}
  if r.PluginSHA!=hash(script){return errors.New("IA_HALVA_VERSION_EXISTENTE_CONSERVADA")}
  if e=iaCheckEngine(folder,pkg);e!=nil{return e}
  _,after,e=halvaSaved(root,r);if e!=nil{return e}
 }else{
  after,e=halvaPatched(engine,root,script);if e!=nil{return e}
  folder,e=prepareSidecar(root,pkg);if e!=nil{return e}
  if e=iaMakeSafeDirs(folder,filepath.Join("install","halva"));e!=nil{return e}
  dir:=halvaRecordDir(root)
  if e=halvaKeep(filepath.Join(dir,"original.halva"),engine.original);e!=nil{return e}
  if e=halvaKeep(filepath.Join(dir,"traducido.halva"),after);e!=nil{return e}
  r=halvaReceipt{Schema:halvaReceiptSchema,BeforeSHA:hash(engine.original),AfterSHA:hash(after),PluginSHA:hash(script)}
  raw,_:=json.MarshalIndent(r,"","  ")
  if e=createNew(receiptPath,raw);e!=nil{return e}
 }
 current,e:=halvaReadFile(halvaEngineFile(root),halvaMax);if e!=nil{return e}
 if hash(current)==r.AfterSHA{return nil}
 if hash(current)!=r.BeforeSHA{return errors.New("IA_HALVA_PAQUETE_CAMBIADO")}
 if e=writeAtomic(halvaEngineFile(root),after);e!=nil{return errors.New("IA_HALVA_PUBLICACION_FALLIDA")}
 if b,e:=halvaReadFile(halvaEngineFile(root),halvaMax);e!=nil||hash(b)!=r.AfterSHA{
  return errors.New("IA_HALVA_POSTCONDICION_NO_VERIFICADA")
 }
 return nil
}

func halvaIdentity(root string,pkg *packageReader)(string,error){
 r,e:=readHalvaReceipt(root);if e!=nil{return "",e}
 if r.PluginSHA!=pkg.manifest.Files["IATraductora.js"]{return "",errors.New("IA_HALVA_VERSION_NO_VERIFICADA")}
 if e=iaCheckEngine(filepath.Join(root,brandFolder),pkg);e!=nil{return "",e}
 if _,_,e=halvaSaved(root,r);e!=nil{return "",e}
 kind,engine,e:=halvaInspect(root);if e!=nil||hash(engine.original)!=r.AfterSHA{return "",errors.New("IA_HALVA_VERSION_NO_VERIFICADA")}
 script,e:=halvaRead(engine,"js/plugins/iatraductora.js",1024*1024)
 if e!=nil||hash(script)!=r.PluginSHA{return "",errors.New("IA_HALVA_JS_NO_VERIFICADO")}
 return fmt.Sprintf("%s %s-HALVA SHA256=%s",installerBuildID,kind,r.PluginSHA),nil
}
func recoverHalva(root string)error{
 r,e:=readHalvaReceipt(root);if e!=nil{return e}
 before,_,e:=halvaSaved(root,r);if e!=nil{return e}
 current,e:=halvaReadFile(halvaEngineFile(root),halvaMax);if e!=nil{return e}
 if hash(current)==r.BeforeSHA{return nil}
 if hash(current)!=r.AfterSHA{return errors.New("IA_HALVA_PAQUETE_CAMBIADO")}
 if e=writeAtomic(halvaEngineFile(root),before);e!=nil{return e}
 if b,e:=halvaReadFile(halvaEngineFile(root),halvaMax);e!=nil||hash(b)!=r.BeforeSHA{return errors.New("IA_HALVA_RECUPERACION_NO_VERIFICADA")}
 return nil
}
