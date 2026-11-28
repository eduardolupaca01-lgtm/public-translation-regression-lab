package main

// A separate offline localization trial for an opaque MV/NWBin title.
// The original title is never executed or changed. Do not modify binaries,
// loader, manifest, protection logic, event scripts, choice indices or saves.
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
 ChoiceGroups int `json:"choice_groups"`
 ChoiceLabels int `json:"choice_labels"`
 Wrapped int `json:"wrapped_lines"`
 Breaks int `json:"added_breaks"`
 FitWarnings int `json:"fit_warnings"`
 Menu int `json:"menu_terms,omitempty"`
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
// Independently verify only allowed display text and proven native choice
// groups. The full map is compared after masking those fields. All event
// commands, indices, conditions, variables, scripts and other data remain.
type mvJSONDisplayField struct{Code string;Params []any}
func mvJSONEventLists(doc any)([][]any,error){
 obj,ok:=doc.(map[string]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
 events,ok:=obj["events"].([]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
 var lists [][]any
 for _,ev:=range events{
  if ev==nil{continue}
  event,ok:=ev.(map[string]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
  pages,ok:=event["pages"].([]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
  for _,pg:=range pages{
   page,ok:=pg.(map[string]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
   list,ok:=page["list"].([]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
   for _,c:=range list{
    cmd,ok:=c.(map[string]any);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
    for _,key:=range []string{"code","indent"}{
     n,ok:=cmd[key].(json.Number);if !ok{return nil,mvJSONError("MAPA_INVALIDO")}
     if _,e:=n.Int64();e!=nil{return nil,mvJSONError("MAPA_INVALIDO")}
    }
   }
   lists=append(lists,list)
  }
 }
 return lists,nil
}
func mvJSONDisplay(doc any)([]mvJSONDisplayField,error){
 lists,e:=mvJSONEventLists(doc);if e!=nil{return nil,e}
 var fields []mvJSONDisplayField
 for _,list:=range lists{
  for _,c:=range list{
   cmd:=c.(map[string]any)
   code:=string(cmd["code"].(json.Number))
   if code!="401"&&code!="405"{continue}
   params,ok:=cmd["parameters"].([]any);if !ok||len(params)!=1{return nil,mvJSONError("MAPA_INVALIDO")}
   if _,ok=params[0].(string);!ok{return nil,mvJSONError("MAPA_INVALIDO")}
   fields=append(fields,mvJSONDisplayField{code,params})
  }
 }
 return fields,nil
}
var mvJSONChoiceUnsafe=regexp.MustCompile("(?i)[\\\\<>{}\\[\\]()%:\\x00-\\x1f]|https?://|www\\.")
func mvJSONPlainChoice(value any)bool{
 s,ok:=value.(string)
 return ok&&len([]rune(s))>0&&len([]rune(s))<=180&&s==strings.TrimSpace(s)&&!mvJSONChoiceUnsafe.MatchString(s)
}
type mvJSONChoiceGroup struct{
 labels []any
 branches map[int][]any
 indent int64
 valid bool
}
func mvJSONChoiceGroups(doc any)([]mvJSONChoiceGroup,error){
 lists,e:=mvJSONEventLists(doc);if e!=nil{return nil,e}
 groups:=[]mvJSONChoiceGroup{}
 for _,list:=range lists{
  stack:=[]*mvJSONChoiceGroup{}
  for _,row:=range list{
   cmd:=row.(map[string]any);code:=string(cmd["code"].(json.Number));indent,_:=cmd["indent"].(json.Number).Int64()
   params,ok:=cmd["parameters"].([]any)
   switch code{
   case "102":
    for len(stack)>0&&stack[len(stack)-1].indent>=indent{stack=stack[:len(stack)-1]}
    g:=&mvJSONChoiceGroup{indent:indent,branches:map[int][]any{}}
    if ok&&len(params)==5{
     g.labels,g.valid=params[0].([]any)
     g.valid=g.valid&&len(g.labels)>=1&&len(g.labels)<=24
     for _,v:=range g.labels{if !mvJSONPlainChoice(v){g.valid=false}}
     for _,v:=range params[1:]{
      n,ok:=v.(json.Number);if !ok{g.valid=false;continue};if _,e:=n.Int64();e!=nil{g.valid=false}
     }
    }
    stack=append(stack,g)
   case "402","403","404":
    if len(stack)==0||stack[len(stack)-1].indent!=indent{
     for _,g:=range stack{g.valid=false};continue
    }
    g:=stack[len(stack)-1]
    if code=="402"{
     if !g.valid||!ok||len(params)!=2{g.valid=false;continue}
     n,ok:=params[0].(json.Number);if !ok{g.valid=false;continue}
     index,e:=n.Int64()
     if e!=nil||index<0||index>=int64(len(g.labels))||g.branches[int(index)]!=nil||!reflect.DeepEqual(params[1],g.labels[int(index)]){g.valid=false;continue}
     g.branches[int(index)]=params
    }else if code=="403"{
     if !ok||len(params)!=0{g.valid=false}
    }else{
     stack=stack[:len(stack)-1]
     if g.valid&&ok&&len(params)==0&&len(g.branches)==len(g.labels){groups=append(groups,*g)}
    }
   }
  }
 }
 return groups,nil
}
func mvJSONSameFormatting(a,b string,wrap bool)bool{
 if strings.TrimSpace(b)==""||len(b)>1800*6{return false}
 ac,bc:=mvJSONControl.FindAllString(a,-1),mvJSONControl.FindAllString(b,-1)
 if wrap{
  // Only additional LF line breaks may be introduced by the wrapper.
  // Preserve every preexisting control and original line separator.
  i:=0
  for _,token:=range bc{
   if i<len(ac)&&ac[i]==token{i++;continue}
   if token!="\n"{return false}
  }
  if i!=len(ac)||len(bc)-len(ac)>64{return false}
 }else if !reflect.DeepEqual(ac,bc){return false}
 digits:=func(s string)[]string{
  s=strings.Map(func(r rune)rune{if r>='０'&&r<='９'{return r-'０'+'0'};return r},s)
  out:=mvJSONDigits.FindAllString(s,-1)
  for i,n:=range out{n=strings.TrimLeft(n,"0");if n==""{n="0"};out[i]=n}
  sort.Strings(out);return out
 }
 if !reflect.DeepEqual(digits(a),digits(b)){return false}
 return !strings.ContainsAny(mvJSONControl.ReplaceAllString(b,""),"\\<>{}[]\x00")
}
type mvJSONChanges struct{Lines,ChoiceGroups,ChoiceLabels,Wrapped,Breaks int}
func mvJSONVerifyMapDetailed(before,after []byte)(mvJSONChanges,error){
 changes:=mvJSONChanges{}
 a,e:=mvJSONDecode(before);if e!=nil{return changes,e}
 b,e:=mvJSONDecode(after);if e!=nil{return changes,e}
 x,e:=mvJSONDisplay(a);if e!=nil{return changes,e}
 y,e:=mvJSONDisplay(b);if e!=nil||len(x)!=len(y){return changes,mvJSONError("ESTRUCTURA_CAMBIADA")}
 for i:=range x{
  if x[i].Code!=y[i].Code{return changes,mvJSONError("ESTRUCTURA_CAMBIADA")}
  original,result:=x[i].Params[0].(string),y[i].Params[0].(string)
  if original!=result{
   if !mvJSONSameFormatting(original,result,x[i].Code=="401"){return changes,mvJSONError("CONTROLES_CAMBIADOS")}
   changes.Lines++
   n:=strings.Count(result,"\n")-strings.Count(original,"\n")
   if n>0{changes.Wrapped++;changes.Breaks+=n}
  }
  x[i].Params[0]="";y[i].Params[0]=""
 }
 cx,e:=mvJSONChoiceGroups(a);if e!=nil{return changes,e}
 cy,e:=mvJSONChoiceGroups(b);if e!=nil||len(cx)!=len(cy){return changes,mvJSONError("ELECCIONES_CAMBIADAS")}
 for i:=range cx{
  l,r:=cx[i],cy[i]
  if l.indent!=r.indent||len(l.labels)!=len(r.labels){return changes,mvJSONError("ELECCIONES_CAMBIADAS")}
  n:=0
  for j:=range l.labels{
   old,new:=l.labels[j].(string),r.labels[j].(string)
   if old!=new{
    if !mvJSONSameFormatting(old,new,false)||!mvJSONPlainChoice(new){return changes,mvJSONError("ELECCIONES_CAMBIADAS")}
    n++
   }
   l.labels[j]="";r.labels[j]="";l.branches[j][1]="";r.branches[j][1]=""
  }
  if n>0{changes.ChoiceGroups++;changes.ChoiceLabels+=n}
 }
 if !reflect.DeepEqual(a,b){return changes,mvJSONError("ESTRUCTURA_CAMBIADA")}
 return changes,nil
}
func mvJSONVerifyMap(before,after []byte)(int,error){
 changes,e:=mvJSONVerifyMapDetailed(before,after);return changes.Lines,e
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
 sourceSystem:=filepath.Join(content,"data","System.json")
 systemBefore,e:=mvJSONRead(sourceSystem,16*1024*1024);if e!=nil{return "",report,e}
 systemAfter,menuCount,e:=mvJSONLocalizeSystem(systemBefore);if e!=nil{return "",report,e}
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
 required:=[]string{exe,filepath.Join(root,"package.json"),filepath.Join(content,"index.html"),filepath.Join(content,"js","main.js"),filepath.Join(content,"js","plugins.bin"),sourceMap,sourceSystem}
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
 targetSystem:=filepath.Join(dest,rel,"data","System.json")
 if e=xpHashFile(target,hash(before));e!=nil{return "",report,mvJSONError("ORIGEN_CAMBIADO")}
 if e=xpHashFile(targetSystem,hash(systemBefore));e!=nil{return "",report,mvJSONError("ORIGEN_CAMBIADO")}
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
 if e!=nil||json.Unmarshal(raw,&report)!=nil||report.Schema!=mvJSONSchema||report.Map!=mapName||report.Before!=hash(before)||report.Lines<0||report.ChoiceLabels<0||report.Lines+report.ChoiceLabels<=0||report.Units<0||report.Units>256||report.FitWarnings<0{return "",report,mvJSONError("INFORME_INVALIDO")}
 candidate:=filepath.Join(journal,"candidate.json")
 after,e:=mvJSONRead(candidate,16*1024*1024);if e!=nil||hash(after)!=report.After{return "",report,mvJSONError("RESULTADO_INVALIDO")}
 changed,e:=mvJSONVerifyMapDetailed(before,after);if e!=nil{return "",report,e}
 if changed.Lines!=report.Lines||changed.ChoiceGroups!=report.ChoiceGroups||changed.ChoiceLabels!=report.ChoiceLabels||changed.Wrapped!=report.Wrapped||changed.Breaks!=report.Breaks{return "",report,mvJSONError("INFORME_INVALIDO")}
 if e=vxaceAtomicReplaceFrom(candidate,target,report.After,report.Before);e!=nil{return "",report,e}
 if e=xpHashFile(target,report.After);e!=nil{return "",report,mvJSONError("RESULTADO_INVALIDO")}
 report.Menu=menuCount
 if menuCount>0{
  if e=vxaceCloneFile(targetSystem,filepath.Join(journal,"original-System.json"));e!=nil{return "",report,e}
  systemCandidate:=filepath.Join(journal,"candidate-System.json")
  if e=createNew(systemCandidate,systemAfter);e!=nil{return "",report,e}
  if e=vxaceAtomicReplaceFrom(systemCandidate,targetSystem,hash(systemAfter),hash(systemBefore));e!=nil{return "",report,e}
 }
 if e=xpHashFile(targetSystem,hash(systemAfter));e!=nil{return "",report,mvJSONError("RESULTADO_INVALIDO")}
 // A local presentation report includes the exact backup/candidate hashes
 // and counts. No changes to the existing worker report schema or cache.
 summary,_:=json.MarshalIndent(struct{
  Report mvJSONReport `json:"translation"`
  SystemBefore string `json:"system_before_sha256"`
  SystemAfter string `json:"system_after_sha256"`
 }{report,hash(systemBefore),hash(systemAfter)},"","  ")
 if e=createNew(filepath.Join(journal,"presentation.json"),summary);e!=nil{return "",report,e}
 for src,want:=range protected{
  if e=xpHashFile(src,want);e!=nil{return "",report,mvJSONError("ORIGEN_CAMBIADO")}
  if strings.EqualFold(src,exe)||src==sourceMap||src==sourceSystem{continue}
  p,e:=filepath.Rel(root,src);if e!=nil{return "",report,e}
  if e=xpHashFile(filepath.Join(dest,p),want);e!=nil{return "",report,mvJSONError("ARRANQUE_CAMBIADO")}
 }
 for _,src:=range absent{
  p,e:=filepath.Rel(root,src);if e!=nil{return "",report,e}
  if _,e=os.Lstat(src);!os.IsNotExist(e){return "",report,mvJSONError("ORIGEN_CAMBIADO")}
  if _,e=os.Lstat(filepath.Join(dest,p));!os.IsNotExist(e){return "",report,mvJSONError("ARRANQUE_CAMBIADO")}
 }
 instructions:=fmt.Sprintf("PRUEBA R44 JSON INTERFAZ, mapa %s: %d dialogos, %d elecciones, %d terminos de menu, %d lineas ajustadas. Avisos de ancho: %d.\nNo es traduccion completa ni complemento F10 del juego. F10 en Servidor muestra el estado de la ultima copia.\nAbra el ejecutable original COPIADO desde esta carpeta. Si el juego no admite los datos localizados, cierre y utilice su original intacto. No se modificaron los binarios ni sus verificaciones.\nRespaldos exactos en IA Traductora/install/mv-json/. Detalle: presentation.json.\n",mapName,report.Lines,report.ChoiceLabels,report.Menu,report.Wrapped,report.FitWarnings)
 if e=createNew(filepath.Join(journal,"LEEME.txt"),[]byte(instructions));e!=nil{return "",report,e}
 final:=filepath.Join(dest,filepath.Base(exe))
 if e=mvJSONCopyEntry(exe,final,exeInfo);e!=nil{return "",report,e}
 if e=xpHashFile(final,protected[exe]);e!=nil{return "",report,mvJSONError("ARRANQUE_CAMBIADO")}
 if e=os.Remove(marker);e!=nil{return "",report,e}
 return final,report,nil
}
