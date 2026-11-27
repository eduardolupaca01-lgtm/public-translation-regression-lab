package main

// Servidor v2: instalador propio para RPG Maker MV/MZ. Sin llamadas al
// instalador/ejecutable, registro o rutas de otra aplicación.
import(
 "archive/zip"
 "bytes"
 "crypto/sha256"
 "encoding/binary"
 "encoding/hex"
 "encoding/json"
 "errors"
 "flag"
 "fmt"
 "io"
 "os"
 "path"
 "path/filepath"
 "strings"
)

const (
 packageSchema="ia-traductora-package-v1"
 ownerSchema="ia-traductora-owner-v1"
 packageMagic="SERVIDOR2ZIPSHA1" // exactamente 16 bytes
 brandFolder="IA Traductora"
 pluginName="IATraductora"
 installerBuildID="RPG-MVMZ-R30-20261126"
 maxArchive=int64(900*1024*1024)
)
type packageManifest struct{
 Schema string `json:"schema"`
 Files map[string]string `json:"files"`
}
type ownerManifest struct{
 Schema string `json:"schema"`
 WorkerSHA string `json:"worker_sha256"`
 PluginSHA string `json:"plugin_sha256"`
 Product string `json:"product,omitempty"`
 VXACEHelperSHA string `json:"vxace_helper_sha256,omitempty"`
 VXACEPluginSHA string `json:"vxace_plugin_sha256,omitempty"`
 VXACEPluginBuild string `json:"vxace_plugin_build,omitempty"`
}
type installReceipt struct{
 Schema string `json:"schema"`
 BeforeSHA string `json:"before_sha256"`
 AfterSHA string `json:"after_sha256"`
 PluginSHA string `json:"plugin_sha256"`
 Status string `json:"status"`
}
type packageReader struct{ f *os.File; archive *zip.Reader; files map[string]*zip.File; manifest packageManifest }
func (p *packageReader)Close(){if p.f!=nil{_ =p.f.Close()}}
func hash(b []byte)string{h:=sha256.Sum256(b);return hex.EncodeToString(h[:])}
func ordinary(file string)bool{st,err:=os.Lstat(file);return err==nil&&st.Mode().IsRegular()&&st.Mode()&os.ModeSymlink==0}
func safeFile(name string)bool{
 return name!=""&&name==path.Clean(name)&&!strings.HasPrefix(name,"/")&&
 !strings.Contains(name,"\\")&&!strings.HasPrefix(name,"../")&&name!=".."&&
 !strings.HasPrefix(name,"./")&& !strings.Contains(name,":")
}
func readPackage(filename string)(*packageReader,error){
 f,err:=os.Open(filename);if err!=nil{return nil,err}
 good:=false;defer func(){if !good{_ = f.Close()}}()
 stat,err:=f.Stat();if err!=nil{return nil,err}
 if stat.Size()<56{return nil,errors.New("IA_FALTA_PAQUETE_NEURONAL")}
 footer:=make([]byte,56)
 if _,err=f.ReadAt(footer,stat.Size()-56);err!=nil{return nil,err}
 if string(footer[40:])!=packageMagic{return nil,errors.New("IA_PAQUETE_NO_ADJUNTADO")}
 size:=int64(binary.LittleEndian.Uint64(footer[:8]))
 if size<1024||size>maxArchive||size>stat.Size()-56{return nil,errors.New("IA_PAQUETE_TAMANO")}
 reader:=io.NewSectionReader(f,stat.Size()-56-size,size)
 digest:=sha256.New()
 if _,err=io.Copy(digest,reader);err!=nil{return nil,err}
 if !bytes.Equal(digest.Sum(nil),footer[8:40]){return nil,errors.New("IA_PAQUETE_SHA_INCORRECTO")}
 zr,err:=zip.NewReader(io.NewSectionReader(f,stat.Size()-56-size,size),size)
 if err!=nil{return nil,errors.New("IA_PAQUETE_ZIP_INVALIDO")}
 files:=map[string]*zip.File{};var sum int64
 for _,item:=range zr.File{
  if !safeFile(item.Name)||item.FileInfo().IsDir()||item.Mode()&os.ModeSymlink!=0||
    item.UncompressedSize64>uint64(maxArchive){return nil,errors.New("IA_PAQUETE_RUTA_PELIGROSA")}
  if _,exists:=files[item.Name];exists{return nil,errors.New("IA_PAQUETE_REPETIDO")}
  sum+=int64(item.UncompressedSize64)
  if sum>maxArchive||len(files)>65{return nil,errors.New("IA_PAQUETE_EXPANSION")}
  files[item.Name]=item
 }
 mf:=files["manifest.json"]
 if mf==nil{return nil,errors.New("IA_FALTA_MANIFIESTO")}
 raw,err:=readZip(mf,256*1024);if err!=nil{return nil,err}
 var manifest packageManifest
 if json.Unmarshal(raw,&manifest)!=nil||manifest.Schema!=packageSchema||
 len(manifest.Files)!=len(files)-1{return nil,errors.New("IA_MANIFIESTO_INVALIDO")}
 for filename,sha:=range manifest.Files{
  if !safeFile(filename)||files[filename]==nil||len(sha)!=64{
   return nil,errors.New("IA_ARCHIVOS_MANIFIESTO_INCORRECTOS")
  }
 }
 for _,name:=range []string{"IATraductora.exe","IATraductora.js","models/opus_ja_es/model.bin",
   "models/opus_ja_es/source.spm","models/opus_ja_es/target.spm",
   "models/opus_en_es/model.bin","models/opus_en_es/source.spm",
   "models/opus_en_es/target.spm"}{
  if files[name]==nil{return nil,errors.New("IA_MODELOS_NO_INCLUIDOS")}
 }
 // VX Ace support is optional for old MV/MZ packages, but the helper and
 // Ruby runtime must arrive together; never accept a half-packaged adapter.
 helperPresent:=files["vxace-helper.exe"]!=nil
 pluginPresent:=files["vxace/IATraductoraVXACE.rb"]!=nil
 if helperPresent!=pluginPresent{return nil,errors.New("IA_VXACE_PAQUETE_INCOMPLETO")}
 if helperPresent{
  if len(manifest.Files["vxace-helper.exe"])!=64||
     len(manifest.Files["vxace/IATraductoraVXACE.rb"])!=64{
   return nil,errors.New("IA_VXACE_MANIFIESTO_INVALIDO")
  }
 }
 good=true
 return &packageReader{f:f,archive:zr,files:files,manifest:manifest},nil
}
func readZip(item *zip.File,limit int64)([]byte,error){
 if item==nil||int64(item.UncompressedSize64)>limit{return nil,errors.New("IA_ARCHIVO_EXCESIVO")}
 reader,err:=item.Open();if err!=nil{return nil,err};defer reader.Close()
 b,err:=io.ReadAll(io.LimitReader(reader,limit+1));if err!=nil||int64(len(b))>limit{
  return nil,errors.New("IA_LECTURA_ARCHIVO")
 }
 return b,nil
}
// Recognize a native MZ compressed database, not an arbitrary .jsono file.
func porCompressedDatabase(content string) bool {
 js:=filepath.Join(content,"js")
 data:=filepath.Join(content,"data")
 for _,dir:=range []string{content,js,filepath.Join(js,"plugins"),data}{
  st,err:=os.Lstat(dir);if err!=nil||!st.IsDir()||st.Mode()&os.ModeSymlink!=0{return false}
 }
 for _,n:=range []string{"POR_DatabaseEncoder.js","lz-string.min.js"}{
  if !ordinary(filepath.Join(js,"plugins",n)){return false}
 }
 for _,n:=range []string{"System.jsono","Actors.jsono","CommonEvents.jsono","MapInfos.jsono"}{
  file:=filepath.Join(data,n);if !ordinary(file){return false}
  st,err:=os.Stat(file);if err!=nil||st.Size()<4||st.Size()>2*1024*1024{return false}
 }
 registry:=filepath.Join(js,"plugins.js")
 if !ordinary(registry){return false}
 st,err:=os.Stat(registry);if err!=nil||st.Size()>2*1024*1024{return false}
 raw,err:=os.ReadFile(registry);if err!=nil{return false}
 _,entries,err:=parseRegistry(raw);if err!=nil{return false}
 active:=map[string]bool{}
 for _,entry:=range entries{
  var name string;var status bool
  if json.Unmarshal(entry["name"],&name)==nil&&json.Unmarshal(entry["status"],&status)==nil&&status{active[name]=true}
 }
 if !active["POR_DatabaseEncoder"]||!active["lz-string.min"]{return false}
 raw,err=os.ReadFile(filepath.Join(data,"System.jsono"))
 if err!=nil||len(raw)%4!=0{return false}
 body:=bytes.TrimRight(raw,"=")
 if len(body)==0||len(raw)-len(body)>3{return false}
 for _,c:=range body{if !((c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='+'||c=='/'){return false}}
 return true
}
// Detect deployed engines by original file markers, without running game code.
func engineAt(content string) string {
 js:=filepath.Join(content,"js")
 mv:=ordinary(filepath.Join(js,"rpg_core.js"))
 mz:=ordinary(filepath.Join(js,"rmmz_core.js"))
 if mv&&mz{return "AMBIGUOUS"}
 if !ordinary(filepath.Join(js,"plugins.js")){return ""}
 plain:=ordinary(filepath.Join(content,"data","System.json"))
 if !plain&&!(mz&&porCompressedDatabase(content)){return ""}
 if mz {
  for _,n:=range []string{"rmmz_managers.js","rmmz_objects.js","rmmz_scenes.js","rmmz_windows.js"}{
   if !ordinary(filepath.Join(js,n)){return "AMBIGUOUS"}
  }
  for _,dir:=range []string{content,js,filepath.Join(content,"data")}{
   st,err:=os.Lstat(dir);if err!=nil||!st.IsDir()||st.Mode()&os.ModeSymlink!=0{return "AMBIGUOUS"}
  }
  return "MZ"
 }
 if mv{return "MV"}
 return ""
}
func detectGame(gameEXE string)(string,string,error){
 absolute,err:=filepath.Abs(gameEXE);if err!=nil||!strings.EqualFold(filepath.Ext(absolute),".exe")||
 !ordinary(absolute){return "","",errors.New("IA_SELECCIONA_GAME_EXE")}
 root:=filepath.Dir(absolute);st,err:=os.Lstat(root)
 if err!=nil||!st.IsDir()||st.Mode()&os.ModeSymlink!=0{
  return "","",errors.New("IA_JUEGO_RUTA_INVALIDA")
 }
 // Packed Cook Tool roots must not be mistaken for a loose RPG project.
 // The launch cache can be regenerated or removed by the vendor.
 if e:=cookToolPreflight(root);e!=nil{return "","",e}
 var chosen string
 for _,dir:=range []string{filepath.Join(root,"www"),root}{
  kind:=engineAt(dir)
  if kind=="AMBIGUOUS"{return "","",errors.New("IA_RPG_RUTAS_AMBIGUAS")}
  if kind!=""{
   if chosen!=""{return "","",errors.New("IA_RPG_RUTAS_AMBIGUAS")}
   chosen=dir
  }
 }
 if chosen==""{return "","",errors.New("IA_SOLO_RPG_MAKER_MV_MZ")}
 if info,err:=os.Lstat(filepath.Join(chosen,"js","plugins"));err!=nil||!info.IsDir()||
 info.Mode()&os.ModeSymlink!=0{return "","",errors.New("IA_CARPETA_PLUGINS_INVALIDA")}
 return root,chosen,nil
}
func parseRegistry(reg []byte)(int,[]map[string]json.RawMessage,error){
 // MV produces static var $plugins = [{...},...]; no eval and no code execution.
 text:=strings.TrimPrefix(string(bytes.TrimPrefix(reg,[]byte{0xef,0xbb,0xbf})),"//")
 loc:=strings.Index(text,"var $plugins")
 if loc<0{return -1,nil,errors.New("IA_REGISTRO_MV_NO_ESTATICO")}
 start:=strings.IndexByte(text[loc:],'[')
 if start<0{return -1,nil,errors.New("IA_REGISTRO_SIN_LISTA")}
 start+=loc
 // Use JSON decoder for the bounded array; no dynamic JS support.
 decoder:=json.NewDecoder(strings.NewReader(text[start:]))
 var entries []map[string]json.RawMessage
 if decoder.Decode(&entries)!=nil||len(entries)>500{
  return -1,nil,errors.New("IA_PLUGIN_JS_NO_ADMITIDO")
 }
 // Determine exact closing bracket while respecting strings and escapes.
 depth,quoted,escaped:=0,false,false
 finish:=-1
 for i:=start;i<len(text);i++{
  c:=text[i]
  if quoted{
   if escaped{escaped=false}else if c=='\\'{escaped=true}else if c=='"'{quoted=false}
   continue
  }
  if c=='"'{quoted=true}else if c=='['{depth++}else if c==']'{
   depth--;if depth==0{finish=i;break}
  }
 }
 if finish<0{return -1,nil,errors.New("IA_REGISTRO_INCOMPLETO")}
 return finish+len(string(reg))-len(text),entries,nil
}
func checkEntries(entries []map[string]json.RawMessage)(bool,error){
 installed:=false
 for _,entry:=range entries{
  var name string;var enabled bool
  if json.Unmarshal(entry["name"],&name)!=nil{return false,errors.New("IA_COMPLEMENTO_SIN_NOMBRE")}
  _=json.Unmarshal(entry["status"],&enabled)
  if strings.EqualFold(name,pluginName){
   if installed{return false,errors.New("IA_COMPLEMENTO_REGISTRADO_DUPLICADO")}
   if !enabled{return false,errors.New("IA_COMPLEMENTO_DESACTIVADO")}
   installed=true
  }
  if enabled&&strings.EqualFold(name,"TenshixgameRPGLive"){
   return false,errors.New("IA_MIGRACION_PREVIA_REQUERIDA")
  }
 }
 return installed,nil
}
func appendRegistry(reg []byte)([]byte,error){
 return appendRegistryParams(reg,map[string]string{})
}
func appendRegistryParams(reg []byte,params map[string]string)([]byte,error){
 finish,entries,err:=parseRegistry(reg);if err!=nil{return nil,err}
 already,err:=checkEntries(entries);if err!=nil{return nil,err}
 if already{return nil,errors.New("IA_PLUGIN_YA_REGISTRADO")}
 obj:=map[string]any{"name":pluginName,"status":true,
  "description":"IA Traductora: japonés/inglés a español (local)",
  "parameters":params}
 raw,_:=json.Marshal(obj)
 // Insert exactly before closing bracket. The original bytes are kept intact.
 prefix:=reg[:finish];suffix:=reg[finish:]
 sep:="";if len(entries)>0{sep=","}
 return append(append(append([]byte{},prefix...),[]byte(sep+"\n"+string(raw)+"\n")...),suffix...),nil
}
func writeAtomic(filename string,b []byte)error{
 parent:=filepath.Dir(filename)
 f,err:=os.CreateTemp(parent,".servidor-v2-")
 if err!=nil{return err}
 tmp:=f.Name();defer os.Remove(tmp)
 if _,err=f.Write(b);err!=nil{f.Close();return err}
 if err=f.Sync();err!=nil{f.Close();return err}
 if err=f.Close();err!=nil{return err}
 return os.Rename(tmp,filename)
}
func createNew(filename string,b []byte)error{
 f,err:=os.OpenFile(filename,os.O_CREATE|os.O_EXCL|os.O_WRONLY,0600);if err!=nil{return err}
 if _,err=f.Write(b);err!=nil{f.Close();return err}
 if err=f.Sync();err!=nil{f.Close();return err};return f.Close()
}
// Explicitly separate staging, Windows publication and recovery from the
// MV-specific installer. Existing game assets are never overwritten here.
func prepareSidecar(game string,pkg *packageReader)(string,error){
 return iaPrepareAndPublishSidecar(game,pkg)
}
func Install(gameEXE string,pkg *packageReader)error{
 if fingerprint,matched,vxErr:=detectVXAce(gameEXE);matched{
  if vxErr!=nil{return vxErr}
  return installVXAce(fingerprint,pkg)
 }
 root,content,err:=detectGame(gameEXE)
 if err!=nil{
  if packed,ok:=halvaRootFromDetection(gameEXE,err);ok{
   if _,_,e:=halvaInspect(packed);e==nil{return installHalva(packed,pkg)}
  }
  return err
 }
 registry:=filepath.Join(content,"js","plugins.js")
 jsfile:=filepath.Join(content,"js","plugins",pluginName+".js")
 old,err:=os.ReadFile(registry);if err!=nil||len(old)>4*1024*1024{
  return errors.New("IA_REGISTRO_NO_SE_PUEDE_LEER")
 }
 updated,err:=appendRegistry(old)
 var previous *migrationPlan
 if err!=nil {
  switch err.Error() {
  case "IA_PLUGIN_YA_REGISTRADO":
   return iaUpgradeOwnPlugin(root,content,old,pkg)
  case "IA_MIGRACION_PREVIA_REQUERIDA":
   if engineAt(content)=="MZ"{return errors.New("IA_MZ_MIGRACION_MANUAL_REQUERIDA")}
   previous,err=verifiedOldMigration(root,content,old)
   if err!=nil{return err}
   updated,err=appendRegistry(previous.OriginalRegistry)
   if err!=nil{return err}
  default:
   return err
  }
 }
 // A verified game recovered to its exact original registry must be
 // safely re-enabled/upgraded instead of falsely treating our JS as foreign.
 if ordinary(jsfile){return iaReinstallAfterRecovery(root,content,old,updated,pkg)}
 if _,e:=os.Lstat(jsfile);!os.IsNotExist(e){return errors.New("IA_COMPLEMENTO_AJENO_EXISTE")}
 script,err:=readZip(pkg.files["IATraductora.js"],1024*1024)
 if err!=nil||hash(script)!=pkg.manifest.Files["IATraductora.js"]{
  return errors.New("IA_PLUGIN_SHA_INCORRECTO")
 }
 if !bytes.Contains(script,[]byte("◆ IA Traductora · F10"))||
    bytes.Contains(script,[]byte("TENSHIXGAME RPG")){
  return errors.New("IA_PLUGIN_MARCA_ANTIGUA")
 }
 sidecar,err:=prepareSidecar(root,pkg)
 if err!=nil{return err}
 // All recovery data is written before changing the original registry.
 backup:=filepath.Join(sidecar,"install","original-plugins.js")
 if err=createNew(backup,old);err!=nil{return err}
 receipt:=installReceipt{Schema:"ia-traductora-install-v1",BeforeSHA:hash(old),
  AfterSHA:hash(updated),PluginSHA:hash(script),Status:"PREPARED"}
 recFile:=filepath.Join(sidecar,"install","receipt.json")
 recBytes,_:=json.MarshalIndent(receipt,"","  ")
 if err=createNew(recFile,recBytes);err!=nil{return err}
 if err=createNew(jsfile,script);err!=nil{return err}
 if err=writeAtomic(registry,updated);err!=nil{return err}
 receipt.Status="INSTALLED";recBytes,_=json.MarshalIndent(receipt,"","  ")
 if err=writeAtomic(recFile,recBytes);err!=nil{return err}
 // Postcondition: do not report success for different game resources.
 onDisk,_:=os.ReadFile(jsfile)
 list,_:=os.ReadFile(registry)
 if hash(onDisk)!=receipt.PluginSHA||hash(list)!=receipt.AfterSHA{
  return errors.New("IA_INSTALACION_NO_VERIFICADA")
 }
 if previous!=nil {
  if err=archiveOldMigration(previous,sidecar,registry,jsfile);err!=nil {
   // No deletion or forced overwrite. A valid new plugin is installed,
   // but do not claim completion while the old runtime remains visible.
   return fmt.Errorf("IA_MIGRACION_NO_SE_PUDO_ARCHIVAR: %w",err)
  }
 }
 return verifiedNewInstallation(root,content,list)
}
// The receipt may be valid for an older version. Verify the bytes against
// the selected package before announcing successful installation.
func installedPackageIdentity(gameEXE string,pkg *packageReader)(string,error){
 if fingerprint,matched,vxErr:=detectVXAce(gameEXE);matched{
  if vxErr!=nil{return "",vxErr}
  return installedVXAceIdentity(fingerprint,pkg)
 }
 root,content,err:=detectGame(gameEXE)
 if err!=nil{
  if packed,ok:=halvaRootFromDetection(gameEXE,err);ok{return halvaIdentity(packed,pkg)}
  return "",err
 }
 script:=filepath.Join(content,"js","plugins",pluginName+".js")
 worker:=filepath.Join(root,brandFolder,".local","Rpg","engine","IATraductora.exe")
 if !ordinary(script)||!ordinary(worker){return "",errors.New("IA_INSTALACION_VERSION_NO_VERIFICADA")}
 source,err:=os.ReadFile(script)
 if err!=nil||hash(source)!=pkg.manifest.Files["IATraductora.js"]{
  return "",errors.New("IA_INSTALACION_VERSION_NO_VERIFICADA")
 }
 digest,err:=digestFile(worker)
 if err!=nil||digest!=pkg.manifest.Files["IATraductora.exe"]{
  return "",errors.New("IA_INSTALACION_MOTOR_VERSION_NO_VERIFICADA")
 }
 build:="SIN-MARCA"
 const marker="var BUILD_ID=\""
 if i:=bytes.Index(source,[]byte(marker));i>=0{
  rest:=source[i+len(marker):]
  if j:=bytes.IndexByte(rest,'"');j>0&&j<=32{
   v:=string(rest[:j]);safe:=true
   for _,r:=range v{if !(r>='A'&&r<='Z'||r>='0'&&r<='9'||r=='-'){safe=false;break}}
   if safe{build=v}
  }
 }
 return build+" SHA256="+hash(source),nil
}
func main(){
 exe:=flag.String("game","","Game.exe de una copia cerrada de RPG Maker MV, MZ o VX Ace")
 payload:=flag.String("package","","Ejecutable Servidor.exe con paquete firmado; por defecto el propio ejecutable")
 recoverGame:=flag.Bool("recover",false,"Recuperar el registro original de complementos MV/MZ (no necesita modelos)")
 inspect:=flag.Bool("inspect",false,"Diagnóstico RPG de solo lectura, sin modelos ni ejecución del juego")
 flag.Parse()
 if *inspect {
  if *exe==""||*recoverGame{fmt.Fprintln(os.Stderr,"IA_INSPECCION_GAME_EXE_REQUERIDO");os.Exit(1)}
  kind,e:=detectInstallTarget(*exe)
  if e!=nil{fmt.Println(e.Error());os.Exit(2)}
  fmt.Println("IA_RPG_RECURSOS_ACCESIBLES motor="+kind+" version="+installerBuildID)
  return
 }
 if *recoverGame{
  if *exe==""{fmt.Fprintln(os.Stderr,"IA_RECUPERACION_GAME_EXE_REQUERIDO");os.Exit(1)}
  if err:=RecoverGame(*exe);err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}
  fmt.Println("IA_RECUPERACION_REGISTRO_ORIGINAL_VERIFICADA")
  return
 }
 if *exe==""{runUI();return}
 source:=*payload;if source==""{var err error;source,err=os.Executable();if err!=nil{fmt.Fprintln(os.Stderr,"IA_EXE_NO_DISPONIBLE");os.Exit(1)}}
 p,err:=readPackage(source)
 if err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}
 defer p.Close()
 if err=Install(*exe,p);err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}
 identity,err:=installedPackageIdentity(*exe,p)
 if err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}
 fmt.Println("[IA_VERSION_INSTALADA] "+identity)
 fmt.Println("IA Traductora: instalación RPG verificada. Reinicia el juego.")
}
