//go:build windows

package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestCookToolSelectionClearsPreviouslySelectedGame(t *testing.T){
	root:=t.TempDir()
	cookFixtureFile(t,root,"Game.exe",[]byte("fixture"))
	cookFixtureFile(t,root,"GameConfig.sbcf",[]byte("fixture"))
	cookFixtureFile(t,root,"GamePackages/Common/Data.halva",[]byte("fixture"))
	previous:=iaSelectFile
	oldGame,oldScreen,oldBrowse,oldLogs:=iaCurrentUI.gameFile,iaCurrentUI.screenFile,iaCurrentUI.browse,iaCurrentUI.logText
	defer func(){iaSelectFile=previous;iaCurrentUI.gameFile=oldGame;iaCurrentUI.screenFile=oldScreen;iaCurrentUI.browse=oldBrowse;iaCurrentUI.logText=oldLogs}()
	iaCurrentUI.gameFile="C:\\previous\\Game.exe"
	iaCurrentUI.browse=423
	iaCurrentUI.logText=""
	iaSelectFile=func(_ uintptr)(string,error){return filepath.Join(root,"Game.exe"),nil}
	iaWinProc(0,iaWMCommand,iaCmdBrowse,423)
	if iaCurrentUI.gameFile!=""{t.Fatal("previous game still selected after Halva selection")}
	if iaCurrentUI.screenFile!=filepath.Join(root,"Game.exe"){t.Fatal("visual route not selected")}
	if !strings.Contains(iaCurrentUI.logText,"IA_RPG_HALVA_DETECTADO"){t.Fatal("missing useful diagnosis")}
}
