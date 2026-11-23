//go:build windows

package main

import (
    "os"
    "path/filepath"
    "strings"
    "testing"
)

func TestServidorIntegratedMVWorkspaceIsGameLocal(t *testing.T){
    game:=t.TempDir()
    local:=filepath.Join(game,tx771OnefileSidecar,".local")
    workspace,err:=servidorMVWorkspace(game,local,"auto")
    if err!=nil{t.Fatal(err)}
    if !strings.HasPrefix(workspace,local+string(filepath.Separator)) ||
        !strings.Contains(workspace,"game-workspaces"){
        t.Fatalf("workspace not in game-local sidecar: %q",workspace)
    }
    again,err:=servidorMVWorkspace(game,local,"auto")
    if err!=nil||again!=workspace{t.Fatal("workspace identity not stable")}
    en,_:=servidorMVWorkspace(game,local,"en")
    if en==workspace{t.Fatal("language-specific workspace collision")}
}
func TestServidorIntegratedMVRejectsNonMVBeforeWriting(t *testing.T){
    exe:=servidorFixture(t,"rmmz_core.js","rmmz_managers.js")
    local:=filepath.Join(filepath.Dir(exe),"Tenshixgame-IA",".local")
    err:=servidorInstallMV(exe,local)
    if err==nil||!strings.Contains(err.Error(),"TX779_ONLY_MV_SELECTED"){t.Fatalf("unverified game accepted: %v",err)}
    if _,e:=os.Lstat(filepath.Dir(local));!os.IsNotExist(e){
        t.Fatalf("non-MV created sidecar: %v",e)
    }
}
func TestServidorIntegratedMVRejectsMissingPortableRuntimeBeforeWriting(t *testing.T){
    exe:=servidorFixture(t,"rpg_core.js","rpg_managers.js")
    local:=filepath.Join(filepath.Dir(exe),"Tenshixgame-IA",".local")
    err:=servidorInstallMV(exe,local)
    if err==nil||!strings.Contains(err.Error(),"TX779_LOCAL_ENGINE_NOT_FOUND"){t.Fatalf("missing V95 runtime accepted: %v",err)}
}
