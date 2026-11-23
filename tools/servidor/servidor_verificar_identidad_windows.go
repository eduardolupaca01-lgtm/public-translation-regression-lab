//go:build windows

package main

// SERVIDOR TX783: forbid claiming completion when the installed game plugin
// still has the old F10 label. This validates the real installed bytes after
// the original owner-verified installer, not a test template or a journal.
import(
    "crypto/sha256"
    "encoding/hex"
    "errors"
    "os"
    "path/filepath"
    "strings"
)

func servidorValidVisibleIAPlugin(source []byte)bool{
    text:=string(source)
    return strings.Contains(text,"◆ IA Traductora · F10") &&
        strings.Contains(text,"IA Traductora · V95") &&
        !strings.Contains(text,"◆ TENSHIXGAME RPG") &&
        !strings.Contains(text,"TENSHIXGAME RPG · V95")
}
func servidorVerifyInstalledF10Badge(gameRoot,expectedSHA string)error{
    if !filepath.IsAbs(gameRoot)||len(expectedSHA)!=64{
        return errors.New("TX783_BAD_ROOT_OR_EXPECTED_SIGNATURE")
    }
    var jsRoot string
    for _,rel:=range []string{"www",""}{
        candidate:=filepath.Join(gameRoot,rel,"js")
        if st,err:=os.Lstat(filepath.Join(candidate,"plugins.js"));err==nil&&
           st.Mode().IsRegular()&&st.Mode()&os.ModeSymlink==0{
            if jsRoot!=""{return errors.New("TX783_AMBIGUOUS_GAME_JS_LAYOUT")}
            jsRoot=candidate
        }
    }
    if jsRoot==""{return errors.New("TX783_GAME_REGISTRY_MISSING")}
    // Verify the EXACT plugin that the legacy installer currently registered.
    // A later independent installer will replace this compatibility path.
    filename:=filepath.Join(jsRoot,"plugins","TenshixgameRPGLive.js")
    st,err:=os.Lstat(filename)
    if err!=nil||!st.Mode().IsRegular()||st.Mode()&os.ModeSymlink!=0||
       st.Size()<10000||st.Size()>1024*1024{
        return errors.New("TX783_INSTALLED_RPG_PLUGIN_NOT_ORDINARY")
    }
    source,err:=os.ReadFile(filename)
    if err!=nil{return errors.New("TX783_PLUGIN_UNREADABLE")}
    digest:=sha256.Sum256(source)
    if hex.EncodeToString(digest[:])!=expectedSHA{
        return errors.New("TX783_INSTALLED_PLUGIN_SHA_NOT_SIGNED")
    }
    if !servidorValidVisibleIAPlugin(source){
        return errors.New("TX783_STALE_F10_IDENTITY_VISIBLE")
    }
    list,err:=os.ReadFile(filepath.Join(jsRoot,"plugins.js"))
    if err!=nil||len(list)>4*1024*1024{
        return errors.New("TX783_PLUGIN_REGISTRY_UNAVAILABLE")
    }
    if !strings.Contains(string(list),`"name":"TenshixgameRPGLive"`){
        return errors.New("TX783_NATIVE_PLUGIN_NOT_REGISTERED")
    }
    return nil
}
