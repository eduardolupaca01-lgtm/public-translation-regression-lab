package main

import (
 "bytes"
 "context"
 "fmt"
 "os"
 "os/exec"
 "path/filepath"
 "runtime"
 "strings"
 "testing"
 "time"
)

func mvnwbinWrite(t *testing.T,path,text string){
 t.Helper()
 if e:=os.WriteFile(path,[]byte(text),0600);e!=nil{t.Fatal(e)}
}
func mvnwbinFixture(t *testing.T,approved bool)string{
 t.Helper()
 root:=createFixture(t)
 content:=filepath.Join(root,"www")
 js:=filepath.Join(content,"js")
 data:=filepath.Join(content,"data")
 for _,n:=range mvnwbinCore{
  mvnwbinWrite(t,filepath.Join(js,n),"// authored laboratory file\n")
 }
 mvnwbinWrite(t,filepath.Join(js,"rpg_core.js"),"window.coreReady=true;\n")
 for _,n:=range []string{"Actors.json","CommonEvents.json","MapInfos.json"}{
  mvnwbinWrite(t,filepath.Join(data,n),"[]")
 }
 mvnwbinWrite(t,filepath.Join(js,"guard.bin"),"opaque synthetic guard")
 mvnwbinWrite(t,filepath.Join(js,"plugins.bin"),"opaque synthetic built-in registry")
 // Unique application identity avoids attaching to a different NW process.
 name:=fmt.Sprintf("ia-r44-test-%d",time.Now().UnixNano())
 mvnwbinWrite(t,filepath.Join(root,"package.json"),fmt.Sprintf("{\"name\":%q,\"main\":\"www/index.html\",\"window\":{\"show\":false}}",name))
 var html strings.Builder
 html.WriteString("<!doctype html><html><body>\n")
 for _,n:=range mvnwbinCore{fmt.Fprintf(&html,"<script src=\"js/%s\"></script>\n",n)}
 html.WriteString("<script>\nvar w=nw.Window.get();\nw.evalNWBin(null,require('path').join(nw.App.startPath,'www','js','guard.bin'));\nw.evalNWBin(null,require('path').join(nw.App.startPath,'www','js','plugins.bin'));\n</script>\n")
 if approved{
  mvnwbinWrite(t,filepath.Join(js,"plugins.js"),mvnwbinOptIn+"\nvar $plugins = [];\n")
  html.WriteString("<script src=\"js/plugins.js\"></script>\n")
 }else{
  if e:=os.Remove(filepath.Join(js,"plugins.js"));e!=nil{t.Fatal(e)}
 }
 html.WriteString("<script src=\"js/main.js\"></script>\n</body></html>")
 mvnwbinWrite(t,filepath.Join(content,"index.html"),html.String())
 mvnwbinWrite(t,filepath.Join(js,"main.js"),"PluginManager.setup($plugins);\n")
 return root
}
func mvnwbinProtectedFiles(root string)[]string{
 return []string{filepath.Join(root,"package.json"),filepath.Join(root,"Game.exe"),
  filepath.Join(root,"www","index.html"),filepath.Join(root,"www","js","guard.bin"),
  filepath.Join(root,"www","js","plugins.bin"),filepath.Join(root,"www","js","main.js"),
  filepath.Join(root,"www","data","System.json")}
}
func mvnwbinSnapshot(t *testing.T,root string)map[string]string{
 t.Helper()
 result:=map[string]string{}
 for _,file:=range mvnwbinProtectedFiles(root){
  sum,e:=digestFile(file);if e!=nil{t.Fatal(e)};result[file]=sum
 }
 return result
}
func mvnwbinSame(t *testing.T,expected map[string]string){
 t.Helper()
 for file,want:=range expected{
  got,e:=digestFile(file);if e!=nil||got!=want{t.Fatal("original resource changed",filepath.Base(file),e)}
 }
}
func TestR44NWBinOpaqueGameRemainsReadOnly(t *testing.T){
 root:=mvnwbinFixture(t,false)
 exe:=filepath.Join(root,"Game.exe")
 snapshot:=mvnwbinSnapshot(t,root)
 pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
 if _,e=detectInstallTarget(exe);e==nil||e.Error()!=mvnwbinExtensionUnavailable{t.Fatalf("incorrect classification %v",e)}
 if e=Install(exe,pkg);e==nil||e.Error()!=mvnwbinExtensionUnavailable{t.Fatalf("opaque installation was not refused %v",e)}
 if e=RecoverGame(exe);e==nil{t.Fatal("recovery without installation accepted")}
 if _,e=os.Lstat(filepath.Join(root,"IA Traductora"));!os.IsNotExist(e){t.Fatal("sidecar created for opaque game")}
 if _,e=os.Lstat(filepath.Join(root,"www","js","plugins.js"));!os.IsNotExist(e){t.Fatal("fabricated plugin registry")}
 mvnwbinSame(t,snapshot)
}
func TestR44NWBinPublisherRegistryInstallAndRestore(t *testing.T){
 root:=mvnwbinFixture(t,true)
 exe:=filepath.Join(root,"Game.exe")
 registry:=filepath.Join(root,"www","js","plugins.js")
 before,e:=os.ReadFile(registry);if e!=nil{t.Fatal(e)}
 snapshot:=mvnwbinSnapshot(t,root)
 if kind,e:=detectInstallTarget(exe);e!=nil||kind!=mvnwbinKind{t.Fatalf("approved profile %s %v",kind,e)}
 pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
 if e=Install(exe,pkg);e!=nil{t.Fatal(e)}
 if _,e=installedPackageIdentity(exe,pkg);e!=nil{t.Fatal(e)}
 after,e:=os.ReadFile(registry);if e!=nil||!bytes.Contains(after,[]byte("\"name\":\"IATraductora\"")){t.Fatal("authorized registry not updated")}
 mvnwbinSame(t,snapshot)
 if e=RecoverGame(exe);e!=nil{t.Fatal(e)}
 restored,e:=os.ReadFile(registry);if e!=nil||!bytes.Equal(restored,before){t.Fatal("registry not restored")}
 mvnwbinSame(t,snapshot)
}
func TestR44NWBinRejectsIncompleteAndMixedLayouts(t *testing.T){
 cases:=[]struct{name,expected string; mutate func(*testing.T,string)}{
  {"manifest missing",mvnwbinManifestMissing,func(t *testing.T,r string){if e:=os.Remove(filepath.Join(r,"package.json"));e!=nil{t.Fatal(e)}}},
  {"remote main",mvnwbinInvalid,func(t *testing.T,r string){mvnwbinWrite(t,filepath.Join(r,"package.json"),"{\"name\":\"probe\",\"main\":\"https://example.invalid/index.html\"}")}},
  {"no opt-in",mvnwbinExtensionUnavailable,func(t *testing.T,r string){mvnwbinWrite(t,filepath.Join(r,"www","js","plugins.js"),"var $plugins = [];")}},
  {"no setup",mvnwbinExtensionUnavailable,func(t *testing.T,r string){mvnwbinWrite(t,filepath.Join(r,"www","js","main.js"),"// no supported plugin loading")}},
  {"invalid database",mvnwbinInvalid,func(t *testing.T,r string){mvnwbinWrite(t,filepath.Join(r,"www","data","System.json"),"[]")}},
  {"missing binary",mvnwbinInvalid,func(t *testing.T,r string){if e:=os.Remove(filepath.Join(r,"www","js","guard.bin"));e!=nil{t.Fatal(e)}}},
  {"commented add-on",mvnwbinExtensionUnavailable,func(t *testing.T,r string){p:=filepath.Join(r,"www","index.html");b,e:=os.ReadFile(p);if e!=nil{t.Fatal(e)};mvnwbinWrite(t,p,strings.Replace(string(b),"<script src=\"js/plugins.js\"></script>","<!-- <script src=\"js/plugins.js\"></script> -->",1))}},
  {"mixed engines","IA_RPG_RUTAS_AMBIGUAS",func(t *testing.T,r string){mvnwbinWrite(t,filepath.Join(r,"www","js","rmmz_core.js"),"// wrong engine")}},
 }
 for _,c:=range cases{t.Run(c.name,func(t *testing.T){
  root:=mvnwbinFixture(t,true);c.mutate(t,root)
  if _,e:=detectInstallTarget(filepath.Join(root,"Game.exe"));e==nil||e.Error()!=c.expected{t.Fatalf("got %v, expected %s",e,c.expected)}
  if _,e:=os.Lstat(filepath.Join(root,"IA Traductora"));!os.IsNotExist(e){t.Fatal("detector wrote files")}
 })}
}

