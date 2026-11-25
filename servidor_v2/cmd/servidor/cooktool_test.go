package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func cookFixtureFile(t *testing.T, root, rel string, data []byte){
	t.Helper()
	f:=filepath.Join(root,filepath.FromSlash(rel))
	if err:=os.MkdirAll(filepath.Dir(f),0700);err!=nil{t.Fatal(err)}
	if err:=os.WriteFile(f,data,0600);err!=nil{t.Fatal(err)}
}

func TestCookToolBothExecutablesRecognizedWithoutWrites(t *testing.T){
	root:=t.TempDir()
	original:=map[string][]byte{
		"Game.exe":[]byte("synthetic"),
		"Dragonhouse.GameBootstrapper.exe":[]byte("synthetic"),
		"GameConfig.sbcf":[]byte("synthetic config"),
		"GamePackages/Common/DatabasePackage.halva":[]byte("synthetic, not a real archive"),
		"GamePackages/win-x64/EnginePackage.halva2":[]byte("synthetic, not a real archive"),
		"Binaries/runtime.bin":[]byte("synthetic"),
	}
	for rel,data:=range original{cookFixtureFile(t,root,rel,data)}
	pkg,err:=readPackage(fakePackage(t));if err!=nil{t.Fatal(err)};defer pkg.Close()
	for _,name:=range []string{"Game.exe","Dragonhouse.GameBootstrapper.exe"}{
		exe:=filepath.Join(root,name)
		r,c,e:=detectGame(exe)
		if e==nil||r!=""||c!=""||!strings.HasPrefix(e.Error(),cookToolPackedCode+":")||
			!strings.Contains(e.Error(),"halva=1 halva2=1"){t.Fatalf("wrong diagnosis for %s: %v",name,e)}
		if e=Install(exe,pkg);e==nil||!strings.HasPrefix(e.Error(),cookToolPackedCode){t.Fatalf("packed install not stopped: %v",e)}
	}
	for rel,want:=range original{
		got,err:=os.ReadFile(filepath.Join(root,filepath.FromSlash(rel)))
		if err!=nil||!bytes.Equal(want,got){t.Fatalf("original modified: %s",rel)}
	}
	if _,err:=os.Lstat(filepath.Join(root,brandFolder));!os.IsNotExist(err){t.Fatal("unexpected translator folder")}
}

func TestCookToolMixedRootAndLooseExport(t *testing.T){
	root:=createFixture(t)
	exe:=filepath.Join(root,"Game.exe")
	// A custom assets folder alone must not block a normal RPG export.
	cookFixtureFile(t,root,"GamePackages/other.bin",[]byte("fixture"))
	if _,_,e:=detectGame(exe);e!=nil{t.Fatalf("ordinary RPG changed: %v",e)}
	registry:=filepath.Join(root,"www","js","plugins.js")
	before,err:=os.ReadFile(registry);if err!=nil{t.Fatal(err)}
	// A packed layout with loose core markers is ambiguous, and could be a
	// cache. Never edit it as though it were a normal exported project.
	cookFixtureFile(t,root,"GameConfig.sbcf",[]byte("fixture"))
	pkg,err:=readPackage(fakePackage(t));if err!=nil{t.Fatal(err)};defer pkg.Close()
	if e:=Install(exe,pkg);e==nil||!strings.HasPrefix(e.Error(),cookToolPackedCode){t.Fatalf("mixed layout install not blocked: %v",e)}
	after,err:=os.ReadFile(registry);if err!=nil||!bytes.Equal(before,after){t.Fatal("mixed registry modified")}
}

func TestCookToolRejectsWrongMarkerTypes(t *testing.T){
	root:=t.TempDir()
	cookFixtureFile(t,root,"Game.exe",[]byte("fixture"))
	cookFixtureFile(t,root,"GameConfig.sbcf",[]byte("fixture"))
	cookFixtureFile(t,root,"GamePackages",[]byte("must be a folder"))
	_,_,e:=detectGame(filepath.Join(root,"Game.exe"))
	if e==nil||e.Error()!=cookToolUnsafeCode{t.Fatalf("unsafe layout: %v",e)}
}

func TestCookToolInventoryBudget(t *testing.T){
	root:=t.TempDir()
	for _,rel:=range []string{"A.halva","B.halva2","C.txt"}{cookFixtureFile(t,root,rel,[]byte("fixture"))}
	budget:=2;got:=cookToolInventory{}
	cookToolScan(root,0,&budget,&got)
	if budget!=0||!got.partial||got.halva+got.halva2+got.other!=2{t.Fatalf("inventory exceeded bound: %+v",got)}
}

func TestInstallerBuildMatchesSharedPlugin(t *testing.T){
	raw,err:=os.ReadFile(filepath.Join("..","..","plugin","IATraductora.js"))
	if err!=nil{t.Fatal(err)}
	if !bytes.Contains(raw,[]byte("var BUILD_ID=\""+installerBuildID+"\";")){t.Fatal("installer and plugin build IDs disagree")}
}
