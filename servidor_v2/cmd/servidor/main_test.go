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
 t.Helper()
 directory:=t.TempDir();packageEXE:=filepath.Join(directory,"Servidor.exe")
 required:=map[string][]byte{
 "IATraductora.exe":[]byte("fake neutron FOR TEST ONLY"),
 "IATraductora.js":[]byte("◆ IA Traductora · F10 
 IA Traductora · V95"),
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
