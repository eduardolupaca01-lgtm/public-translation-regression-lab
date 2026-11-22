package translation

import "testing"

func TestARepeatedJapaneseDialogueHasTheSameKeyAcrossGameMoves(t *testing.T){
    // Game path is intentionally not a parameter, eliminating the previous
    // cache-key break when C:/Game was copied to D:/Game.
    source:=Source{Family:"rpg-maker",Engine:"mv",Language:"ja",Raw:"\\C[6]おはよう、夏実。\\C[0]"}
    a,err:=Key(source);if err!=nil{t.Fatal(err)}
    b,err:=Key(source);if err!=nil{t.Fatal(err)}
    if len(a)!=64||a!=b{t.Fatal("cache identity changed after a replay")}
    ok,err:=Match(source,source);if err!=nil||!ok{t.Fatal("scan/painter shared input no longer matches")}
}
func TestControlCodesAndActualTextMustNotBeNormalizedAway(t *testing.T){
    base:=Source{Family:"rpg-maker",Engine:"mv",Language:"ja",Raw:"\\V[1]話"}
    a,_:=Key(base)
    for _,v:=range []string{"\\V[2]話","\\V[1] 話","\\V[1]話\n","\\C[1]話","\\V[1]話!"}{
        changed:=base
        changed.Raw=v
        b,err:=Key(changed)
        if err!=nil||b==a{t.Fatalf("dangerous collision: %q",v)}
    }
}
func TestCrossGameAndLanguageKeysRemainIsolated(t *testing.T){
    a:=Source{"rpg-maker","mv","ja","今日"}
    b:=a;b.Language="en"
    c:=a;c.Engine="mz"
    x,_:=Key(a);y,_:=Key(b);z,_:=Key(c)
    if x==y||x==z||y==z{t.Fatal("independent cache domains collided")}
}
func TestInvalidInputsAreRefused(t *testing.T){
    for _,s:=range []Source{
        {},{Family:"rpg-maker",Engine:"mv",Language:"ja"},
        {Family:"rpg-maker",Engine:"mv",Language:"ja",Raw:"x\x00y"},
        {Family:"rpg-maker",Engine:"mv",Language:"ja",Raw:string([]byte{0xff})},
    } {
        if _,err:=Key(s);err==nil{t.Fatalf("invalid source accepted: %+v",s)}
    }
}
