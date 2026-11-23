package main

import(
 "archive/zip"
 "bytes"
 "encoding/binary"
 "encoding/json"
 "encoding/hex"
 "os"
 "path/filepath"
 "strings"
 "testing"
)

func TestNewBrandAndSafeRegistry(t *testing.T){
 original:=[]byte("// publisher header\nvar $plugins = [\n{\"name\":\"MPP_MessageEX\",\"status\":true,\"parameters\":{}}\n];\n")
 revised,err:=appendRegistry(original)
 if err!=nil{t.Fatal(err)}
 if !bytes.HasPrefix(revised,[]byte("// publisher header")){t.Fatal("original publisher bytes changed")}
 if !bytes.Contains(revised,[]byte(`"name":"IATraductora"`)){t.Fatal("new plugin not registered")}
 if bytes.Contains(revised,[]byte("TENSHIXGAME RPG")){t.Fatal("old branding leaked into plugin")}
 if !bytes.Equal(original,append([]byte{},original...)){t.Fatal("original registry altered")}
 if _,err=appendRegistry(revised);err==nil{t.Fatal("duplicate plugin silently added")}
}
func TestLegacyEngineIsRejectedUntilVerifiedMigration(t *testing.T){
 old:=[]byte(`var $plugins = [{"name":"TenshixgameRPGLive","status":true,"parameters":{}}];`)
 _,err:=appendRegistry(old)
 if err==nil||!strings.Contains(err.Error(),"MIGRACION"){t.Fatal("old active process must never run concurrently")}
}
func createFixture(t *testing.T)string{
 t.Helper()
 game:=filepath.Join(t.TempDir(),"日本語 jogo RPG MV")
 js:=filepath.Join(game,"www","js")
 if err:=os.MkdirAll(filepath.Join(js,"plugins"),0700);err!=nil{t.Fatal(err)}
 if err:=os.MkdirAll(filepath.Join(game,"www","data"),0700);err!=nil{t.Fatal(err)}
 for _,file:=range []string{filepath.Join(js,"rpg_core.js"),filepath.Join(game,"www","data","System.json")}{
  if err:=os.WriteFile(file,[]byte("{}"),0600);err!=nil{t.Fatal(err)}
 }
 if err:=os.WriteFile(filepath.Join(js,"plugins.js"),[]byte(`var $plugins = [];`),0600);err!=nil{t.Fatal(err)}
 if err:=os.WriteFile(filepath.Join(game,"Game.exe"),[]byte("synthetic only"),0600);err!=nil{t.Fatal(err)}
 return game
}
func TestGameMVPathAndForeignFile(t *testing.T){
 game:=createFixture(t)
 root,content,err:=detectGame(filepath.Join(game,"Game.exe"))
 if err!=nil||root!=game||!strings.HasSuffix(content,"www"){t.Fatal("MV path not recognized")}
 if err:=os.WriteFile(filepath.Join(game,"www","js","plugins","IATraductora.js"),[]byte("unknown"),0600);err!=nil{t.Fatal(err)}
 if !ordinary(filepath.Join(game,"www","js","plugins","IATraductora.js")){t.Fatal("foreign plugin missing")}
}
func fakePackage(t *testing.T)string{
 return fakePackageWith(t,[]byte("◆ IA Traductora · F10 \n IA Traductora · V95"),[]byte("fake neutron FOR TEST ONLY"))
}
func fakePackageWith(t *testing.T,plugin,worker []byte)string{
 t.Helper()
 directory:=t.TempDir();packageEXE:=filepath.Join(directory,"Servidor.exe")
 required:=map[string][]byte{
 "IATraductora.exe":worker,
 "IATraductora.js":plugin,
 "models/opus_ja_es/model.bin":[]byte("m"),
 "models/opus_ja_es/source.spm":[]byte("s"),
 "models/opus_ja_es/target.spm":[]byte("t"),
 "models/opus_en_es/model.bin":[]byte("m"),
 "models/opus_en_es/source.spm":[]byte("s"),
 "models/opus_en_es/target.spm":[]byte("t"),
 }
 manifest:=packageManifest{Schema:packageSchema,Files:map[string]string{}}
 for k,v:=range required{manifest.Files[k]=hash(v)}
 buffer:=new(bytes.Buffer);zw:=zip.NewWriter(buffer)
 for k,v:=range required{
  out,err:=zw.Create(k);if err!=nil{t.Fatal(err)}
  if _,err=out.Write(v);err!=nil{t.Fatal(err)}
 }
 record,_:=json.Marshal(manifest);entry,_:=zw.Create("manifest.json");entry.Write(record)
 if err:=zw.Close();err!=nil{t.Fatal(err)}
 data:=buffer.Bytes()
 foot:=make([]byte,56);binary.LittleEndian.PutUint64(foot,uint64(len(data)))
 sum:=sha256ForTest(data);copy(foot[8:40],sum)
 copy(foot[40:],[]byte(packageMagic))
 final:=append([]byte("fake bootstrap EXE -- test"),data...)
 final=append(final,foot...)
 if err:=os.WriteFile(packageEXE,final,0600);err!=nil{t.Fatal(err)}
 return packageEXE
}
func sha256ForTest(data []byte)[]byte{sum:=hash(data);raw,_:=hexDecodeForTest(sum);return raw}
func hexDecodeForTest(s string)([]byte,error){
 return hex.DecodeString(s)
}
func TestNewInstallerWorksOnClosedCopyAndVerifiesNewPaths(t *testing.T){
 packageEXE:=fakePackage(t)
 pkg,err:=readPackage(packageEXE);if err!=nil{t.Fatal(err)}
 defer pkg.Close()
 game:=createFixture(t)
 original,_:=os.ReadFile(filepath.Join(game,"www","js","plugins.js"))
 if err=Install(filepath.Join(game,"Game.exe"),pkg);err!=nil{t.Fatal(err)}
 for _,rel:=range []string{"IA Traductora/.local/Rpg/engine/IATraductora.exe",
 "IA Traductora/owner-v1.json","IA Traductora/install/original-plugins.js",
 "www/js/plugins/IATraductora.js"}{
  if !ordinary(filepath.Join(game,filepath.FromSlash(rel))){t.Fatalf("missing %s",rel)}
 }
 backup,_:=os.ReadFile(filepath.Join(game,"IA Traductora","install","original-plugins.js"))
 if !bytes.Equal(original,backup){t.Fatal("player registry backup modified")}
 if _,err:=os.Stat(filepath.Join(game,"Tenshixgame-IA"));!os.IsNotExist(err){t.Fatal("old folder created")}
}


