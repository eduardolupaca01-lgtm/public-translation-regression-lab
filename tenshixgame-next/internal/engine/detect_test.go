package engine

import (
    "os"
    "path/filepath"
    "runtime"
    "strings"
    "testing"
)

func fixture(t *testing.T)string {
    t.Helper()
    root:=t.TempDir()
    put(t,root,"Game.exe",[]byte("MZ FICTIONAL, NOT EXECUTABLE"))
    return root
}
func put(t *testing.T,root,relative string, data []byte){
    t.Helper()
    target:=filepath.Join(root,filepath.FromSlash(relative))
    if err:=os.MkdirAll(filepath.Dir(target),0750);err!=nil{t.Fatal(err)}
    if err:=os.WriteFile(target,data,0600);err!=nil{t.Fatal(err)}
}
func runCheck(t *testing.T,root,family,expected,status string)Result{
    t.Helper()
    r,err:=Inspect(filepath.Join(root,"Game.exe"),family)
    if err!=nil{t.Fatal(err)}
    if r.DetectedEngine!=expected||r.Status!=status {
        t.Fatalf("wanted %q %q, received %q %q %+v",expected,status,r.DetectedEngine,r.Status,r)
    }
    if r.CanInstall{t.Fatal("unapproved adapter was allowed to install")}
    return r
}
func Test17NavigationGroupsAreNotClaimsOfTranslationCompatibility(t *testing.T) {
    if len(Families)!=17{t.Fatalf("navigation families=%d",len(Families))}
    ids:=map[string]bool{}
    for _,f:=range Families{
        if ids[f.ID]||f.TranslationCertified{t.Fatalf("invalid or false-certified family %+v",f)}
        ids[f.ID]=true
    }
    f,ok:=Find("rpg-maker")
    if !ok||len(f.Variants)<7{t.Fatal("RPG Maker generations must not collapse into MV/MZ")}
}
func TestRPGMakerMVInsideWWWWithVersion(t *testing.T){
    root:=fixture(t)
    put(t,root,"www/js/plugins.js",[]byte("var $plugins = [];"))
    put(t,root,"www/data/System.json",[]byte("{}"))
    put(t,root,"www/js/rpg_managers.js",[]byte("/* fixture */"))
    put(t,root,"www/js/rpg_core.js",[]byte("Utils.RPGMAKER_VERSION = '1.6.3';"))
    r:=runCheck(t,root,"rpg-maker","RPG Maker MV","identified")
    if r.EngineVersion!="1.6.3"{t.Fatal(r.EngineVersion)}
}
func TestRPGMakerMZStandaloneAndNeverConfusedWithMV(t *testing.T){
    root:=fixture(t)
    put(t,root,"js/plugins.js",[]byte("var $plugins = [];"))
    put(t,root,"data/System.json",[]byte("{}"))
    put(t,root,"js/rmmz_managers.js",[]byte("// synthetic"))
    put(t,root,"js/rmmz_core.js",[]byte("Utils.RPGMAKER_VERSION = \"1.8.1\";"))
    r:=runCheck(t,root,"rpg-maker","RPG Maker MZ","identified")
    if r.EngineVersion!="1.8.1"{t.Fatal(r.EngineVersion)}
}
func TestConflictBothMVAndMZIsNotSilentlyInstalled(t *testing.T){
    root:=fixture(t)
    for _,f:=range []string{"js/plugins.js","data/System.json","js/rpg_core.js","js/rpg_managers.js","js/rmmz_core.js","js/rmmz_managers.js"} {
        put(t,root,f,[]byte("{}"))
    }
    r:=runCheck(t,root,"rpg-maker","","conflict")
    if len(r.Evidence)!=2{t.Fatal(r.Evidence)}
}
func TestRPG2000Or2003NeedsSubversionProof(t *testing.T){
    root:=fixture(t)
    put(t,root,"RPG_RT.ldb",[]byte("LDB"))
    put(t,root,"RPG_RT.lmt",[]byte("LMT"))
    r:=runCheck(t,root,"rpg-maker","RPG Maker 2000/2003","ambiguous")
    if !strings.Contains(r.EngineVersion,"no distinguible"){t.Fatal(r.EngineVersion)}
}
func TestRGSSSeparateXPVXAndVXAce(t *testing.T){
    cases:=[]struct{marker,resources,expected string}{
        {"RGSS104E.dll","Data/Actors.rxdata","RPG Maker XP"},
        {"RGSS202J.dll","Data/Actors.rvdata","RPG Maker VX"},
        {"RGSS301.dll","Data/Actors.rvdata2","RPG Maker VX Ace"},
    }
    for _,c:=range cases{
        t.Run(c.expected,func(t *testing.T){
            root:=fixture(t)
            put(t,root,"Game.ini",[]byte("[Game]\nLibrary="+c.marker+"\n"))
            put(t,root,c.resources,[]byte("SYNTHETIC"))
            runCheck(t,root,"rpg-maker",c.expected,"identified")
        })
    }
}
func TestUnityAndRPGAreNotExchangeable(t *testing.T){
    root:=fixture(t)
    put(t,root,"UnityPlayer.dll",[]byte("fixture"))
    put(t,root,"Game_Data/globalgamemanagers",[]byte("fixture"))
    runCheck(t,root,"unity","Unity","identified")
    runCheck(t,root,"rpg-maker","","unknown")
}
func TestRenpyDistributionVersionHintNotCertification(t *testing.T){
    root:=fixture(t)
    if err:=os.MkdirAll(filepath.Join(root,"renpy"),0700);err!=nil{t.Fatal(err)}
    if err:=os.MkdirAll(filepath.Join(root,"game"),0700);err!=nil{t.Fatal(err)}
    put(t,root,"renpy/version.py",[]byte("version_tuple = (8, 3, 7)"))
    r:=runCheck(t,root,"renpy","Ren'Py","identified")
    if r.EngineVersion!="8.3.7"{t.Fatal(r.EngineVersion)}
}
func TestGodotOwnPCKNotArbitraryNeighbor(t *testing.T){
    root:=fixture(t)
    put(t,root,"OtherGame.pck",[]byte("fake"))
    runCheck(t,root,"godot","","unknown")
    put(t,root,"Game.pck",[]byte("fake"))
    runCheck(t,root,"godot","Godot","identified")
}
func TestGameMakerRequiresFORMGEN8STRG(t *testing.T){
    root:=fixture(t)
    put(t,root,"data.win",[]byte("FORM0000GEN8aSTRGb"))
    runCheck(t,root,"gamemaker","GameMaker","identified")
    put(t,root,"data.win",[]byte("notFORM"))
    runCheck(t,root,"gamemaker","GameMaker (candidato)","ambiguous")
}
func TestUnknownProbeNeverWritesToPlayerGame(t *testing.T){
    root:=fixture(t)
    original,err:=os.ReadFile(filepath.Join(root,"Game.exe"))
    if err!=nil{t.Fatal(err)}
    r:=runCheck(t,root,"rpg-maker","","unknown")
    if !strings.Contains(r.Explanation,"No se verificó"){t.Fatal(r.Explanation)}
    actual,err:=os.ReadFile(filepath.Join(root,"Game.exe"))
    if err!=nil||string(actual)!=string(original){t.Fatal("game exe mutated")}
    if _,err:=os.Stat(filepath.Join(root,"Tenshixgame-IA"));!os.IsNotExist(err){
        t.Fatal("inspector created a game-local engine without authorization")
    }
}
func TestNonexistentOrUnrelatedFamilyIsRejected(t *testing.T){
    _,err:=Inspect("Game.exe","not-a-family")
    if err==nil{t.Fatal("unknown family accepted")}
    _,err=Inspect(filepath.Join(t.TempDir(),"none.exe"),"rpg-maker")
    if err==nil{t.Fatal("missing exe accepted")}
}
func TestSymlinkedGameMarkerAndRootRefused(t *testing.T){
    root:=fixture(t)
    outside:=filepath.Join(t.TempDir(),"System.json")
    if err:=os.WriteFile(outside,[]byte("{}"),0600);err!=nil{t.Fatal(err)}
    put(t,root,"www/js/rpg_core.js",[]byte("Utils.RPGMAKER_VERSION='1.6.2'"))
    put(t,root,"www/js/rpg_managers.js",[]byte("ok"))
    put(t,root,"www/js/plugins.js",[]byte("{}"))
    symlink:=filepath.Join(root,"www/data/System.json")
    if err:=os.MkdirAll(filepath.Dir(symlink),0700);err!=nil{t.Fatal(err)}
    if err:=os.Symlink(outside,symlink);err!=nil{
        if runtime.GOOS=="windows"{t.Skip("Windows cannot create symlink without permission")}
        t.Fatal(err)
    }
    runCheck(t,root,"rpg-maker","","unknown")
    alias:=filepath.Join(t.TempDir(),"alias")
    if err:=os.Symlink(root,alias);err==nil {
        if _,err=Inspect(alias,"rpg-maker");err==nil{t.Fatal("linked game root accepted")}
    }
}
