package main

import (
 "bytes"
 "os"
 "path/filepath"
 "testing"
)

func TestScreenSidecarOutsideGameStableAcrossLaunchersAndVersions(t *testing.T){
 root:=t.TempDir();cache:=t.TempDir()
 for rel,data:=range map[string][]byte{"Game.exe":[]byte("fixture"),"Dragonhouse.GameBootstrapper.exe":[]byte("fixture"),"GameConfig.sbcf":[]byte("fixture"),"GamePackages/Data.halva":[]byte("fixture")}{
  cookFixtureFile(t,root,rel,data)
 }
 p,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer p.Close()
 profile,worker,e:=prepareScreen(filepath.Join(root,"Game.exe"),cache,p);if e!=nil{t.Fatal(e)}
 again,w2,e:=prepareScreen(filepath.Join(root,"Dragonhouse.GameBootstrapper.exe"),cache,p)
 if e!=nil||again!=profile||worker!=w2||!ordinary(worker){t.Fatalf("screen profile not reusable: %v",e)}
 p2,e:=readPackage(fakePackageWith(t,[]byte("◆ IA Traductora · F10 new"),[]byte("different worker")));if e!=nil{t.Fatal(e)};defer p2.Close()
 profile2,w3,e:=prepareScreen(filepath.Join(root,"Game.exe"),cache,p2)
 if e!=nil||profile2!=profile||w3==worker||!ordinary(worker)||!ordinary(w3){t.Fatalf("versioned worker broken: %v",e)}
 got,e:=os.ReadFile(filepath.Join(root,"GamePackages","Data.halva"));if e!=nil||!bytes.Equal(got,[]byte("fixture")){t.Fatal("original changed")}
 if _,e=os.Stat(filepath.Join(root,brandFolder));!os.IsNotExist(e){t.Fatal("wrote into game")}
 normal:=createFixture(t)
 if _,_,e=prepareScreen(filepath.Join(normal,"Game.exe"),cache,p);e==nil{t.Fatal("normal native game unexpectedly routed to OCR")}
}
