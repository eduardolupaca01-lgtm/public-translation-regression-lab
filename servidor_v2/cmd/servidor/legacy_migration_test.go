package main

import(
 "encoding/json"
 "os"
 "path/filepath"
 "strings"
 "testing"
)

func legacyGameFixture(t *testing.T)(string,[]byte){
 t.Helper()
 root:=createFixture(t)
 oldRoot:=filepath.Join(root,"Tenshixgame-IA")
 worker:=filepath.Join(oldRoot,".local","TENSHIXGAME-RPG","engine","engine","TenshixgameAI.exe")
 if err:=os.MkdirAll(filepath.Dir(worker),0700);err!=nil{t.Fatal(err)}
 model:=[]byte("old owned engine bytes, never executed")
 if err:=os.WriteFile(worker,model,0600);err!=nil{t.Fatal(err)}
 owner:=oldOwner{Schema:"tenshixgame-rpg-portable-owner-v1",
  Product:"TENSHIXGAME-RPG",WorkerSHA:hash(model)}
 ownerBytes,_:=json.Marshal(owner)
 if err:=os.WriteFile(filepath.Join(oldRoot,"portable-owner-v1.json"),ownerBytes,0600);err!=nil{t.Fatal(err)}
 oldRegistry:=[]byte("var $plugins = [];")
 updated:=[]byte("var $plugins = [{\"name\":\"TenshixgameRPGLive\",\"status\":true,\"parameters\":{}}];")
 plugin:=[]byte("// previous verified-plugin fixture, not executable")
 oldPlugin:=filepath.Join(root,"www","js","plugins","TenshixgameRPGLive.js")
 if err:=os.WriteFile(oldPlugin,plugin,0600);err!=nil{t.Fatal(err)}
 journal:=filepath.Join(oldRoot,".local","TENSHIXGAME-RPG","game-workspaces","testowner","tx395-rpg-live")
 if err:=os.MkdirAll(journal,0700);err!=nil{t.Fatal(err)}
 record:=oldPluginJournal{Schema:"tenshixgame-rpg-live-plugin-v1",
  Engine:"mv",Status:"INSTALLED",OriginalSHA:hash(oldRegistry),
  UpdatedSHA:hash(updated),PluginSHA:hash(plugin)}
 data,_:=json.Marshal(record)
 if err:=os.WriteFile(filepath.Join(journal,"manifest.json"),data,0600);err!=nil{t.Fatal(err)}
 if err:=os.WriteFile(filepath.Join(journal,"original-plugins.js"),oldRegistry,0600);err!=nil{t.Fatal(err)}
 registry:=filepath.Join(root,"www","js","plugins.js")
 if err:=os.WriteFile(registry,updated,0600);err!=nil{t.Fatal(err)}
 save:=filepath.Join(root,"www","save","File1.rpgsave")
 if err:=os.MkdirAll(filepath.Dir(save),0700);err!=nil{t.Fatal(err)}
 if err:=os.WriteFile(save,[]byte("PLAYER DATA"),0600);err!=nil{t.Fatal(err)}
 return root,updated
}
func TestVerifiedMigrationMovesOnlyOriginalOwnedFilesIntoNewBackup(t *testing.T){
 pkgPath:=fakePackage(t)
 pkg,e:=readPackage(pkgPath);if e!=nil{t.Fatal(e)};defer pkg.Close()
 game,_:=legacyGameFixture(t)
 if err:=Install(filepath.Join(game,"Game.exe"),pkg);err!=nil{t.Fatal(err)}
 newRoot:=filepath.Join(game,"IA Traductora")
 if !ordinary(filepath.Join(newRoot,".local","Rpg","engine","IATraductora.exe")){
  t.Fatal("new independent worker missing")
 }
 if _,err:=os.Stat(filepath.Join(game,"Tenshixgame-IA"));!os.IsNotExist(err){
  t.Fatal("old runtime still visible in game root")
 }
 archived:=filepath.Join(newRoot,"Respaldos","runtime-anterior","portable-owner-v1.json")
 if !ordinary(archived){t.Fatal("legacy marker not preserved as recovery archive")}
 if !ordinary(filepath.Join(newRoot,"Respaldos","plugin-anterior.js")){
  t.Fatal("old plugin not preserved")
 }
 reg,_:=os.ReadFile(filepath.Join(game,"www","js","plugins.js"))
 if strings.Contains(string(reg),`"name":"TenshixgameRPGLive"`)||
   !strings.Contains(string(reg),`"name":"IATraductora"`){
  t.Fatal("registry still launches old bridge or omitted IA")
 }
 save,_:=os.ReadFile(filepath.Join(game,"www","save","File1.rpgsave"))
 if string(save)!="PLAYER DATA"{t.Fatal("player save was modified")}
 if err:=Install(filepath.Join(game,"Game.exe"),pkg);err!=nil{
  t.Fatal("idempotent reinstall rejected:",err)
 }
}
func TestLegacyMigrationRefusesModifiedGameRegistry(t *testing.T){
 pkgPath:=fakePackage(t)
 pkg,e:=readPackage(pkgPath);if e!=nil{t.Fatal(e)};defer pkg.Close()
 game,original:=legacyGameFixture(t)
 registry:=filepath.Join(game,"www","js","plugins.js")
 edited:=append(append([]byte{},original...),[]byte("// user edited")...)
 if err:=os.WriteFile(registry,edited,0600);err!=nil{t.Fatal(err)}
 if err:=Install(filepath.Join(game,"Game.exe"),pkg);err==nil{
  t.Fatal("must not migrate journal whose registry SHA has changed")
 }
 after,_:=os.ReadFile(registry)
 if string(after)!=string(edited){t.Fatal("rejected migration altered user registry")}
 if _,err:=os.Stat(filepath.Join(game,"Tenshixgame-IA"));err!=nil{
  t.Fatal("rejected migration removed old runtime")
 }
}
func TestLegacyMigrationRefusesForgedWorker(t *testing.T){
 pkgPath:=fakePackage(t)
 pkg,e:=readPackage(pkgPath);if e!=nil{t.Fatal(e)};defer pkg.Close()
 game,original:=legacyGameFixture(t)
 worker:=filepath.Join(game,"Tenshixgame-IA",".local","TENSHIXGAME-RPG","engine","engine","TenshixgameAI.exe")
 if err:=os.WriteFile(worker,[]byte("not original"),0600);err!=nil{t.Fatal(err)}
 if err:=Install(filepath.Join(game,"Game.exe"),pkg);err==nil{
  t.Fatal("mismatched worker must stop migration")
 }
 current,_:=os.ReadFile(filepath.Join(game,"www","js","plugins.js"))
 if string(current)!=string(original){t.Fatal("bad legacy model must not alter game")}
}