func TestVerifiedPluginUpgradeInPlace(t *testing.T){
    oldJS:=[]byte("◆ IA Traductora · F10\n // MV plugin release A")
    newJS:=[]byte("◆ IA Traductora · F10\n // MV plugin release B - fixed game root")
    worker:=[]byte("unchanged owned worker")
    oldPath:=fakePackageWith(t,oldJS,worker)
    newPath:=fakePackageWith(t,newJS,worker)
    first,e:=readPackage(oldPath);if e!=nil{t.Fatal(e)};defer first.Close()
    second,e:=readPackage(newPath);if e!=nil{t.Fatal(e)};defer second.Close()
    game:=createFixture(t)
    registry:=filepath.Join(game,"www","js","plugins.js")
    original,_:=os.ReadFile(registry)
    if e=Install(filepath.Join(game,"Game.exe"),first);e!=nil{t.Fatal(e)}
    installedRegistry,_:=os.ReadFile(registry)
    if e=Install(filepath.Join(game,"Game.exe"),second);e!=nil{
        t.Fatalf("owned plugin must upgrade instead of silently claiming installed: %v",e)
    }
    pluginFile:=filepath.Join(game,"www","js","plugins","IATraductora.js")
    updated,_:=os.ReadFile(pluginFile)
    if !bytes.Equal(updated,newJS){t.Fatal("game is still running old plugin")}
    currentRegistry,_:=os.ReadFile(registry)
    if !bytes.Equal(installedRegistry,currentRegistry){t.Fatal("upgrade changed game's plugin registry")}
    backup,_:=os.ReadFile(filepath.Join(game,"IA Traductora","install","original-plugins.js"))
    if !bytes.Equal(backup,original){t.Fatal("upgrade changed original registry backup")}
    versioned:=filepath.Join(game,"IA Traductora","install","updates",hash(oldJS)+".js")
    if got,_:=os.ReadFile(versioned);!bytes.Equal(got,oldJS){t.Fatal("previous plugin not preserved")}
    if e=Install(filepath.Join(game,"Game.exe"),second);e!=nil{t.Fatalf("idempotent reinstall: %v",e)}
}
func TestDifferentModelCannotBeFalselyUpgraded(t *testing.T){
    pluginA:=[]byte("◆ IA Traductora · F10\nrelease A")
    pluginB:=[]byte("◆ IA Traductora · F10\nrelease B")
    pathA:=fakePackageWith(t,pluginA,[]byte("worker A"))
    pathB:=fakePackageWith(t,pluginB,[]byte("worker B"))
    a,e:=readPackage(pathA);if e!=nil{t.Fatal(e)};defer a.Close()
    b,e:=readPackage(pathB);if e!=nil{t.Fatal(e)};defer b.Close()
    game:=createFixture(t)
    if e=Install(filepath.Join(game,"Game.exe"),a);e!=nil{t.Fatal(e)}
    registry:=filepath.Join(game,"www","js","plugins.js")
    before,_:=os.ReadFile(registry)
    if e=Install(filepath.Join(game,"Game.exe"),b);e!=nil{
        t.Fatalf("verified app-owned worker should be updated safely: %v",e)
    }
    after,_:=os.ReadFile(registry)
    if !bytes.Equal(before,after){t.Fatal("worker update changed game registry")}
    pluginFile:=filepath.Join(game,"www","js","plugins","IATraductora.js")
    if got,_:=os.ReadFile(pluginFile);!bytes.Equal(got,pluginB){
        t.Fatal("new plugin bytes were not installed")
    }
    workerFile:=filepath.Join(game,"IA Traductora",".local","Rpg","engine","IATraductora.exe")
    if got,_:=os.ReadFile(workerFile);!bytes.Equal(got,[]byte("worker B")){
        t.Fatal("new worker bytes were not installed")
    }
    backupWorker:=filepath.Join(game,"IA Traductora","install","updates",hash([]byte("worker A"))+".exe")
    if got,_:=os.ReadFile(backupWorker);!bytes.Equal(got,[]byte("worker A")){
        t.Fatal("previous worker backup missing")
    }
}

