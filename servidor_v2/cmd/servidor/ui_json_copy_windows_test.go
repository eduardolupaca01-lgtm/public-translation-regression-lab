//go:build windows

package main

import "testing"

func TestR44RPGCopyActionsAreSeparate(t *testing.T){
 cases:=[]struct{name string;selected,json,clone,busy bool;want [4]bool}{
  {"none",false,false,false,false,[4]bool{}},
  {"ordinary",true,false,false,false,[4]bool{true,true,false,false}},
  {"packed_vxace",true,false,true,false,[4]bool{true,true,true,false}},
  {"offline_json",true,true,false,false,[4]bool{false,false,false,true}},
  {"offline_even_with_stale_clone_flag",true,true,true,false,[4]bool{false,false,false,true}},
  {"busy",true,true,false,true,[4]bool{}},
  {"busy_vxace",true,false,true,true,[4]bool{}},
 }
 for _,c:=range cases{t.Run(c.name,func(t *testing.T){
  ui:=iaUI{jsonPilot:c.json,cloneAllowed:c.clone,busy:c.busy}
  if c.selected{ui.gameFile="synthetic Game.exe"}
  for i,cmd:=range []int{iaCmdInstall,iaCmdRecover,iaCmdClone,iaCmdJSONCopy}{
   if got:=iaRPGActionAllowed(&ui,cmd);got!=c.want[i]{t.Fatalf("action %d got %t want %t",cmd,got,c.want[i])}
  }
 })}
 if iaCmdJSONCopy==iaCmdClone||iaCmdJSONCopy==iaCmdInstall{t.Fatal("copy commands collide")}
}

func TestR44JSONSelectionCannotInvokeDirectInstall(t *testing.T){
 ui:=&iaCurrentUI
 oldGame,oldPilot,oldClone,oldBusy:=ui.gameFile,ui.jsonPilot,ui.cloneAllowed,ui.busy
 defer func(){ui.gameFile=oldGame;ui.jsonPilot=oldPilot;ui.cloneAllowed=oldClone;ui.busy=oldBusy}()
 // Call the actual installer entry points with an offline-only selection.
 // They must return before opening a dialog, reading a payload or spawning
 // a goroutine, even if someone sends a manual WM_COMMAND to that button.
 ui.gameFile="synthetic Game.exe";ui.jsonPilot=true;ui.cloneAllowed=true;ui.busy=false
 iaStartInstall()
 iaStartRecover()
 iaStartClone()
 if ui.busy{t.Fatal("offline selection triggered an incompatible operation")}
}
