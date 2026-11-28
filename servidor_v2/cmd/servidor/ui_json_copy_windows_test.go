//go:build windows

package main
import "testing"

func TestR44RPGCopyActionsAreSeparate(t *testing.T){
 cases:=[]struct{name string;selected,json,pending,clone,busy bool;want [4]bool}{
  {"none",false,false,false,false,false,[4]bool{}},
  {"ordinary",true,false,false,false,false,[4]bool{true,true,false,false}},
  {"packed_vxace",true,false,false,true,false,[4]bool{true,true,true,false}},
  {"offline_json_clean",true,true,false,false,false,[4]bool{true,false,false,true}},
  {"offline_json_pending",true,true,true,false,false,[4]bool{false,true,false,false}},
  {"offline_stale_clone_flag",true,true,false,true,false,[4]bool{true,false,false,true}},
  {"busy",true,true,true,false,true,[4]bool{}},
  {"busy_vxace",true,false,false,true,true,[4]bool{}},
 }
 for _,c:=range cases{t.Run(c.name,func(t *testing.T){
  ui:=iaUI{jsonPilot:c.json,jsonRecovery:c.pending,cloneAllowed:c.clone,busy:c.busy}
  if c.selected{ui.gameFile="synthetic Game.exe"}
  for i,cmd:=range []int{iaCmdInstall,iaCmdRecover,iaCmdClone,iaCmdJSONCopy}{
   if got:=iaRPGActionAllowed(&ui,cmd);got!=c.want[i]{t.Fatalf("action %d got %t want %t",cmd,got,c.want[i])}
  }
 })}
 if iaCmdJSONCopy==iaCmdClone||iaCmdJSONCopy==iaCmdInstall{t.Fatal("copy commands collide")}
}
func TestR44JSONPendingSelectionCannotOverwrite(t *testing.T){
 ui:=&iaCurrentUI
 oldGame,oldPilot,oldPending,oldClone,oldBusy:=ui.gameFile,ui.jsonPilot,ui.jsonRecovery,ui.cloneAllowed,ui.busy
 defer func(){ui.gameFile=oldGame;ui.jsonPilot=oldPilot;ui.jsonRecovery=oldPending;ui.cloneAllowed=oldClone;ui.busy=oldBusy}()
 ui.gameFile="synthetic Game.exe";ui.jsonPilot=true;ui.jsonRecovery=true;ui.cloneAllowed=true;ui.busy=false
 iaStartInstall()
 iaStartClone()
 iaStartJSONPilot(false)
 if ui.busy{t.Fatal("pending JSON operation dispatched an overwrite")}
}
