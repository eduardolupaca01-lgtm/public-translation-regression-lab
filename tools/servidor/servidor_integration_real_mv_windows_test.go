//go:build windows

package main

// This deliberately uses the ACTUAL 22-file V95 package from the signed
// onefile built in CI. The synthetic MV fixture is never launched and no
// private player's files are accessed. A passing test proves installation,
// not live gameplay with a commercial MV game.
import (
    "bytes"
    "os"
    "path/filepath"
    "strings"
    "testing"

    cleanhost "github.com/camachogomez791-byte/tenshixgame-tx20026/reference/tx331-clean-product-host"
)

func TestServidorIntegratedRealV95MVInstallAndRestore(t *testing.T){
    if os.Getenv("TX779_REAL_ENGINE_TEST")!="1"{
        t.Skip("only isolated Windows CI with the authentic signed V95 package")
    }
    originalEXE:=os.Getenv("TX779_REAL_ONEFILE_EXE")
    if !filepath.IsAbs(originalEXE){t.Fatal("TX779_AUTHENTIC_ONEFILE_REQUIRED")}
    exeInfo,err:=os.Lstat(originalEXE)
    if err!=nil||!exeInfo.Mode().IsRegular()||exeInfo.Mode()&os.ModeSymlink!=0||
        exeInfo.Size()<250*1024*1024{
        t.Fatal("TX779_SIGNED_V95_EXE_NOT_VERIFIED_OR_MISSING")
    }
    payload,err:=openAppended(originalEXE)
    if err!=nil{t.Fatal("TX779_REAL_ONEFILE_SHA_OR_MANIFEST_FAILED")}
    defer payload.close()

    root:=filepath.Join(t.TempDir(),"日本語 RPG Maker MV sólo prueba")
    js:=filepath.Join(root,"www","js")
    data:=filepath.Join(root,"www","data")
    if err:=os.MkdirAll(filepath.Join(js,"plugins"),0700);err!=nil{t.Fatal(err)}
    if err:=os.MkdirAll(data,0700);err!=nil{t.Fatal(err)}
    for _,name:=range []string{"rpg_core.js","rpg_managers.js"}{
        if err:=os.WriteFile(filepath.Join(js,name),[]byte("// original MV signature fixture"),0600);err!=nil{t.Fatal(err)}
    }
    originalList:=[]byte("\xef\xbb\xbf// Original game publisher plugin list\r\nvar $plugins=[];\r\n")
    registry:=filepath.Join(js,"plugins.js")
    if err:=os.WriteFile(registry,originalList,0600);err!=nil{t.Fatal(err)}
    if err:=os.WriteFile(filepath.Join(data,"System.json"),[]byte("{}"),0600);err!=nil{t.Fatal(err)}
    gameEXE:=filepath.Join(root,"Game.exe")
    if err:=os.WriteFile(gameEXE,[]byte("disposable MV marker - NEVER launch"),0600);err!=nil{t.Fatal(err)}
    save:=filepath.Join(root,"www","save","File1.rpgsave")
    if err:=os.MkdirAll(filepath.Dir(save),0700);err!=nil{t.Fatal(err)}
    if err:=os.WriteFile(save,[]byte("player-save-unchanged"),0600);err!=nil{t.Fatal(err)}

    _,local,err:=tx771PreparePortableOnefile(payload,root)
    if err!=nil{t.Fatal("TX779_AUTHENTIC_V95_PACKAGE_CANNOT_PREPARE_IN_GAME")}
    if err:=servidorInstallMV(gameEXE,local);err!=nil{
        t.Fatalf("TX779_ONE_APP_DIRECT_INSTALLATION_FAILED: %v",err)
    }
    updated,err:=os.ReadFile(registry)
    if err!=nil||bytes.Equal(updated,originalList)||
        !bytes.Contains(updated,[]byte("TenshixgameRPGLive")){
        t.Fatal("TX779_MV_PLUGIN_NOT_REGISTERED_BY_DIRECT_SERVIDOR")
    }
    gamePlugin:=filepath.Join(js,"plugins","TenshixgameRPGLive.js")
    source,err:=os.ReadFile(gamePlugin)
    if err!=nil||len(source)<20000||len(source)>1024*1024{
        t.Fatal("TX779_MV_SIGNED_JS_MISSING_OR_INVALID_SIZE")
    }
    owner,err:=tx771OwnerFile(filepath.Join(root,tx771OnefileSidecar,"portable-owner-v1.json"))
    if err!=nil{t.Fatal("TX779_NO_AUTHENTIC_WORKER_MARKER")}
    for _,needed:=range []string{
        owner.WorkerSHA256,
        "tx771PortableRuntime",
        "TenshigameTranduccion",
        "TenshigameTraduccion",
        "embedded-v87-bridge.json",
        "127.0.0.1",
        "/translate",
    }{
        if !strings.Contains(string(source),needed){
            t.Fatal("TX779_SIGNED_MV_JS_MISSING_WORKER_PIN_OR_BRIDGE_CONTRACT")
        }
    }
    if err:=servidorInstallMV(gameEXE,local);err!=nil{
        t.Fatalf("TX779_REPEATED_INSTALL_SHOULD_VERIFY_NOT_OVERWRITE: %v",err)
    }
    current,err:=os.ReadFile(gamePlugin)
    if err!=nil||!bytes.Equal(current,source){
        t.Fatal("TX779_IDEMPOTENT_PLUGIN_CHANGED_BYTES")
    }
    workspace,err:=servidorMVWorkspace(root,local,"auto")
    if err!=nil{t.Fatal(err)}
    ok,err:=cleanhost.RestoreRPGLivePlugin(gameEXE,workspace)
    if err!=nil||!ok{t.Fatalf("TX779_OWNER_VERIFIED_RESTORE_FAILED: %v",err)}
    restored,err:=os.ReadFile(registry)
    if err!=nil||!bytes.Equal(restored,originalList){
        t.Fatal("TX779_PLAYER_PLUGIN_LIST_NOT_RESTORED_EXACTLY")
    }
    oldSave,err:=os.ReadFile(save)
    if err!=nil||string(oldSave)!="player-save-unchanged"{
        t.Fatal("TX779_PLAYER_SAVE_MODIFIED")
    }
}
