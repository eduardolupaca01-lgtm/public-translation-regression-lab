package main
import (
 "encoding/json"
 "fmt"
 "os"
 "os/exec"
 "path/filepath"
 "testing"
 "time"
 "context"
 "bytes"
 "strings"
 "reflect"
)
const mvJSONFixtureMap=`{"width":20,"events":[null,{"id":1,"name":"Aster","pages":[{"conditions":{"switch1Id":2},"list":[{"code":101,"indent":0,"parameters":["portrait",0,0,2]},{"code":401,"indent":0,"parameters":["\\C[2]Please open the wooden gate.\\C[0]"]},{"code":401,"indent":0,"parameters":["橋を渡ってください。"]},{"code":102,"indent":0,"parameters":[["Yes","No"],1,0,2,0]},{"code":402,"indent":0,"parameters":[0,"Yes"]},{"code":355,"indent":1,"parameters":["Please open the wooden gate."]},{"code":402,"indent":0,"parameters":[1,"No"]},{"code":404,"indent":0,"parameters":[]},{"code":0,"indent":0,"parameters":[]}]}]}]}`
func TestR44JSONStructuralVerification(t *testing.T){
 good:=strings.Replace(mvJSONFixtureMap,"Please open the wooden gate.\\\\C[0]","Abre la puerta de madera.\\\\C[0]",1)
 good=strings.Replace(good,"橋を渡ってください。","Cruza el puente.",1)
 if n,e:=mvJSONVerifyMap([]byte(mvJSONFixtureMap),[]byte(good));e!=nil||n!=2{t.Fatalf("valid projection: %d %v",n,e)}
 for _,bad:=range []string{
  strings.Replace(good,"\"switch1Id\":2","\"switch1Id\":3",1),
  strings.Replace(good,"[0,\"Yes\"]","[0,\"Run away.\"]",1),
  strings.Replace(good,"Please open the wooden gate.","Destroy this script.",1),
  strings.Replace(good,"\\\\C[2]","\\\\C[3]",1),
 }{
  if _,e:=mvJSONVerifyMap([]byte(mvJSONFixtureMap),[]byte(bad));e==nil{t.Fatal("accepted invalid mutation")}
 }
}
func TestR44JSONMenuTermsOnly(t *testing.T){
 before:=[]byte(`{"gameTitle":"Test","locale":"es_ES","startMapId":1,"terms":{"basic":["Level","HP","TP"],"commands":["Item","Skill","Equip","Status","Formation","Quest Log","Options","Save","Game End",null,"Custom"],"params":["Attack","Max HP"],"messages":{"alwaysDash":"Always Dash","bgmVolume":"BGM Volume","partyName":"The group of %1"}}}`)
 after,n,e:=mvJSONLocalizeSystem(before)
 if e!=nil||n!=15{t.Fatalf("menu projection count %d %v",n,e)}
 expected:=[]byte(`{"gameTitle":"Test","locale":"es_ES","startMapId":1,"terms":{"basic":["Nivel","PV","TP"],"commands":["Objetos","Habilidades","Equipo","Estado","Formación","Misiones","Opciones","Guardar","Salir",null,"Custom"],"params":["Ataque","PV máx."],"messages":{"alwaysDash":"Correr siempre","bgmVolume":"Vol. música","partyName":"The group of %1"}}}`)
 x,e:=mvJSONDecode(expected);if e!=nil{t.Fatal(e)}
 y,e:=mvJSONDecode(after);if e!=nil||!reflect.DeepEqual(x,y){t.Fatal("unrelated System data changed",e)}
}
func TestR44JSONChoiceAndWrapVerification(t *testing.T){
 original:=`{"events":[{"pages":[{"list":[{"code":101,"indent":0,"parameters":["",0,0,2]},{"code":401,"indent":0,"parameters":["\\C[2]Please wait here until the morning.\\C[0]"]},{"code":102,"indent":0,"parameters":[["Yes","No"],1,0,2,0]},{"code":402,"indent":0,"parameters":[0,"Yes"]},{"code":402,"indent":0,"parameters":[1,"No"]},{"code":404,"indent":0,"parameters":[]}]}]}]}`
 good:=strings.ReplaceAll(original,"Yes","Sí")
 good=strings.Replace(good,"Please wait here until the morning.","Por favor, espera aquí\\nhasta la mañana.",1)
 changed,e:=mvJSONVerifyMapDetailed([]byte(original),[]byte(good))
 if e!=nil||changed.Lines!=1||changed.ChoiceGroups!=1||changed.ChoiceLabels!=1||changed.Wrapped!=1||changed.Breaks!=1{t.Fatalf("valid native fields %+v %v",changed,e)}
 for _,bad:=range []string{
  strings.Replace(good,"[0,\"Sí\"]","[0,\"No\"]",1),
  strings.Replace(good,"[1,\"No\"]","[0,\"No\"]",1),
  strings.Replace(good,"[\"Sí\",\"No\"],1,0","[\"Sí\",\"No\"],0,0",1),
  strings.Replace(good,"\\\\C[2]","\\\\C[3]",1),
  strings.ReplaceAll(good,"Sí","hide_if(1)"),
 }{if _,e:=mvJSONVerifyMapDetailed([]byte(original),[]byte(bad));e==nil{t.Fatal("accepted inconsistent or executable choice")}}
}
func TestR44JSONCopyFolderNeverOverwrites(t *testing.T){
 root:=filepath.Join(t.TempDir(),"Juego 日本語")
 if e:=os.Mkdir(root,0700);e!=nil{t.Fatal(e)}
 first,e:=mvJSONCopyFolder(root)
 if e!=nil||filepath.Base(first)!="Juego 日本語 - IA JSON"{t.Fatalf("first named folder: %s %v",filepath.Base(first),e)}
 keep:=filepath.Join(first,"keep.txt")
 if e=os.WriteFile(keep,[]byte("existing copy"),0600);e!=nil{t.Fatal(e)}
 secondPath:=first+" (2)"
 if e=os.WriteFile(secondPath,[]byte("existing file"),0600);e!=nil{t.Fatal(e)}
 third,e:=mvJSONCopyFolder(root)
 if e!=nil||third!=first+" (3)"{t.Fatalf("collision not handled: %s %v",filepath.Base(third),e)}
 for name,want:=range map[string]string{keep:"existing copy",secondPath:"existing file"}{
  raw,e:=os.ReadFile(name);if e!=nil||string(raw)!=want{t.Fatal("existing destination changed",e)}
 }
 if st,e:=os.Stat(root);e!=nil||!st.IsDir(){t.Fatal("original folder changed",e)}
}
func TestR44JSONPilotRealOPUS(t *testing.T){
 packaged:=os.Getenv("IA_R44_REAL_PACKAGE")
 if packaged==""{t.Skip("frozen real OPUS supplied by Windows acceptance")}
 sdk:=os.Getenv("IA_R44_NWBIN_SDK");if sdk==""{t.Fatal("missing SDK")}
 for _,profile:=range []string{"two_active","one_retained","one_absent"}{
  t.Run(profile,func(t *testing.T){r44JSONPilotProfile(t,sdk,packaged,profile,false)})
 }
}
func TestR44JSONDirectRealOPUS(t *testing.T){
 packaged:=os.Getenv("IA_R44_REAL_PACKAGE")
 if packaged==""{t.Skip("frozen real OPUS supplied by Windows acceptance")}
 sdk:=os.Getenv("IA_R44_NWBIN_SDK");if sdk==""{t.Fatal("missing SDK")}
 for _,profile:=range []string{"two_active","one_absent"}{
  t.Run(profile,func(t *testing.T){r44JSONPilotProfile(t,sdk,packaged,profile,true)})
 }
}
func r44JSONPilotProfile(t *testing.T,sdk,packaged,profile string,direct bool){
 t.Helper()
 var root string
 if profile=="two_active"{root=mvnwbinFixture(t,false)}else{root=mvnwbinSingleFixture(t,profile=="one_retained")}
 content:=filepath.Join(root,"www");js:=filepath.Join(content,"js")
 mvnwbinWrite(t,filepath.Join(root,"package.json"),fmt.Sprintf("{\"name\":\"ia-r44-json-trial-%d\",\"main\":\"www/index.html\",\"window\":{\"show\":false}}",time.Now().UnixNano()))
 mvnwbinWrite(t,filepath.Join(content,"data","System.json"),"{\"startMapId\":1,\"terms\":{\"commands\":[\"Item\",\"Skill\",\"Options\",\"Save\"]}}")
 mapPath:=filepath.Join(content,"data","Map001.json")
 mvnwbinWrite(t,mapPath,mvJSONFixtureMap)
 fixtures:=[]struct{name,source string}{}
 if profile=="two_active"||profile=="one_retained"{
  fixtures=append(fixtures,struct{name,source string}{"guard","if(!window.coreReady)throw Error('core not ready');window.originalGuardRan=true;"})
 }
 pluginSource:="if(!window.coreReady)throw Error('core not ready');window.originalPluginsRan=true;"
 if profile=="two_active"{pluginSource="if(!window.originalGuardRan)throw Error('guard not run');window.originalPluginsRan=true;"}
 fixtures=append(fixtures,struct{name,source string}{"plugins",pluginSource})
 for _,item:=range fixtures{
  bin:=filepath.Join(js,item.name+".bin")
  if e:=os.Remove(bin);e!=nil{t.Fatal(e)}
  mvnwbinCompileFixture(t,sdk,item.name,item.source,bin)
 }
 // Authored original loader reads the ordinary data file. It is copied
 // byte-for-byte and never replaced by the localizer.
 mainSource:="var fs=require('fs'),p=require('path');var map=JSON.parse(fs.readFileSync(p.join(nw.App.startPath,'www','data','Map001.json'),'utf8'));var list=map.events[1].pages[0].list;var canvas=document.createElement('canvas');canvas.width=700;canvas.height=100;document.body.appendChild(canvas);var ctx=canvas.getContext('2d');ctx.fillText(list[1].parameters[0],10,20);ctx.fillText(list[2].parameters[0],10,50);var pixels=ctx.getImageData(0,0,700,100).data;var sys=JSON.parse(fs.readFileSync(p.join(nw.App.startPath,'www','data','System.json'),'utf8'));var menu=sys.terms.commands.join('|')==='Objetos|Habilidades|Opciones|Guardar';var choice=list[3].parameters[0][0]==='Sí'&&list[4].parameters[1]==='Sí'&&list[6].parameters[1]==='No';var ok=menu&&choice&&window.originalGuardRan&&window.originalPluginsRan&&/puerta|port[oó]n|verja/i.test(list[1].parameters[0])&&/puente/i.test(list[2].parameters[0])&&pixels.some(function(v,i){return i%4===3&&v>0;});fs.writeFileSync(p.join(nw.App.startPath,'r44-json-native.txt'),ok?'PASS':'FAIL');nw.App.quit();\n"
 if profile!="two_active"{
  mainSource=strings.Replace(mainSource,"window.originalGuardRan&&window.originalPluginsRan","window.coreReady&&!window.originalGuardRan&&!window.extraFixtureRan&&window.originalPluginsRan",1)
 }
 mvnwbinWrite(t,filepath.Join(js,"main.js"),mainSource)
 original:=mvnwbinOfflineSnapshot(t,root);mapSHA,e:=digestFile(mapPath);if e!=nil{t.Fatal(e)};original[mapPath]=mapSHA
 pkg,e:=readPackage(packaged);if e!=nil{t.Fatal(e)};defer pkg.Close()
 if direct{r44JSONDirectRealTrial(t,sdk,packaged,root,original);return}
 // Use the executable's public CLI, not a mocked worker. The clone
 // function itself verifies the candidate and source hashes.
 ctx,cancel:=context.WithTimeout(context.Background(),4*time.Minute);defer cancel()
 out,e:=exec.CommandContext(ctx,packaged,"--mv-json-copy","--game",filepath.Join(root,"Game.exe")).CombinedOutput()
 if e!=nil{t.Fatalf("JSON pilot failed: %v %s",e,out)}
 dest:=filepath.Join(filepath.Dir(root),filepath.Base(root)+" - IA JSON")
 if st,e:=os.Lstat(dest);e!=nil||!st.IsDir(){t.Fatal("named copy missing",e)}
 if _,e=os.Lstat(filepath.Join(dest,mvJSONMarker));!os.IsNotExist(e){t.Fatal("incomplete marker remained")}
 if got:=mvJSONWorkerStatus(filepath.Join(dest,"IA Traductora","install","mv-json","status.json"));got!="IA_MV_JSON_CANDIDATO_LISTO"{t.Fatalf("worker terminal status: %s",got)}
 reportFile:=filepath.Join(dest,"IA Traductora","install","mv-json","report.json")
 raw,e:=os.ReadFile(reportFile);if e!=nil{t.Fatal(e)}
 var report mvJSONReport
 if json.Unmarshal(raw,&report)!=nil||report.Lines!=2||report.New!=2||report.ChoiceLabels!=1||report.ChoiceGroups!=1||report.RuntimeMode!="onedir"||report.WorkerPID<=0{t.Fatalf("unexpected translation counts %+v",report)}
 localized,e:=os.ReadFile(filepath.Join(dest,"www","data","Map001.json"))
 if e!=nil{t.Fatal(e)}
 if n,e:=mvJSONVerifyMap([]byte(mvJSONFixtureMap),localized);e!=nil||n!=2{t.Fatal("localized structure",n,e)}
 backup,e:=os.ReadFile(filepath.Join(dest,"IA Traductora","install","mv-json","original-Map001.json"))
 if e!=nil||!bytes.Equal(backup,[]byte(mvJSONFixtureMap)){t.Fatal("exact map backup missing",e)}
 for src,want:=range original{
  if src==mapPath||src==filepath.Join(content,"data","System.json"){continue}
  rel,e:=filepath.Rel(root,src);if e!=nil{t.Fatal(e)}
  got,e:=digestFile(filepath.Join(dest,rel));if e!=nil||got!=want{t.Fatal("copied startup changed",rel,e)}
 }
 systemBackup,e:=os.ReadFile(filepath.Join(dest,"IA Traductora","install","mv-json","original-System.json"))
 originalSystem,e2:=os.ReadFile(filepath.Join(content,"data","System.json"))
 if e!=nil||e2!=nil||!bytes.Equal(systemBackup,originalSystem){t.Fatal("system backup missing or changed")}
 var presentation struct{Translation mvJSONReport `json:"translation"`}
 presentationRaw,e:=os.ReadFile(filepath.Join(dest,"IA Traductora","install","mv-json","presentation.json"))
 if e!=nil||json.Unmarshal(presentationRaw,&presentation)!=nil||presentation.Translation.Menu!=4{t.Fatal("presentation receipt invalid",e)}
 for _,n:=range []string{"guard.bin","plugins.js"}{
  src:=filepath.Join(root,"www","js",n)
  if _,e=os.Lstat(src);os.IsNotExist(e){
   if _,e=os.Lstat(filepath.Join(dest,"www","js",n));!os.IsNotExist(e){t.Fatal("unexpected file in clone",n)}
  }
 }
 mvnwbinSame(t,original)
 ctx2,stop:=context.WithTimeout(context.Background(),90*time.Second);defer stop()
 cmd:=exec.CommandContext(ctx2,filepath.Join(sdk,"nw.exe"),"--disable-background-networking",dest);cmd.Dir=dest
 if out,e=cmd.CombinedOutput();e!=nil{t.Fatalf("native copied app %v %s",e,out)}
 native,e:=os.ReadFile(filepath.Join(dest,"r44-json-native.txt"))
 if e!=nil||string(native)!="PASS"{t.Fatal("IA_R44_JSON_NATIVE_PAINT_FAIL",e)}
 if !ordinary(filepath.Join(dest,"IA Traductora",".local","Rpg","cache","translation-memory-v2.sqlite3")){t.Fatal("cache missing")}
 mvnwbinSame(t,original)
 t.Log("IA_R44_JSON_REAL_OPUS_COPY_NATIVE_PAINT_ORIGINAL_UNCHANGED_PASS")
}