func TestTamperedModelPreventsOwnedUpgrade(t *testing.T){
    oldJS:=[]byte("◆ IA Traductora · F10\nrelease A")
    newJS:=[]byte("◆ IA Traductora · F10\nrelease B")
    oldPath:=fakePackageWith(t,oldJS,[]byte("worker A"))
    newPath:=fakePackageWith(t,newJS,[]byte("worker B"))
    a,e:=readPackage(oldPath);if e!=nil{t.Fatal(e)};defer a.Close()
    b,e:=readPackage(newPath);if e!=nil{t.Fatal(e)};defer b.Close()
    game:=createFixture(t)
    if e=Install(filepath.Join(game,"Game.exe"),a);e!=nil{t.Fatal(e)}
    tampered:=filepath.Join(game,"IA Traductora",".local","Rpg","engine","models","opus_ja_es","model.bin")
    if e=os.WriteFile(tampered,[]byte("changed weights"),0600);e!=nil{t.Fatal(e)}
    if e=Install(filepath.Join(game,"Game.exe"),b);e==nil||
       !strings.Contains(e.Error(),"MOTOR_VERSION_DISTINTA"){
       t.Fatalf("tampered models must not be replaced or accepted: %v",e)
    }
    worker:=filepath.Join(game,"IA Traductora",".local","Rpg","engine","IATraductora.exe")
    if got,_:=os.ReadFile(worker);!bytes.Equal(got,[]byte("worker A")){
        t.Fatal("tampered model caused destructive worker upgrade")
    }
}


