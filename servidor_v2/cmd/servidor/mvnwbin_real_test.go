package main

import (
 "bytes"
 "context"
 "encoding/json"
 "os"
 "os/exec"
 "path/filepath"
 "runtime"
 "strings"
 "testing"
 "time"
)

type r44RealResult struct {
 OK bool `json:"ok"`
 Code string `json:"code"`
 Kind string `json:"kind"`
 Boot json.RawMessage `json:"boot"`
 NW string `json:"nw"`
 EN string `json:"en"`
 JA string `json:"ja"`
 Translated int `json:"translated"`
}
func r44RunCommand(t *testing.T,limit time.Duration,executable string,args ...string){
 t.Helper()
 ctx,cancel:=context.WithTimeout(context.Background(),limit);defer cancel()
 cmd:=exec.CommandContext(ctx,executable,args...)
 out,e:=cmd.CombinedOutput()
 if e!=nil{t.Fatalf("R44 command failed: %v %s",e,out)}
}
func r44WaitWorkerClosed(t *testing.T,root string){
 t.Helper()
 marker:=filepath.Join(root,"www","data","IATraductora","bridge.json")
 end:=time.Now().Add(90*time.Second)
 for time.Now().Before(end){
  if _,e:=os.Lstat(marker);os.IsNotExist(e){return}
  time.Sleep(200*time.Millisecond)
 }
 t.Fatal("IA_R44_WORKER_CLOSE_TIMEOUT")
}
func r44NativeRun(t *testing.T,sdk,root,wantKind string)r44RealResult{
 t.Helper()
 result:=r44RealResult{}
 file:=filepath.Join(root,"r44-real-result.json")
 if _,e:=os.Lstat(file);e==nil{
  if !ordinary(file){t.Fatal("IA_R44_RESULT_NOT_REGULAR")}
  if e=os.Remove(file);e!=nil{t.Fatal(e)}
 }else if !os.IsNotExist(e){t.Fatal(e)}
 // The runtime is genuine NW.js and the app is independently authored.
 // The existing plugin starts its own verified worker; never launch a
 // second worker or inject a fabricated response into the renderer.
 ctx,cancel:=context.WithTimeout(context.Background(),250*time.Second);defer cancel()
 cmd:=exec.CommandContext(ctx,filepath.Join(sdk,"nw.exe"),"--disable-background-networking",root)
 cmd.Dir=root
 out,e:=cmd.CombinedOutput()
 // Always wait for shutdown before SQLite verification and TempDir cleanup,
 // even when the synthetic renderer fails a native assertion.
 r44WaitWorkerClosed(t,root)
 if e!=nil{t.Fatalf("IA_R44_NW_EXIT %v %s",e,out)}
 b,e:=os.ReadFile(file);if e!=nil{t.Fatal("IA_R44_NO_RENDERER_REPORT",e)}
 if len(b)>8192||json.Unmarshal(b,&result)!=nil{t.Fatal("IA_R44_INVALID_RENDERER_REPORT")}
 if !result.OK{t.Fatalf("R44 renderer: %s boot=%s",result.Code,result.Boot)}
 if result.NW!="0.48.4"||result.Kind!=wantKind{t.Fatal("IA_R44_RESULT_INVALID")}
 if wantKind=="real"&&(result.EN==""||result.JA==""||result.Translated<0){t.Fatal("IA_R44_RESULT_INVALID")}
 return result
}
type r44Fixture struct{
 root,exe,registry string
 before []byte
 snapshot map[string]string
}
func r44PrepareFixture(t *testing.T,sdk,mode string)r44Fixture{
 t.Helper()
 if sdk==""||runtime.GOOS!="windows"{t.Fatal("IA_R44_REAL_SDK_REQUIRED")}
 root:=mvnwbinFixture(t,true)
 content:=filepath.Join(root,"www")
 js:=filepath.Join(content,"js")
 exe:=filepath.Join(root,"Game.exe")
 registry:=filepath.Join(js,"plugins.js")
 before,e:=os.ReadFile(registry);if e!=nil{t.Fatal(e)}
 for _,item:=range []struct{name,source string}{
  {"guard","if(!window.coreReady)throw Error('core not ready');window.originalGuardRan=true;"},
  {"plugins","if(!window.originalGuardRan)throw Error('guard not run');window.originalPluginsRan=true;"},
 }{
  bin:=filepath.Join(js,item.name+".bin")
  if e=os.Remove(bin);e!=nil{t.Fatal(e)}
  mvnwbinCompileFixture(t,sdk,item.name,item.source,bin)
 }
 fixturePath:=filepath.Join("..","..","tests","r44_nwbin_renderer.js")
 fixture,e:=os.ReadFile(fixturePath);if e!=nil{t.Fatal(e)}
 mvnwbinWrite(t,filepath.Join(js,"rpg_windows.js"),string(fixture))
 manager:="window.PluginManager={parameters:function(){return {};},setup:function(list){var plugins=list.filter(function(p){return p.status;});if(plugins.length!==1||plugins[0].name!=='IATraductora'){window.r44LoadFailed();return;}var s=document.createElement('script');s.src='js/plugins/'+plugins[0].name+'.js';s.charset='UTF-8';s.async=false;s.onload=window.r44Run;s.onerror=window.r44LoadFailed;document.body.appendChild(s);}};\n"
 if mode=="ui"{manager=strings.Replace(manager,"s.onload=window.r44Run;","s.onload=window.r44RunUIOnly;",1)}else if mode!="real"{t.Fatal("IA_R44_MODE_INVALID")}
 mvnwbinWrite(t,filepath.Join(js,"rpg_managers.js"),manager)
 // Main remains the original author-provided plaintext add-on entry.
 // The installer is not permitted to modify any of these files.
 snapshot:=mvnwbinSnapshot(t,root)
 for _,n:=range mvnwbinCore{
  f:=filepath.Join(js,n);h,e:=digestFile(f);if e!=nil{t.Fatal(e)};snapshot[f]=h
 }
 for _,n:=range []string{"Actors.json","CommonEvents.json","MapInfos.json"}{
  f:=filepath.Join(content,"data",n);h,e:=digestFile(f);if e!=nil{t.Fatal(e)};snapshot[f]=h
 }
 return r44Fixture{root,exe,registry,before,snapshot}
}
func TestR44NWBinNativeUI(t *testing.T){
 sdk:=os.Getenv("IA_R44_NWBIN_SDK")
 if sdk==""{t.Skip("native SDK supplied by separate CI job")}
 f:=r44PrepareFixture(t,sdk,"ui")
 source,e:=os.ReadFile(filepath.Join("..","..","plugin","IATraductora.js"));if e!=nil{t.Fatal(e)}
 pkg,e:=readPackage(fakePackageWith(t,source,[]byte("unexecuted preflight worker")));if e!=nil{t.Fatal(e)};defer pkg.Close()
 if e=Install(f.exe,pkg);e!=nil{t.Fatal(e)}
 if _,e=installedPackageIdentity(f.exe,pkg);e!=nil{t.Fatal(e)}
 r44NativeRun(t,sdk,f.root,"ui")
 mvnwbinSame(t,f.snapshot)
 if e=RecoverGame(f.exe);e!=nil{t.Fatal(e)}
 restored,e:=os.ReadFile(f.registry);if e!=nil||!bytes.Equal(restored,f.before){t.Fatal("IA_R44_UI_RESTORE_FAIL",e)}
 mvnwbinSame(t,f.snapshot)
 t.Log("IA_R44_NATIVE_UI_PREFLIGHT_PASS")
}
func TestR44NWBinRealOPUS(t *testing.T){
 sdk:=os.Getenv("IA_R44_NWBIN_SDK")
 packaged:=os.Getenv("IA_R44_REAL_PACKAGE")
 if packaged==""{t.Skip("full real-OPUS package supplied by the R44 real Windows workflow")}
 f:=r44PrepareFixture(t,sdk,"real")
 root,exe,registry,before,snapshot:=f.root,f.exe,f.registry,f.before,f.snapshot
 r44RunCommand(t,240*time.Second,packaged,"--game",exe)
 pkg,e:=readPackage(packaged);if e!=nil{t.Fatal(e)};defer pkg.Close()
 if _,e=installedPackageIdentity(exe,pkg);e!=nil{t.Fatal(e)}
 mvnwbinSame(t,snapshot)
 db:=filepath.Join(root,"IA Traductora",".local","Rpg","cache","translation-memory-v2.sqlite3")
 report:=filepath.Join(root,"r44-real-result.json")
 verifier:=filepath.Join("..","..","tests","r44_nwbin_cache.py")
 first:=r44NativeRun(t,sdk,root,"real")
 if first.Translated<2{t.Fatal("IA_R44_REAL_NEURAL_INFERENCE_MISSING")}
 r44RunCommand(t,30*time.Second,"python",verifier,db,report)
 t.Log("IA_R44_NWBIN_REAL_OPUS_FIRST_PAINT_F10_PASS")
 mvnwbinSame(t,snapshot)
 second:=r44NativeRun(t,sdk,root,"real")
 if second.Translated!=0||second.EN!=first.EN||second.JA!=first.JA{
  t.Fatalf("IA_R44_RESTART_CACHE_FAIL new_inferences=%d",second.Translated)
 }
 r44RunCommand(t,30*time.Second,"python",verifier,db,report)
 mvnwbinSame(t,snapshot)
 r44RunCommand(t,120*time.Second,packaged,"--recover","--game",exe)
 restored,e:=os.ReadFile(registry);if e!=nil||!bytes.Equal(restored,before){t.Fatal("IA_R44_REGISTRY_RESTORE_FAIL",e)}
 mvnwbinSame(t,snapshot)
 if !ordinary(db){t.Fatal("IA_R44_CACHE_LOST_AFTER_RESTORE")}
 r44RunCommand(t,30*time.Second,"python",verifier,db,report)
 t.Log("IA_R44_NWBIN_REAL_OPUS_CACHE_RESTORE_PASS")
}
