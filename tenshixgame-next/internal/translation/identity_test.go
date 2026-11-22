package translation

import "testing"

func TestOriginalV95BridgeKeyInteroperability(t *testing.T){
    examples:=[]struct{language,raw,want string}{
        {"ja","おはよう、夏実。","f9e07c98230035eacbbe6ba4c6bbf54d1e89eb91577e202764082e951b5ecca1"},
        {"en","New Game","a822353538abf900673eef555126fb5c49f5d63e3f18c7f4d77ced77bfd2c794"},
        {"ja","\\C[6]おはよう、夏実。\\C[0]","96e6355d7955ad608155d5d8075e1a56c1f5edce6678cf6e8e156d75b4f5a5b3"},
    }
    for _,x:=range examples{
        key,err:=Key(Source{Family:"rpg-maker",Engine:"mv",Language:x.language,Raw:x.raw})
        if err!=nil||key!=x.want{t.Fatalf("native plugin key mismatch: %q got %s want %s (%v)",x.raw,key,x.want,err)}
    }
}

func TestCopyingGameDoesNotBreakCacheKey(t *testing.T){
    src:=Source{"rpg-maker","mv","ja","\\C[6]おはよう、夏実。\\C[0]"}
    a,err:=Key(src);if err!=nil{t.Fatal(err)}
    b,err:=Key(src);if err!=nil||a!=b{t.Fatal("replay differs")}
    if ok,err:=Match(src,src);err!=nil||!ok{t.Fatal("exact renderer lookup failed")}
}

func TestNativeAndScopedKeysHaveDifferentPurposes(t *testing.T){
    a:=Source{"rpg-maker","mv","ja","今日"}
    b:=a;b.Language="en"
    c:=a;c.Engine="mz"
    x,_:=Key(a);y,_:=Key(b);z,_:=Key(c)
    if x==y {t.Fatal("resolved language must change the original plugin key")}
    if x!=z {t.Fatal("native key must NOT include engine and break compatibility")}
    i,_:=ScopedKey(a);j,_:=ScopedKey(c)
    if i==j||i==x{t.Fatal("separate diagnostic scope must not masquerade as native key")}
    ok,err:=Match(a,c)
    if err!=nil||ok{t.Fatal("cross-engine render must be rejected")}
}
func TestPreserveControlCodesAndWhitespace(t *testing.T){
    base:=Source{"rpg-maker","mv","ja","\\V[1]話"}
    a,_:=Key(base)
    for _,v:=range []string{"\\V[2]話","\\V[1] 話","\\V[1]話\n","\\C[1]話","\\V[1]話!"}{
        changed:=base;changed.Raw=v
        b,err:=Key(changed)
        if err!=nil||b==a{t.Fatalf("source collision %q",v)}
    }
}
func TestAutoLanguageMustBeResolvedBeforeCache(t *testing.T){
    if ResolveAutoLanguage("今日は楽しい")!="ja"||ResolveAutoLanguage("New Game")!="en"{
        t.Fatal("auto language logic drifted from original plugin")
    }
    _,err:=Key(Source{"rpg-maker","mv","auto","今日は"})
    if err==nil{t.Fatal("unresolved auto should not create unreachable cache")}
}
func TestInvalidSourcesAreRejected(t *testing.T){
    for _,s:=range []Source{
        {},{Family:"rpg-maker",Engine:"mv",Language:"ja"},
        {Family:"rpg-maker",Engine:"mv",Language:"ja",Raw:"a\x00b"},
        {Family:"rpg-maker",Engine:"mv",Language:"ja",Raw:string([]byte{0xff})},
        {Family:"rpg-maker",Engine:"mv",Language:"fr",Raw:"Hola"},
    }{
        if _,err:=Key(s);err==nil{t.Fatalf("invalid source accepted: %+v",s)}
    }
}
