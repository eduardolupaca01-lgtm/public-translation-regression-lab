//go:build windows

package main

import (
 "errors"
 "os"
 "path/filepath"
 "strings"
 "testing"
)

func TestR44WebPanelSelectionAndNavigationAreIndependent(t *testing.T){
 ui:=&iaUI{gameFile:"RPG.exe",logText:"RPG diagnostic",jsonPilot:true,jsonRecovery:true,jsonSummary:"RPG summary",cloneAllowed:true}
 old:=iaSelectWebFile;defer func(){iaSelectWebFile=old}()
 exe:=filepath.Join(t.TempDir(),"Game.exe")
 if e:=os.WriteFile(exe,[]byte("fixture"),0600);e!=nil{t.Fatal(e)}
 iaSwitchSection(ui,true)
 if !ui.webActive||iaWebActionAllowed(ui)||iaRPGActionAllowed(ui,iaCmdRecover){t.Fatal("incorrect initial WEB actions")}
 iaSelectWebFile=func(uintptr)(string,error){return exe,nil};iaWebSelect(ui)
 if ui.webFile!=exe||!iaWebActionAllowed(ui){t.Fatal("valid source did not arm WEB")}
 iaSelectWebFile=func(uintptr)(string,error){return "",nil};iaWebSelect(ui)
 if ui.webFile!=exe{t.Fatal("cancel lost selection")}
 iaSelectWebFile=func(uintptr)(string,error){return "invalid.txt",nil};iaWebSelect(ui)
 if ui.webFile!=""||iaWebActionAllowed(ui){t.Fatal("invalid new selection left previous source armed")}
 if ui.logText!="RPG diagnostic"||ui.gameFile!="RPG.exe"||!ui.jsonRecovery||!ui.cloneAllowed||ui.jsonSummary!="RPG summary"{t.Fatal("WEB changed RPG state")}
 ui.busy=true;iaSwitchSection(ui,false)
 if !ui.webActive{t.Fatal("navigation changed while installing")}
 ui.busy=false;iaSwitchSection(ui,false)
 if ui.webActive||!iaRPGActionAllowed(ui,iaCmdRecover)||iaWebActionAllowed(ui){t.Fatal("RPG actions not restored")}
}

func TestR44WebPanelProgressAndErrorsStayInWeb(t *testing.T){
 ui:=&iaUI{webActive:true,busy:true,gameFile:"RPG.exe",webFile:"WEB.exe",logText:"RPG diagnostic",webLogText:"WEB diagnostic"}
 ui.webPending=[]string{"[IA_WEB_EXE_ANALISIS] Analizando","[IA_WEB_PREPARANDO_OPUS] Instalando"}
 ui.webResult="IA_WEB_EXE_RECURSO_SHA_INVALIDO: C:\\private\\game"
 iaWebFinish(ui)
 if ui.busy||!iaWebActionAllowed(ui)||ui.webOutput!=""{t.Fatal("error left invalid installation state")}
 if !strings.Contains(ui.webLogText,"IA_WEB_EXE_ANALISIS")||!strings.Contains(ui.webLogText,"IA_WEB_PREPARANDO_OPUS")||!strings.Contains(ui.webLogText,"IA_WEB_EXE_RECURSO_SHA_INVALIDO")||strings.Contains(ui.webLogText,"private"){t.Fatal("missing or unsafe WEB diagnosis")}
 if ui.logText!="RPG diagnostic"||ui.gameFile!="RPG.exe"{t.Fatal("WEB result changed RPG")}
 old:=iaWebOpenResult;defer func(){iaWebOpenResult=old}()
 opened:="";iaWebOpenResult=func(_ uintptr,path string){opened=path}
 ui.busy=true;ui.webResult="IA_WEB_COPIA_LISTA";ui.webResultGame="copy/Jugar-IA.exe"
 iaWebFinish(ui)
 if ui.busy||opened!=ui.webOutput||opened==""||ui.webFile!="WEB.exe"||ui.gameFile!="RPG.exe"{t.Fatal("completion lost a selection or failed to publish result")}
}

func TestR44WebNativeCommandRoutingAndClipboard(t *testing.T){
 ui:=&iaCurrentUI
 oldActive,oldBusy,oldFile,oldRPG,oldWeb,oldButton,oldCopyBtn:=ui.webActive,ui.busy,ui.webFile,ui.logText,ui.webLogText,ui.webInstall,ui.copyBtn
 oldAction,oldCopy:=iaWebInstallAction,iaCopyDiagnostics
 defer func(){
  ui.webActive=oldActive;ui.busy=oldBusy;ui.webFile=oldFile;ui.logText=oldRPG;ui.webLogText=oldWeb;ui.webInstall=oldButton;ui.copyBtn=oldCopyBtn
  iaWebInstallAction=oldAction;iaCopyDiagnostics=oldCopy
 }()
 ui.webActive=true;ui.busy=false;ui.webFile="WEB.exe";ui.webInstall=812;ui.copyBtn=813
 ui.logText="RPG";ui.webLogText="WEB"
 calls:=0;iaWebInstallAction=func(){calls++}
 iaWinProc(0,iaWMCommand,iaCmdWebInstall,812)
 iaWinProc(0,iaWMCommand,iaCmdWebInstall,999)
 ui.busy=true;iaWinProc(0,iaWMCommand,iaCmdWebInstall,812)
 ui.busy=false;ui.webActive=false;iaWinProc(0,iaWMCommand,iaCmdWebInstall,812)
 if calls!=1{t.Fatalf("wrong WEB dispatch count: %d",calls)}
 copied:=[]string{};iaCopyDiagnostics=func(_ uintptr,s string)error{copied=append(copied,s);if s==""{return errors.New("empty")};return nil}
 ui.webActive=true;iaWinProc(0,iaWMCommand,iaCmdCopy,813)
 ui.webActive=false;iaWinProc(0,iaWMCommand,iaCmdCopy,813)
 if len(copied)!=2||copied[0]!="WEB"||copied[1]!="RPG"{t.Fatalf("mixed clipboard diagnostics: %v",copied)}
}
