package main

import (
 "bytes"
 "context"
 "fmt"
 "io"
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
 // The real MV entry page declares UTF-8. Without it Chromium can
 // decode external scripts as Windows-1252 and reject Japanese identifiers.
 html.WriteString("<!doctype html><html><head><meta charset=\"UTF-8\"></head><body>\n")
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
// Independently authored one-binary fixture. It represents a publisher
// that chose a single compiled registry in its original HTML. Never use
// this helper on a supplied game or to alter any actual guard.
func mvnwbinSingleFixture(t *testing.T,retainedGuard bool)string{
 t.Helper()
 root:=mvnwbinFixture(t,false)
 content:=filepath.Join(root,"www")
 js:=filepath.Join(content,"js")
 var html strings.Builder
 html.WriteString("<!doctype html><html><head><meta charset=\"UTF-8\"></head><body>\n")
 for _,n:=range mvnwbinCore{fmt.Fprintf(&html,"<script src=\"js/%s\"></script>\n",n)}
 html.WriteString("<script>\nvar w=nw.Window.get();\n<!-- w.evalNWBin(null,require('path').join(nw.App.startPath,'www','js','guard.bin')); -->\nw.evalNWBin(null,require('path').join(nw.App.startPath,'www','js','plugins.bin'));\n</script>\n<script src=\"js/main.js\"></script>\n</body></html>")
 mvnwbinWrite(t,filepath.Join(content,"index.html"),html.String())
 mvnwbinWrite(t,filepath.Join(js,"plugins.js"),`var $plugins = [{"name":"AuthoredExtra","status":true,"description":"Fixture","parameters":{}}];`)
 mvnwbinWrite(t,filepath.Join(js,"plugins","AuthoredExtra.js"),"window.extraFixtureRan=true;\n")
 if !retainedGuard{if e:=os.Remove(filepath.Join(js,"guard.bin"));e!=nil{t.Fatal(e)}}
 return root
}
func mvnwbinProtectedFiles(root string)[]string{
 files:=[]string{filepath.Join(root,"package.json"),filepath.Join(root,"Game.exe"),
  filepath.Join(root,"www","index.html"),filepath.Join(root,"www","js","plugins.bin"),
  filepath.Join(root,"www","js","main.js"),filepath.Join(root,"www","data","System.json")}
 // The live add-on tests intentionally change the plaintext registry.
 // Snapshot it separately in the offline tests where no write is allowed.
 for _,n:=range []string{"guard.bin"}{
  f:=filepath.Join(root,"www","js",filepath.FromSlash(n))
  if mvnwbinMarker(f){files=append(files,f)}
 }
 return files
}
func mvnwbinSnapshot(t *testing.T,root string)map[string]string{
 t.Helper()
 result:=map[string]string{}
 for _,file:=range mvnwbinProtectedFiles(root){
  sum,e:=digestFile(file);if e!=nil{t.Fatal(e)};result[file]=sum
 }
 return result
}
func mvnwbinOfflineSnapshot(t *testing.T,root string)map[string]string{
 t.Helper()
 result:=mvnwbinSnapshot(t,root)
 for _,n:=range []string{"plugins.js","plugins/AuthoredExtra.js"}{
  f:=filepath.Join(root,"www","js",filepath.FromSlash(n))
  if mvnwbinMarker(f){sum,e:=digestFile(f);if e!=nil{t.Fatal(e)};result[f]=sum}
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
func TestR44NWBinEmptyManifestNameDoesNotEnableInstallation(t *testing.T){
 // A blank name in a deployed NWBin app is not a reason to misclassify
 // its engine. It does not authorize adding a new loader either.
 for _,approved:=range []bool{false,true}{
  t.Run(fmt.Sprintf("registry_%t",approved),func(t *testing.T){
   root:=mvnwbinFixture(t,approved)
   exe:=filepath.Join(root,"Game.exe")
   mvnwbinWrite(t,filepath.Join(root,"package.json"),`{"name":"","main":"www/index.html","window":{"width":816,"height":624}}`)
   before:=mvnwbinSnapshot(t,root)
   want:=mvnwbinExtensionUnavailable
   if approved{want=mvnwbinInvalid}
   pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
   if _,e=detectInstallTarget(exe);e==nil||e.Error()!=want{t.Fatalf("incorrect diagnostic: %v; want %s",e,want)}
   if e=Install(exe,pkg);e==nil||e.Error()!=want{t.Fatalf("unsafe install: %v",e)}
   if _,e=os.Lstat(filepath.Join(root,"IA Traductora"));!os.IsNotExist(e){t.Fatal("sidecar created")}
   mvnwbinSame(t,before)
  })
 }
}

func TestR44NWBinSingleRegistryUsesOnlyJSONCopy(t *testing.T){
 for _,retained:=range []bool{true,false}{
  t.Run(fmt.Sprintf("guard_present_%t",retained),func(t *testing.T){
   root:=mvnwbinSingleFixture(t,retained)
   exe:=filepath.Join(root,"Game.exe")
   // A blank deployed app name is not authorization for live install.
   mvnwbinWrite(t,filepath.Join(root,"package.json"),`{"name":"","main":"www/index.html"}`)
   before:=mvnwbinOfflineSnapshot(t,root)
   if _,e:=detectInstallTarget(exe);e==nil||e.Error()!=mvnwbinExtensionUnavailable{t.Fatalf("expected JSON-only route: %v",e)}
   source,content,e:=mvJSONSource(exe)
   if e!=nil||source!=root||content!=filepath.Join(root,"www"){t.Fatalf("JSON copy not recognized: %v",e)}
   pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
   if e=Install(exe,pkg);e==nil||e.Error()!=mvnwbinExtensionUnavailable{t.Fatalf("live install must remain blocked: %v",e)}
   if _,e=os.Lstat(filepath.Join(root,"IA Traductora"));!os.IsNotExist(e){t.Fatal("classifier wrote files")}
   mvnwbinSame(t,before)
   if !retained{if _,e=os.Lstat(filepath.Join(root,"www","js","guard.bin"));!os.IsNotExist(e){t.Fatal("guard manufactured")}}
  })
 }
}
func TestR44NWBinSingleRegistryRejectsIncompleteResources(t *testing.T){
 for _,name:=range []string{"plugins.bin","rpg_windows.js","main.js"}{
  t.Run(name,func(t *testing.T){
   root:=mvnwbinSingleFixture(t,true)
   if e:=os.Remove(filepath.Join(root,"www","js",name));e!=nil{t.Fatal(e)}
   if _,e:=detectInstallTarget(filepath.Join(root,"Game.exe"));e==nil||e.Error()!=mvnwbinInvalid{t.Fatalf("accepted incomplete layout: %v",e)}
  })
 }
 t.Run("active_guard_missing",func(t *testing.T){
  root:=mvnwbinFixture(t,false)
  if e:=os.Remove(filepath.Join(root,"www","js","guard.bin"));e!=nil{t.Fatal(e)}
  if _,e:=detectInstallTarget(filepath.Join(root,"Game.exe"));e==nil||e.Error()!=mvnwbinInvalid{t.Fatalf("accepted broken two-call layout: %v",e)}
 })
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

// NW.js 0.48's Windows nwjc CLI can lose non-ASCII characters in
// absolute command-line paths. Compile only our authored fixture in a
// separate workspace with ASCII relative filenames; publish the unchanged
// binary bytes into the original Unicode test directory using Go file APIs.
// Never compile or transform any binary supplied by the game.
func mvnwbinCompileFixture(t *testing.T,sdk,name,source,destination string){
 t.Helper()
 stage:=t.TempDir()
 srcName,binName:="fixture.js","fixture.bin"
 mvnwbinWrite(t,filepath.Join(stage,srcName),source)
 ctx,cancel:=context.WithTimeout(context.Background(),60*time.Second)
 defer cancel()
 cmd:=exec.CommandContext(ctx,filepath.Join(sdk,"nwjc.exe"),srcName,binName)
 cmd.Dir=stage
 out,e:=cmd.CombinedOutput()
 compiled:=filepath.Join(stage,binName)
 if e!=nil||!mvnwbinRegular(compiled,64*1024*1024){t.Fatalf("nwjc %s fixture compilation failed: %v %s",name,e,out)}
 before,e:=digestFile(compiled);if e!=nil{t.Fatal(e)}
 if e=mvnwbinPublishCompiledFixture(compiled,destination);e!=nil{t.Fatal(e)}
 after,e:=digestFile(destination);if e!=nil||before!=after{t.Fatalf("compiled %s bytes changed: %v",name,e)}
 t.Logf("IA_R44_NWBIN_FIXTURE_COMPILED name=%s sha256=%s",name,after)
}

// Destination is an existing synthetic placeholder, not a user binary.
// Copy the generated bytes without changing the contents; require that the
// final path is a new file, never silently overwrite an unexpected file.
func mvnwbinPublishCompiledFixture(source,destination string)error{
 f,e:=os.Open(source);if e!=nil{return e};defer f.Close()
 out,e:=os.OpenFile(destination,os.O_WRONLY|os.O_CREATE|os.O_EXCL,0600)
 if e!=nil{return e}
 n,copyErr:=io.Copy(out,io.LimitReader(f,64*1024*1024+1))
 syncErr:=out.Sync()
 closeErr:=out.Close()
 if copyErr!=nil{return copyErr}
 if n<=0||n>64*1024*1024{return fmt.Errorf("invalid compiled fixture size: %d",n)}
 if syncErr!=nil{return syncErr}
 return closeErr
}

func TestR44NWBinCompiledFixtureUnicodeCopy(t *testing.T){
 root:=filepath.Join(t.TempDir(),"日本語 café jogo")
 if e:=os.Mkdir(root,0700);e!=nil{t.Fatal(e)}
 source:=filepath.Join(t.TempDir(),"fixture.bin")
 destination:=filepath.Join(root,"fixture.bin")
 raw:=[]byte{0,255,128,10,13,0,65,42}
 if e:=os.WriteFile(source,raw,0600);e!=nil{t.Fatal(e)}
 if e:=mvnwbinPublishCompiledFixture(source,destination);e!=nil{t.Fatal(e)}
 b,e:=os.ReadFile(destination);if e!=nil||!bytes.Equal(raw,b){t.Fatal("binary changed",e)}
 if e=mvnwbinPublishCompiledFixture(source,destination);e==nil{t.Fatal("overwrote existing destination")}
 b,e=os.ReadFile(destination);if e!=nil||!bytes.Equal(raw,b){t.Fatal("existing bytes changed",e)}
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
  bin:=filepath.Join(js,item.name+".bin")
  if e=os.Remove(bin);e!=nil{t.Fatal(e)}
  mvnwbinCompileFixture(t,sdk,item.name,item.source,bin)
 }
 mvnwbinWrite(t,filepath.Join(js,"rpg_managers.js"),"window.PluginManager={setup:function(list){list.forEach(function(p){if(p.status){var s=document.createElement('script');s.src='js/plugins/'+p.name+'.js';s.charset='UTF-8';s.async=false;document.body.appendChild(s);}});}};\n")
 mvnwbinWrite(t,filepath.Join(js,"main.js"),"PluginManager.setup($plugins);\n"+
  "var fs=require('fs'),p=require('path');var end=Date.now()+12000;function verify(){if(!window.originalGuardRan||!window.originalPluginsRan){fs.writeFileSync(p.join(nw.App.startPath,'r44-result.txt'),'FAIL_GUARD');nw.App.quit();return;}if(window.r44AddonRan){fs.writeFileSync(p.join(nw.App.startPath,'r44-result.txt'),'PASS');nw.App.quit();return;}if(Date.now()>end){fs.writeFileSync(p.join(nw.App.startPath,'r44-result.txt'),'FAIL_ADDON');nw.App.quit();return;}setTimeout(verify,50);}verify();\n")
 t.Log("IA_R44_NWBIN_BOTH_BINARIES_READY")
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
