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