func TestRecoverGameOriginalRegistryAndPreservePlayerSaves(t *testing.T){
  pkgPath:=fakePackage(t)
  pkg,e:=readPackage(pkgPath);if e!=nil{t.Fatal(e)};defer pkg.Close()
  game:=createFixture(t)
  source:=filepath.Join(game,"Game.exe")
  registry:=filepath.Join(game,"www","js","plugins.js")
  original,_:=os.ReadFile(registry)
  save:=filepath.Join(game,"www","save","File1.rpgsave")
  if e=os.MkdirAll(filepath.Dir(save),0700);e!=nil{t.Fatal(e)}
  if e=os.WriteFile(save,[]byte("PLAYER GAME SAVE"),0600);e!=nil{t.Fatal(e)}
  if e=Install(source,pkg);e!=nil{t.Fatal(e)}
  installed,_:=os.ReadFile(registry)
  if bytes.Equal(original,installed){t.Fatal("MV fixture was not installed")}
  if e=RecoverGame(source);e!=nil{t.Fatal(e)}
  restored,_:=os.ReadFile(registry)
  if !bytes.Equal(restored,original){t.Fatal("original plugins.js was not restored byte-identically")}
  if e=RecoverGame(source);e!=nil{t.Fatalf("repeat recovery rejected: %v",e)}
  saved,_:=os.ReadFile(save)
  if string(saved)!="PLAYER GAME SAVE"{t.Fatal("player save was modified")}
  if !ordinary(filepath.Join(game,"www","js","plugins","IATraductora.js")){
    t.Fatal("recovery removed the translator plugin instead of safely deactivating it")
  }
  snapshot:=filepath.Join(game,"IA Traductora","install","recovery",hash(installed)+".plugins.js")
  persisted,_:=os.ReadFile(snapshot)
  if !bytes.Equal(persisted,installed){t.Fatal("installed registry snapshot missing")}
}
func TestRecoverGameFailClosedOnAlteredUserRegistryAndBackup(t *testing.T){
  path:=fakePackage(t);pkg,e:=readPackage(path);if e!=nil{t.Fatal(e)};defer pkg.Close()
  game:=createFixture(t)
  registry:=filepath.Join(game,"www","js","plugins.js")
  if e=Install(filepath.Join(game,"Game.exe"),pkg);e!=nil{t.Fatal(e)}
  current,_:=os.ReadFile(registry)
  modified:=append(append([]byte{},current...),[]byte("\n// user edit")...)
  if e=os.WriteFile(registry,modified,0600);e!=nil{t.Fatal(e)}
  if e=RecoverGame(filepath.Join(game,"Game.exe"));e==nil||
    !strings.Contains(e.Error(),"REGISTRO_CAMBIADO"){t.Fatalf("must refuse changed MV registry: %v",e)}
  if got,_:=os.ReadFile(registry);!bytes.Equal(got,modified){t.Fatal("user registry overwritten")}
  if e=os.WriteFile(registry,current,0600);e!=nil{t.Fatal(e)}
  backup:=filepath.Join(game,"IA Traductora","install","original-plugins.js")
  if e=os.WriteFile(backup,[]byte("tampered"),0600);e!=nil{t.Fatal(e)}
  if e=RecoverGame(filepath.Join(game,"Game.exe"));e==nil||
    !strings.Contains(e.Error(),"RESPALDO_ALTERADO"){t.Fatalf("must reject tampered backup: %v",e)}
  if got,_:=os.ReadFile(registry);!bytes.Equal(got,current){t.Fatal("tampered backup caused changes")}
}

