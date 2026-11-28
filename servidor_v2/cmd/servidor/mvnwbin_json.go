package main

// A separate offline localization trial for an opaque MV/NWBin title.
// The original title is never executed or changed. Do not modify binaries,
// loader, manifest, protection logic, event scripts, choices or save files.
import (
 "bytes"
 "context"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "io/fs"
 "os"
 "os/exec"
 "path/filepath"
 "reflect"
 "regexp"
 "sort"
 "strings"
 "time"
)

const mvJSONSchema="ia-mv-json-pilot-v1"
const mvJSONMarker="IA_COPIA_JSON_INCOMPLETA.txt"
var mvJSONName=regexp.MustCompile("^(?:Map[0-9]{3,6})\\.json$")
var mvJSONControl=regexp.MustCompile("(?i)\\\\(?:[CVNPI]\\[[0-9]{1,6}\\]|G|[.!|^$<>{}\\\\])|\\r\\n|\\r|\\n")
var mvJSONDigits=regexp.MustCompile("[0-9０-９]+")
func mvJSONError(code string)error{return errors.New("IA_MV_JSON_"+code)}
type mvJSONRequest struct{
 Schema string `json:"schema"`
 Content string `json:"content"`
 Map string `json:"map"`
 Before string `json:"before_sha256"`
}
type mvJSONReport struct{
 Schema string `json:"schema"`
 Map string `json:"map"`
 Before string `json:"before_sha256"`
 After string `json:"after_sha256"`
 Lines int `json:"translated_lines"`
 Eligible int `json:"eligible_lines"`
 Skipped int `json:"skipped_lines"`
 Rejected int `json:"rejected_lines"`
 Units int `json:"unique_units"`
 New int `json:"new_translations"`
 Hits int `json:"cache_hits"`
}
func mvJSONSource(exe string)(root,content string,err error){
 _,_,e:=detectGame(exe)
 if e==nil||e.Error()!=mvnwbinExtensionUnavailable{return "","",mvJSONError("FORMATO_NO_ADMITIDO")}
 abs,e:=filepath.Abs(exe);if e!=nil||!ordinary(abs)||!vxaceCloneOrdinaryPath(abs){return "","",mvJSONError("EXE_INVALIDO")}
 root=filepath.Dir(abs)
 if vxaceCloneCheckAncestors(root)!=nil{return "","",mvJSONError("RUTA_NO_VERIFICADA")}
 for _,dir:=range []string{filepath.Join(root,"www"),root}{
  if match,e:=mvnwbinProfile(root,dir);match&&e!=nil&&e.Error()==mvnwbinExtensionUnavailable{
   if content!=""{return "","",mvJSONError("RUTA_NO_VERIFICADA")}
   content=dir
  }
 }
 if content==""{return "","",mvJSONError("FORMATO_NO_ADMITIDO")}
 return
}
func mvJSONRead(file string,limit int64)([]byte,error){
 if !ordinary(file)||!vxaceCloneOrdinaryPath(file)||vxaceCloneCheckAncestors(filepath.Dir(file))!=nil{return nil,mvJSONError("ARCHIVO_NO_VERIFICADO")}
 f,e:=os.Open(file);if e!=nil{return nil,e};defer f.Close()
 raw,e:=io.ReadAll(io.LimitReader(f,limit+1))
 if e!=nil||len(raw)==0||int64(len(raw))>limit{return nil,mvJSONError("ARCHIVO_NO_VERIFICADO")}
 return raw,nil
}
func mvJSONDecode(raw []byte)(any,error){
 dec:=json.NewDecoder(bytes.NewReader(bytes.TrimPrefix(raw,[]byte{0xef,0xbb,0xbf})))
 dec.UseNumber()
 var obj any
 if e:=dec.Decode(&obj);e!=nil{return nil,mvJSONError("JSON_INVALIDO")}
 var extra any
 if e:=dec.Decode(&extra);e!=io.EOF{return nil,mvJSONError("JSON_INVALIDO")}
 return obj,nil
}
func mvJSONStart(content string)(string,error){
 raw,e:=mvJSONRead(filepath.Join(content,"data","System.json"),16*1024*1024);if e!=nil{return "",e}
 var system struct{Start int `json:"startMapId"`}
 if json.Unmarshal(bytes.TrimPrefix(raw,[]byte{0xef,0xbb,0xbf}),&system)!=nil||system.Start<1||system.Start>999999{return "",mvJSONError("MAPA_INICIAL_INVALIDO")}
 return fmt.Sprintf("Map%03d.json",system.Start),nil
}
// Collect exactly the native display parameter arrays. Any structural
// variation outside those fields is rejected by the independent Go verifier.
func mvJSONDisplay(doc any)([][]any,error){
 obj,ok:=doc.(map[string]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
 events,ok:=obj["events"].([]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
 var fields [][]any
 for _,ev:=range events{
  if ev==nil{continue}
  event,ok:=ev.(map[string]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
  pages,ok:=event["pages"].([]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
  for _,pg:=range pages{
   page,ok:=pg.(map[string]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
   list,ok:=page["list"].([]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
   for _,c:=range list{
    cmd,ok:=c.(map[string]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
    code,ok:=cmd["code"].(json.Number);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
    if _,e:=code.Int64();e!=nil{return nil,mvJSONError("MAPA_INVALIDO")}
    if code!="401"&&code!="405"{continue}
    params,ok:=cmd["parameters"].([]any);if !ok||len(params)!=1{return nil,mvJSONError("MAPA_INVALIDO")}
    if _,ok=params[0].(string);!ok{return nil,mvJSONError("MAPA_INVALIDO")}
    fields=append(fields,params)
   }
  }
 }
 return fields,nil
}
func mvJSONSameFormatting(a,b string)bool{
 if strings.TrimSpace(b)==""||len(b)>1800*6{return false}
 if !reflect.DeepEqual(mvJSONControl.FindAllString(a,-1),mvJSONControl.FindAllString(b,-1)){return false}
 // Keep digits (including fullwidth digits, which can be normalized by
 // the neural validator) and prevent new executable/control delimiters.
 digits:=func(s string)[]string{
  s=strings.Map(func(r rune)rune{if r>='０'&&r<='９'{return r-'０'+'0'};return r},s)
  out:=mvJSONDigits.FindAllString(s,-1)
  for i,n:=range out{n=strings.TrimLeft(n,"0");if n==""{n="0"};out[i]=n}
  sort.Strings(out);return out
 }
 if !reflect.DeepEqual(digits(a),digits(b)){return false}
 return !strings.ContainsAny(mvJSONControl.ReplaceAllString(b,""),"\\<>{}[]\x00")
}
func mvJSONVerifyMap(before,after []byte)(int,error){
 a,e:=mvJSONDecode(before);if e!=nil{return 0,e}
 b,e:=mvJSONDecode(after);if e!=nil{return 0,e}
 x,e:=mvJSONDisplay(a);if e!=nil{return 0,e}
 y,e:=mvJSONDisplay(b);if e!=nil||len(x)!=len(y){return 0,mvJSONError("ESTRUCTURA_CAMBIADA")}
 changed:=0
 for i:=range x{
  original,result:=x[i][0].(string),y[i][0].(string)
  if original!=result{
   if !mvJSONSameFormatting(original,result){return 0,mvJSONError("CONTROLES_CAMBIADOS")}
   changed++
  }
  x[i][0]="";y[i][0]=""
 }
 if !reflect.DeepEqual(a,b){return 0,mvJSONError("ESTRUCTURA_CAMBIADA")}
 return changed,nil
}
func mvJSONClonePlan(root,exe string)([]vxaceCloneEntry,uint64,error){
 var entries []vxaceCloneEntry
 var total uint64
 seen:=map[string]bool{}
 e:=filepath.WalkDir(root,func(p string,d fs.DirEntry,walkErr error)error{
  if walkErr!=nil{return mvJSONError("COPIA_NO_LEIBLE")}
  if p==root{return nil}
  rel,e:=filepath.Rel(root,p);if e!=nil||!safeFile(filepath.ToSlash(rel)){return mvJSONError("RUTA_NO_VERIFICADA")}
  for _,part:=range strings.Split(filepath.ToSlash(rel),"/"){
   if strings.HasSuffix(part,".")||strings.HasSuffix(part," "){return mvJSONError("RUTA_NO_VERIFICADA")}
  }
  key:=strings.ToLower(filepath.ToSlash(rel))
  if key==strings.ToLower(brandFolder)||key==strings.ToLower(mvJSONMarker)||strings.HasPrefix(key,".ia-traductora-stage-"){
   return mvJSONError("COPIA_PREVIA_NO_ADMITIDA")
  }
  if seen[key]||!vxaceCloneOrdinaryPath(p)||d.Type()&os.ModeSymlink!=0{return mvJSONError("RUTA_NO_VERIFICADA")}
  seen[key]=true
  st,e:=d.Info();if e!=nil||!st.IsDir()&&!st.Mode().IsRegular(){return mvJSONError("RUTA_NO_VERIFICADA")}
  if !st.IsDir(){
   if st.Size()<0||uint64(st.Size())>vxaceCloneMaxBytes-total{return mvJSONError("COPIA_EXCESIVA")}
   total+=uint64(st.Size())
  }
  if len(entries)>=vxaceCloneMaxFiles{return mvJSONError("COPIA_EXCESIVA")}
  if !strings.EqualFold(p,exe){entries=append(entries,vxaceCloneEntry{rel,st})}
  return nil
 })
 return entries,total,e
}
func mvJSONCopyEntry(from,to string,info os.FileInfo)error{
 now,e:=os.Lstat(from)
 if e!=nil||!os.SameFile(now,info)||!vxaceCloneOrdinaryPath(from){return mvJSONError("ORIGEN_CAMBIADO")}
 if info.IsDir(){
  if !now.IsDir()||vxaceCloneCheckAncestors(from)!=nil||vxaceCloneCheckAncestors(filepath.Dir(to))!=nil{return mvJSONError("RUTA_NO_VERIFICADA")}
  return os.Mkdir(to,0700)
 }
 if !vxaceSameReplaceFile(now,info){return mvJSONError("ORIGEN_CAMBIADO")}
 if e=vxaceCloneFile(from,to);e!=nil{return e}
 now,e=os.Lstat(from);if e!=nil||!vxaceSameReplaceFile(now,info){return mvJSONError("ORIGEN_CAMBIADO")}
 return nil
}
func mvJSONCopyPilot(exe string,pkg *packageReader)(string,mvJSONReport,error){
 var report mvJSONReport
 root,content,e:=mvJSONSource(exe);if e!=nil{return "",report,e}
 if pkg==nil{return "",report,mvJSONError("PAQUETE_INCOMPLETO")}
 exe,e=filepath.Abs(exe);if e!=nil{return "",report,e}
 parent:=filepath.Dir(root)
 if parent==root||vxaceCloneCheckAncestors(parent)!=nil{return "",report,mvJSONError("DESTINO_INVALIDO")}
 mapName,e:=mvJSONStart(content);if e!=nil{return "",report,e}
 if !mvJSONName.MatchString(mapName){return "",report,mvJSONError("MAPA_INICIAL_INVALIDO")}
 sourceMap:=filepath.Join(content,"data",mapName)
 before,e:=mvJSONRead(sourceMap,16*1024*1024);if e!=nil{return "",report,e}
 tree,e:=mvJSONDecode(before);if e!=nil{return "",report,e}
 if _,e=mvJSONDisplay(tree);e!=nil{return "",report,e}
 entries,total,e:=mvJSONClonePlan(root,exe);if e!=nil{return "",report,e}
 if e=vxaceCheckDiskSpace(parent,total+2*1024*1024*1024);e!=nil{return "",report,e}
 exeInfo,e:=os.Lstat(exe);if e!=nil{return "",report,e}
 rel,e:=filepath.Rel(root,content);if e!=nil||rel!="www"&&rel!="."{return "",report,mvJSONError("RUTA_NO_VERIFICADA")}
 // Verify the unmodified original startup independently before and
 // after the copy. Optional resources remain exactly as originally
 // provided: never manufacture a missing guard or replace a registry.
 protected:=map[string]string{}
 required:=[]string{exe,filepath.Join(root,"package.json"),filepath.Join(content,"index.html"),filepath.Join(content,"js","main.js"),filepath.Join(content,"js","plugins.bin"),sourceMap}
 for _,name:=range mvnwbinCore{required=append(required,filepath.Join(content,"js",name))}
 absent:=[]string{}
 for _,name:=range []string{"guard.bin","plugins.js"}{
  p:=filepath.Join(content,"js",name)
  _,e:=os.Lstat(p)
  if os.IsNotExist(e){absent=append(absent,p);continue}
  if e!=nil||!ordinary(p)||!vxaceCloneOrdinaryPath(p){return "",report,mvJSONError("ARCHIVO_NO_VERIFICADO")}
  required=append(required,p)
 }
 for _,p:=range required{
  h,e:=digestFile(p);if e!=nil{return "",report,e};protected[p]=h
 }
 dest,e:=os.MkdirTemp(parent,"Juego-IA-MV-JSON-");if e!=nil{return "",report,mvJSONError("DESTINO_INVALIDO")}
 marker:=filepath.Join(dest,mvJSONMarker)
 if e=createNew(marker,[]byte("Copia de prueba incompleta. No ejecutar. El original sigue intacto.\n"));e!=nil{return "",report,e}
 for _,entry:=range entries{
  if e=mvJSONCopyEntry(filepath.Join(root,entry.rel),filepath.Join(dest,entry.rel),entry.info);e!=nil{return "",report,e}
 }
 target:=filepath.Join(dest,rel,"data",mapName)
 if e=xpHashFile(target,hash(before));e!=nil{return "",report,mvJSONError("ORIGEN_CAMBIADO")}
 sidecar,e:=iaPrepareAndPublishSidecar(dest,pkg);if e!=nil{return "",report,e}
 if e=iaCheckEngine(sidecar,pkg);e!=nil{return "",report,e}
 if e=iaMakeSafeDirs(sidecar,filepath.Join("install","mv-json"));e!=nil{return "",report,e}
 journal:=filepath.Join(sidecar,"install","mv-json")
 if e=vxaceCloneFile(target,filepath.Join(journal,"original-"+mapName));e!=nil{return "",report,e}
 request,_:=json.Marshal(mvJSONRequest{mvJSONSchema,rel,mapName,hash(before)})
 if e=createNew(filepath.Join(journal,"request.json"),request);e!=nil{return "",report,e}
 engine:=filepath.Join(sidecar,".local","Rpg","engine")
 statusFile:=filepath.Join(journal,"status.json")
 ctx,cancel:=context.WithTimeout(context.Background(),20*time.Minute);defer cancel()
 cmd:=exec.CommandContext(ctx,filepath.Join(engine,"IATraductora.exe"),"--mv-json-pilot","--game-root",dest,"--diagnostic-file",statusFile)
 cmd.Dir=dest
 if e=cmd.Run();e!=nil{
  var s struct{Code string `json:"code"`}
  if raw,er:=mvJSONRead(statusFile,1024);er==nil&&json.Unmarshal(raw,&s)==nil&&regexp.MustCompile("^IA_[A-Z0-9_]{4,90}$").MatchString(s.Code){return "",report,errors.New(s.Code)}
  return "",report,mvJSONError("MOTOR_FALLO")
 }
 raw,e:=mvJSONRead(filepath.Join(journal,"report.json"),8192)
 if e!=nil||json.Unmarshal(raw,&report)!=nil||report.Schema!=mvJSONSchema||report.Map!=mapName||report.Before!=hash(before)||report.Lines<=0||report.Units>256{return "",report,mvJSONError("INFORME_INVALIDO")}
 candidate:=filepath.Join(journal,"candidate.json")
 after,e:=mvJSONRead(candidate,16*1024*1024);if e!=nil||hash(after)!=report.After{return "",report,mvJSONError("RESULTADO_INVALIDO")}
 changed,e:=mvJSONVerifyMap(before,after);if e!=nil{return "",report,e}
 if changed!=report.Lines{return "",report,mvJSONError("INFORME_INVALIDO")}
 if e=vxaceAtomicReplaceFrom(candidate,target,report.After,report.Before);e!=nil{return "",report,e}
 if e=xpHashFile(target,report.After);e!=nil{return "",report,mvJSONError("RESULTADO_INVALIDO")}
 for src,want:=range protected{
  if e=xpHashFile(src,want);e!=nil{return "",report,mvJSONError("ORIGEN_CAMBIADO")}
  if strings.EqualFold(src,exe)||src==sourceMap{continue}
  p,e:=filepath.Rel(root,src);if e!=nil{return "",report,e}
  if e=xpHashFile(filepath.Join(dest,p),want);e!=nil{return "",report,mvJSONError("ARRANQUE_CAMBIADO")}
 }
 for _,src:=range absent{
  p,e:=filepath.Rel(root,src);if e!=nil{return "",report,e}
  if _,e=os.Lstat(src);!os.IsNotExist(e){return "",report,mvJSONError("ORIGEN_CAMBIADO")}
  if _,e=os.Lstat(filepath.Join(dest,p));!os.IsNotExist(e){return "",report,mvJSONError("ARRANQUE_CAMBIADO")}
 }
 instructions:=fmt.Sprintf("PRUEBA R44 JSON, mapa %s: %d lineas traducidas. No es traduccion completa ni complemento F10.\nAbra el ejecutable original COPIADO desde esta carpeta. Si el juego no admite los datos localizados, cierre y utilice su original intacto. No se modificaron los binarios ni sus verificaciones.\nRespaldo exacto del mapa en IA Traductora/install/mv-json/original-%s.\n",mapName,report.Lines,mapName)
 if e=createNew(filepath.Join(journal,"LEEME.txt"),[]byte(instructions));e!=nil{return "",report,e}
 final:=filepath.Join(dest,filepath.Base(exe))
 if e=mvJSONCopyEntry(exe,final,exeInfo);e!=nil{return "",report,e}
 if e=xpHashFile(final,protected[exe]);e!=nil{return "",report,mvJSONError("ARRANQUE_CAMBIADO")}
 if e=os.Remove(marker);e!=nil{return "",report,e}
 return final,report,nil
}
