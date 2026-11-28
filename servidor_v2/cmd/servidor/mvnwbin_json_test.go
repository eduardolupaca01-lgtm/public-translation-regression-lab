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
)
const mvJSONFixtureMap=`{"width":20,"events":[null,{"id":1,"name":"Aster","pages":[{"conditions":{"switch1Id":2},"list":[{"code":101,"indent":0,"parameters":["portrait",0,0,2]},{"code":401,"indent":0,"parameters":["\\C[2]Please open the wooden gate.\\C[0]"]},{"code":401,"indent":0,"parameters":["橋を渡ってください。"]},{"code":102,"indent":0,"parameters":[["Open the gate.","Wait here."],1,0,2,0]},{"code":355,"indent":1,"parameters":["Please open the wooden gate."]},{"code":0,"indent":0,"parameters":[]}]}]}]}`
func TestR44JSONStructuralVerification(t *testing.T){
 good:=strings.Replace(mvJSONFixtureMap,"Please open the wooden gate.\\\\C[0]","Abre la puerta de madera.\\\\C[0]",1)
 good=strings.Replace(good,"橋を渡ってください。","Cruza el puente.",1)
 if n,e:=mvJSONVerifyMap([]byte(mvJSONFixtureMap),[]byte(good));e!=nil||n!=2{t.Fatalf("valid projection: %d %v",n,e)}
 for _,bad:=range []string{
  strings.Replace(good,"\"switch1Id\":2","\"switch1Id\":3",1),
  strings.Replace(good,"Wait here.","Run away.",1),
  strings.Replace(good,"Please open the wooden gate.","Destroy this script.",1),
  strings.Replace(good,"\\\\C[2]","\\\\C[3]",1),
 }{
  if _,e:=mvJSONVerifyMap([]byte(mvJSONFixtureMap),[]byte(bad));e==nil{t.Fatal("accepted invalid mutation")}
 }
}
func TestR44JSONPilotRealOPUS(t *testing.T){
 packaged:=os.Getenv("IA_R44_REAL_PACKAGE")
 if packaged==""{t.Skip("frozen real OPUS supplied by Windows acceptance")}
 sdk:=os.Getenv("IA_R44_NWBIN_SDK");if sdk==""{t.Fatal("missing SDK")}
 for _,profile:=range []string{"two_active","one_retained","one_absent"}{
  t.Run(profile,func(t *testing.T){r44JSONPilotProfile(t,sdk,packaged,profile)})
 }
}
func r44JSONPilotProfile(t *testing.T,sdk,packaged,profile string){
 t.Helper()
 var root string
 if profile=="two_active"{root=mvnwbinFixture(t,false)}else{root=mvnwbinSingleFixture(t,profile=="one_retained")}
 content:=filepath.Join(root,"www");js:=filepath.Join(content,"js")
 mvnwbinWrite(t,filepath.Join(root,"package.json"),fmt.Sprintf("{\"name\":\"ia-r44-json-trial-%d\",\"main\":\"www/index.html\",\"window\":{\"show\":false}}",time.Now().UnixNano()))
 mvnwbinWrite(t,filepath.Join(content,"data","System.json"),"{\"startMapId\":1}")
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
 mainSource:="var fs=require('fs'),p=require('path');var map=JSON.parse(fs.readFileSync(p.join(nw.App.startPath,'www','data','Map001.json'),'utf8'));var list=map.events[1].pages[0].list;var canvas=document.createElement('canvas');canvas.width=700;canvas.height=100;document.body.appendChild(canvas);var ctx=canvas.getContext('2d');ctx.fillText(list[1].parameters[0],10,20);ctx.fillText(list[2].parameters[0],10,50);var pixels=ctx.getImageData(0,0,700,100).data;var ok=window.originalGuardRan&&window.originalPluginsRan&&/puerta|port[oó]n|verja/i.test(list[1].parameters[0])&&/puente/i.test(list[2].parameters[0])&&pixels.some(function(v,i){return i%4===3&&v>0;});fs.writeFileSync(p.join(nw.App.startPath,'r44-json-native.txt'),ok?'PASS':'FAIL');nw.App.quit();\n"
 if profile!="two_active"{
  mainSource=strings.Replace(mainSource,"window.originalGuardRan&&window.originalPluginsRan","window.coreReady&&!window.originalGuardRan&&!window.extraFixtureRan&&window.originalPluginsRan",1)
 }
 mvnwbinWrite(t,filepath.Join(js,"main.js"),mainSource)
 original:=mvnwbinSnapshot(t,root);mapSHA,e:=digestFile(mapPath);if e!=nil{t.Fatal(e)};original[mapPath]=mapSHA
 pkg,e:=readPackage(packaged);if e!=nil{t.Fatal(e)};defer pkg.Close()
 // Use the executable's public CLI, not a mocked worker. The clone
 // function itself verifies the candidate and source hashes.
 ctx,cancel:=context.WithTimeout(context.Background(),4*time.Minute);defer cancel()
 out,e:=exec.CommandContext(ctx,packaged,"--mv-json-copy","--game",filepath.Join(root,"Game.exe")).CombinedOutput()
 if e!=nil{t.Fatalf("JSON pilot failed: %v %s",e,out)}
 copies,e:=filepath.Glob(filepath.Join(filepath.Dir(root),"Juego-IA-MV-JSON-*"))
 if e!=nil||len(copies)!=1{t.Fatal("missing unique copy",e)}
 dest:=copies[0]
 if _,e=os.Lstat(filepath.Join(dest,mvJSONMarker));!os.IsNotExist(e){t.Fatal("incomplete marker remained")}
 reportFile:=filepath.Join(dest,"IA Traductora","install","mv-json","report.json")
 raw,e:=os.ReadFile(reportFile);if e!=nil{t.Fatal(e)}
 var report mvJSONReport
 if json.Unmarshal(raw,&report)!=nil||report.Lines!=2||report.New!=2{t.Fatalf("unexpected translation counts %+v",report)}
 localized,e:=os.ReadFile(filepath.Join(dest,"www","data","Map001.json"))
 if e!=nil{t.Fatal(e)}
 if n,e:=mvJSONVerifyMap([]byte(mvJSONFixtureMap),localized);e!=nil||n!=2{t.Fatal("localized structure",n,e)}
 backup,e:=os.ReadFile(filepath.Join(dest,"IA Traductora","install","mv-json","original-Map001.json"))
 if e!=nil||!bytes.Equal(backup,[]byte(mvJSONFixtureMap)){t.Fatal("exact map backup missing",e)}
 for src,want:=range original{
  if src==mapPath{continue}
  rel,e:=filepath.Rel(root,src);if e!=nil{t.Fatal(e)}
  got,e:=digestFile(filepath.Join(dest,rel));if e!=nil||got!=want{t.Fatal("copied startup changed",rel,e)}
 }
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