func TestInactivePluginDoesNotCountAsInstalled(t *testing.T){
    reg:=[]byte("var $plugins=[{\"name\":\"IATraductora\",\"status\":false,\"parameters\":{}}];")
    if _,e:=appendRegistry(reg);e==nil||!strings.Contains(e.Error(),"DESACTIVADO"){
        t.Fatalf("inactive registry must not be silently accepted: %v",e)
    }
    duplicate:=[]byte("var $plugins=[{\"name\":\"IATraductora\",\"status\":true},{\"name\":\"IATraductora\",\"status\":true}];")
    if _,e:=appendRegistry(duplicate);e==nil||!strings.Contains(e.Error(),"DUPLICADO"){
        t.Fatalf("duplicated own plugin must be rejected: %v",e)
    }
}


func TestReinstallCompleteNeuralPackageAfterVerifiedRecovery(t *testing.T){
    firstPath:=fakePackageWith(t,[]byte("◆ IA Traductora · F10\nversion A"),[]byte("worker A"))
    secondPath:=fakePackageWith(t,[]byte("◆ IA Traductora · F10\nversion B"),[]byte("worker B"))
    a,e:=readPackage(firstPath);if e!=nil{t.Fatal(e)};defer a.Close()
    b,e:=readPackage(secondPath);if e!=nil{t.Fatal(e)};defer b.Close()
    game:=createFixture(t);gameEXE:=filepath.Join(game,"Game.exe")
    reg:=filepath.Join(game,"www","js","plugins.js")
    original,_:=os.ReadFile(reg)
    save:=filepath.Join(game,"www","save","File1.rpgsave")
    if e=os.MkdirAll(filepath.Dir(save),0700);e!=nil{t.Fatal(e)}
    if e=os.WriteFile(save,[]byte("ORIGINAL_PLAYER_SAVE"),0600);e!=nil{t.Fatal(e)}
    if e=Install(gameEXE,a);e!=nil{t.Fatal(e)}
    if e=RecoverGame(gameEXE);e!=nil{t.Fatal(e)}
    restored,_:=os.ReadFile(reg)
    if !bytes.Equal(restored,original){t.Fatal("recovery failed before reinstall")}
    if e=Install(gameEXE,b);e!=nil{t.Fatalf("reinstall must accept verified owned files: %v",e)}
    current,_:=os.ReadFile(reg)
    if bytes.Equal(current,original)||!bytes.Contains(current,[]byte("\"name\":\"IATraductora\"")){
        t.Fatal("verified recovery did not reactivate translator")
    }
    pluginFile:=filepath.Join(game,"www","js","plugins","IATraductora.js")
    if p,_:=os.ReadFile(pluginFile);!bytes.Contains(p,[]byte("version B")){
        t.Fatal("game still has stale plugin")
    }
    if saveData,_:=os.ReadFile(save);string(saveData)!="ORIGINAL_PLAYER_SAVE"{
        t.Fatal("reinstall modified player's saves")
    }
    if e=Install(gameEXE,b);e!=nil{t.Fatalf("verified repeat install rejected: %v",e)}
}
func TestReinstallFailsClosedWhenOwnedJSModifiedAfterRecovery(t *testing.T){
    pack:=fakePackage(t)
    pkg,e:=readPackage(pack);if e!=nil{t.Fatal(e)};defer pkg.Close()
    game:=createFixture(t);gameEXE:=filepath.Join(game,"Game.exe")
    reg:=filepath.Join(game,"www","js","plugins.js")
    if e=Install(gameEXE,pkg);e!=nil{t.Fatal(e)}
    if e=RecoverGame(gameEXE);e!=nil{t.Fatal(e)}
    original,_:=os.ReadFile(reg)
    pluginFile:=filepath.Join(game,"www","js","plugins","IATraductora.js")
    if e=os.WriteFile(pluginFile,[]byte("foreign edit"),0600);e!=nil{t.Fatal(e)}
    if e=Install(gameEXE,pkg);e==nil{t.Fatal("must reject foreign JS after recovery")}
    now,_:=os.ReadFile(reg)
    if !bytes.Equal(now,original){t.Fatal("failed reinstall changed game's original registry")}
}