func r44JSONDirectRealTrial(t *testing.T,sdk,packaged,root string,original map[string]string){
 t.Helper()
 exe:=filepath.Join(root,"Game.exe")
 siblings,e:=os.ReadDir(filepath.Dir(root));if e!=nil{t.Fatal(e)}
 run:=func(args ...string){
  ctx,cancel:=context.WithTimeout(context.Background(),5*time.Minute);defer cancel()
  if out,e:=exec.CommandContext(ctx,packaged,args...).CombinedOutput();e!=nil{t.Fatalf("direct command %v %s",e,out)}
 }
 run("--mv-json-install","--game",exe)
 after,e:=os.ReadDir(filepath.Dir(root));if e!=nil||len(after)!=len(siblings){t.Fatal("direct mode created game copy",e)}
 active:=filepath.Join(mvJSONDirectBase(root),"active")
 var rec mvJSONDirectReceipt
 if _,e=mvJSONDirectRead(filepath.Join(active,"prepared.json"),&rec);e!=nil||rec.Report.Lines!=2||rec.Report.New!=2||rec.Report.Menu!=4||rec.Report.ChoiceLabels!=1||rec.Report.RuntimeMode!="onedir"||rec.Report.WorkerPID<=0{t.Fatalf("direct receipt %+v %v",rec,e)}
 for f,want:=range original{
  if filepath.Base(f)=="Map001.json"||filepath.Base(f)=="System.json"{continue}
  if h,e:=digestFile(f);e!=nil||h!=want{t.Fatal("original startup changed",filepath.Base(f),e)}
 }
 ctx,cancel:=context.WithTimeout(context.Background(),90*time.Second)
 cmd:=exec.CommandContext(ctx,filepath.Join(sdk,"nw.exe"),"--disable-background-networking",root);cmd.Dir=root
 out,e:=cmd.CombinedOutput();cancel()
 if e!=nil{t.Fatalf("direct native renderer %v %s",e,out)}
 marker:=filepath.Join(root,"r44-json-native.txt")
 value,e:=os.ReadFile(marker);if e!=nil||string(value)!="PASS"{t.Fatal("IA_R44_DIRECT_NATIVE_PAINT_FAIL",e)}
 cache:=filepath.Join(root,brandFolder,".local","Rpg","cache","translation-memory-v2.sqlite3")
 beforeCache,e:=digestFile(cache);if e!=nil{t.Fatal(e)}
 run("--recover","--game",exe)
 mvnwbinSame(t,original)
 if h,e:=digestFile(cache);e!=nil||h!=beforeCache{t.Fatal("cache changed by recovery",e)}
 if mvJSONDirectNeedsRecovery(exe){t.Fatal("recovery did not retire journal")}
 run("--mv-json-install","--game",exe)
 if _,e=mvJSONDirectRead(filepath.Join(active,"prepared.json"),&rec);e!=nil||rec.Report.New!=0||rec.Report.Hits!=2{t.Fatalf("cache reuse %+v %v",rec,e)}
 run("--recover","--game",exe)
 mvnwbinSame(t,original)
 // Existing independent copy remains available from the restored source.
 skip,unlock,e:=mvJSONDirectCopyGuard(root);if e!=nil||!skip{t.Fatal("copy disabled after restore",e)};unlock()
 t.Log("IA_R44_DIRECT_REAL_OPUS_NATIVE_PAINT_RESTORE_CACHE_PASS")
}
