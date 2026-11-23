//go:build windows

package main

// Servidor's only user-facing installer for RPG Maker MV.
// V95 remains an authenticated background neural process. Installation,
// rollback and game file updates reuse the same verified cleanhost package
// as the old specialized UI, NOT that UI executable.
import (
    "crypto/sha256"
    "encoding/hex"
    "errors"
    "fmt"
    "os"
    "path/filepath"
    "strings"

    cleanhost "github.com/camachogomez791-byte/tenshixgame-tx20026/reference/tx331-clean-product-host"
)

func servidorMVWorkspace(gameRoot,local,language string)(string,error){
    if language!="auto"&&language!="en"&&language!="ja" {
        return "",errors.New("TX779_UNSUPPORTED_SOURCE_LANGUAGE")
    }
    canon,err:=filepath.EvalSymlinks(filepath.Clean(gameRoot))
    if err!=nil{return "",fmt.Errorf("TX779_GAME_ROOT_NOT_CANONICAL: %w",err)}
    if !filepath.IsAbs(canon) {return "",errors.New("TX779_GAME_PATH_NOT_ABSOLUTE")}
    digest:=sha256.Sum256([]byte(strings.ToLower(canon)+"\x00"+"rpgmaker-mv-mz"+"\x00"+language))
    return filepath.Join(local,"TENSHIXGAME-RPG","game-workspaces",
        hex.EncodeToString(digest[:16])),nil
}

func servidorInstallMV(gameEXE,local string)error{
    root,err:=servidorMVGameRoot(gameEXE)
    if err!=nil{return fmt.Errorf("TX779_ONLY_MV_SELECTED: %w",err)}
    selectedLocal:=filepath.Join(root,tx771OnefileSidecar,".local")
    actual,err:=os.Stat(local)
    if err!=nil{return fmt.Errorf("TX779_LOCAL_ENGINE_NOT_FOUND: %w",err)}
    expected,err:=os.Stat(selectedLocal)
    if err!=nil||!os.SameFile(actual,expected){
        return errors.New("TX779_GAME_PORTABLE_RUNTIME_MISMATCH")
    }
    owner,err:=tx771OwnerFile(filepath.Join(root,tx771OnefileSidecar,"portable-owner-v1.json"))
    if err!=nil{return fmt.Errorf("TX779_OWNER_MARKER_INVALID: %w",err)}
    engine:=filepath.Join(selectedLocal,"TENSHIXGAME-RPG","engine")
    worker:=filepath.Join(engine,"engine","TenshixgameAI.exe")
    sha,err:=shaFile(worker)
    if err!=nil||!strings.EqualFold(sha,owner.WorkerSHA256){
        return errors.New("TX779_ORIGINAL_V95_OWNER_WORKER_MISMATCH")
    }
    if _,err=cleanhost.VerifyInstalledIntegrity(engine);err!=nil{
        return fmt.Errorf("TX779_ORIGINAL_V95_ENGINE_INVALID: %w",err)
    }
    if err=cleanhost.VerifyRPGOriginalModelIntegrityForSelectedGame(engine,root);err!=nil{
        return fmt.Errorf("TX779_ORIGINAL_NEURAL_WEIGHTS_INVALID: %w",err)
    }
    game,err:=cleanhost.InspectGameEngine(gameEXE)
    if err!=nil||game.Engine!="mv" {
        return errors.New("TX779_RPG_MAKER_MV_SIGNATURE_REQUIRED")
    }
    gameInfo,err:=os.Stat(game.GameRoot)
    rootInfo,rootErr:=os.Stat(root)
    if err!=nil||rootErr!=nil||!os.SameFile(gameInfo,rootInfo){
        return errors.New("TX779_GAME_ENGINE_ROOT_MISMATCH")
    }
    // Honor previous JA/EN installations only through the original
    // journal-verified rollback. Never remove unknown plugins or their files.
    for _,language:=range []string{"en","ja"} {
        workspace,wsErr:=servidorMVWorkspace(root,selectedLocal,language)
        if wsErr!=nil{return wsErr}
        if _,restoreErr:=cleanhost.RestoreRPGLivePlugin(gameEXE,workspace);restoreErr!=nil{
            return fmt.Errorf("TX779_PREVIOUS_LANGUAGE_RESTORE_REFUSED: %w",restoreErr)
        }
    }
    workspace,err:=servidorMVWorkspace(root,selectedLocal,"auto")
    if err!=nil{return err}
    receipt,err:=cleanhost.InstallRPGLivePlugin(gameEXE,workspace,"auto")
    if err!=nil{return fmt.Errorf("TX779_NATIVE_MV_PLUGIN_INSTALL_FAILED: %w",err)}
    if (receipt.Status!="INSTALLED" && receipt.Status!="ALREADY_INSTALLED_VERIFIED" &&
        receipt.Status!="UPGRADED_VERIFIED") || !receipt.LiveOverlay || !receipt.AheadSceneScan{
        return errors.New("TX779_NATIVE_PLUGIN_INSTALLATION_NOT_VERIFIED")
    }
    // The installer must prove what is actually on disk. A successful
    // InstallRPGLivePlugin receipt does not guarantee that the running game
    // will show this application's identity rather than a stale adapter.
    if err:=servidorVerifyInstalledF10Badge(root,receipt.PluginSHA);err!=nil{
        return fmt.Errorf("IA_TRADUCTORA_COMPLEMENTO_ANTIGUO_O_NO_VERIFICADO: %w",err)
    }
    return nil
}
