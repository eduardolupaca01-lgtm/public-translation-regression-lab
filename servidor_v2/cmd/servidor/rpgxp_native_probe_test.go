package main

import (
 "bytes"
 "os"
 "path/filepath"
 "strings"
 "testing"
)

func TestRPGXPNativeProbeBuildsIsolatedFixture(t *testing.T){
 exe:=rpgxpFixture(t)
 root:=filepath.Dir(exe)
 sentinel:=filepath.Join(root,"Save1.rxdata")
 if e:=os.WriteFile(sentinel,[]byte("private sentinel"),0600);e!=nil{t.Fatal(e)}
 original:=filepath.Join(root,"Data","Scripts.rxdata")
 before,e:=os.ReadFile(original);if e!=nil{t.Fatal(e)}
 dir:=t.TempDir()
 originals,e:=xpNativePrepare(exe,dir);if e!=nil{t.Fatal(e)}
 if len(originals)!=4{t.Fatal("wrong set of tracked source files")}
 if _,e=os.Stat(filepath.Join(dir,"Save1.rxdata"));!os.IsNotExist(e){t.Fatal("save copied")}
 after,e:=os.ReadFile(original);if e!=nil||!bytes.Equal(before,after){t.Fatal("source archive modified")}
 b,e:=os.ReadFile(filepath.Join(dir,"Data","Scripts.rxdata"));if e!=nil{t.Fatal(e)}
 rows,e:=xpParseScripts(b);if e!=nil||len(rows)!=2{t.Fatalf("fixture archive %v",e)}
 for i,want:=range [][]byte{xpNativeWindow,xpNativeMain}{
  script,e:=xpInflate(rows[i].packed,xpMaxInflated)
  if e!=nil||!bytes.Equal(script,want){t.Fatal("unexpected script")}
 }
 plugin,e:=os.ReadFile(filepath.Join("..","..","rpgxp","IATraductoraXP.rb"));if e!=nil{t.Fatal(e)}
 patched,e:=xpPatchScripts(b,plugin);if e!=nil{t.Fatal(e)}
 final,e:=xpParseScripts(patched);if e!=nil||len(final)!=3||string(final[1].name)!=xpScriptName{t.Fatal("owned adapter not placed before Main")}
 if _,_,e=xpTarget(filepath.Join(dir,"Game.exe"));e!=nil{t.Fatal(e)}
 if _,e=xpNativePrepare(exe,dir);e==nil{t.Fatal("nonempty probe accepted")}
 child:=filepath.Join(root,"do-not-use")
 if e=os.Mkdir(child,0700);e!=nil{t.Fatal(e)}
 if _,e=xpNativePrepare(exe,child);e==nil{t.Fatal("probe under game accepted")}
 got,e:=os.ReadFile(sentinel);if e!=nil||string(got)!="private sentinel"{t.Fatal("save changed")}
 if strings.Contains(string(xpNativeMain),"class Win32API"){t.Fatal("mock runtime used")}
}