// This optional CI gate uses the OFFICIAL NW.js SDK on Windows and its
// real nwjc / evalNWBin. All scripts, data and binaries are authored here.
// It proves loader coexistence and installer recovery, not model accuracy
// or compatibility with any protected commercial game.
func TestR44NWBinNativeLoader(t *testing.T){
 sdk:=os.Getenv("IA_R44_NWBIN_SDK")
 if sdk==""{t.Skip("native SDK supplied by separate CI job")}
 if runtime.GOOS!="windows"{t.Fatal("expected Windows SDK")}
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
  src:=filepath.Join(t.TempDir(),item.name+".js")
  mvnwbinWrite(t,src,item.source)
  bin:=filepath.Join(js,item.name+".bin")
  if e=os.Remove(bin);e!=nil{t.Fatal(e)}
  ctx,cancel:=context.WithTimeout(context.Background(),60*time.Second)
  out,e:=exec.CommandContext(ctx,filepath.Join(sdk,"nwjc.exe"),src,bin).CombinedOutput();cancel()
  if e!=nil||!mvnwbinRegular(bin,64*1024*1024){t.Fatalf("nwjc failed %v %s",e,out)}
 }
 mvnwbinWrite(t,filepath.Join(js,"rpg_managers.js"),"window.PluginManager={setup:function(list){list.forEach(function(p){if(p.status){var s=document.createElement('script');s.src='js/plugins/'+p.name+'.js';s.async=false;document.body.appendChild(s);}});}};\n")
 mvnwbinWrite(t,filepath.Join(js,"main.js"),"PluginManager.setup($plugins);\n"+
  "var fs=require('fs'),p=require('path');var end=Date.now()+12000;function verify(){if(!window.originalGuardRan||!window.originalPluginsRan){fs.writeFileSync(p.join(nw.App.startPath,'r44-result.txt'),'FAIL_GUARD');nw.App.quit();return;}if(window.r44AddonRan){fs.writeFileSync(p.join(nw.App.startPath,'r44-result.txt'),'PASS');nw.App.quit();return;}if(Date.now()>end){fs.writeFileSync(p.join(nw.App.startPath,'r44-result.txt'),'FAIL_ADDON');nw.App.quit();return;}setTimeout(verify,50);}verify();\n")
 snapshot:=mvnwbinSnapshot(t,root)
 // An installer-owned harmless loader probe. Neural/presentation regression
 // is run separately against the real IATraductora.js, not this sentinel.
 plugin:=[]byte("// ◆ IA Traductora · F10\nif(!window.originalGuardRan||!window.originalPluginsRan)throw Error('wrong boot order');window.r44AddonRan=true;\n")
 pkg,e:=readPackage(fakePackageWith(t,plugin,[]byte("synthetic worker; not executed")));if e!=nil{t.Fatal(e)};defer pkg.Close()
 if e=Install(exe,pkg);e!=nil{t.Fatal(e)}
 // Launch only the fresh, authored app directory, not the selected stub EXE.
 ctx,cancel:=context.WithTimeout(context.Background(),90*time.Second);defer cancel()
 cmd:=exec.CommandContext(ctx,filepath.Join(sdk,"nw.exe"),"--disable-background-networking",root)
 cmd.Dir=root
 out,e:=cmd.CombinedOutput()
 if e!=nil{t.Fatalf("native SDK run failed: %v %s",e,out)}
 result,e:=os.ReadFile(filepath.Join(root,"r44-result.txt"))
 if e!=nil||string(result)!="PASS"{t.Fatalf("compiled loader test %q %v",result,e)}
 mvnwbinSame(t,snapshot)
 if e=RecoverGame(exe);e!=nil{t.Fatal(e)}
 after,e:=os.ReadFile(registry);if e!=nil||!bytes.Equal(after,before){t.Fatal("restore failed")}
 mvnwbinSame(t,snapshot)
 t.Log("IA_R44_NWBIN_NATIVE_LOADER_PRESERVE_RESTORE_PASS")
}
