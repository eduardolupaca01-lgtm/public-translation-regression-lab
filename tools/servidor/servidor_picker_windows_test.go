//go:build windows

package main

import (
	"errors"
	"os"
	"path/filepath"
	"syscall"
	"testing"
)

func servidorCompletePickerTest(t *testing.T, response servidorFilePickerResponse, initial string)string{
	t.Helper()
	previousScreen:=tx777Screen
	previousBusy:=servidorFilePickerBusy
	previousResults:=servidorFilePickerResults
	previousSummary:=servidorSummary
	st:=&tx777State{game:initial}
	tx777Screen=st
	servidorFilePickerBusy=true
	servidorFilePickerResults=make(chan servidorFilePickerResponse,1)
	servidorFilePickerResults<-response
	servidorSummary=0
	t.Cleanup(func(){
		tx777Screen=previousScreen
		servidorFilePickerBusy=previousBusy
		servidorFilePickerResults=previousResults
		servidorSummary=previousSummary
	})
	servidorPickerComplete()
	if servidorFilePickerBusy{t.Fatal("picker completion left UI blocked")}
	return st.game
}
func TestServidorPickerCancelKeepsWindowAndPreviousSelection(t *testing.T){
	existing:="C:\\PreviousGame\\Game.exe"
	got:=servidorCompletePickerTest(t,servidorFilePickerResponse{chosen:false},existing)
	if got!=existing{t.Fatalf("Cancel erased selection: %q",got)}
}
func TestServidorPickerErrorKeepsWindowAndPreviousSelection(t *testing.T){
	existing:="C:\\PreviousGame\\Game.exe"
	got:=servidorCompletePickerTest(t,servidorFilePickerResponse{
		err:errors.New("SERVIDOR_SELECTOR_WINDOWS_0x3002")},existing)
	if got!=existing{t.Fatalf("picker error erased selection: %q",got)}
}
func TestServidorPickerUnownedWindowNeverOpensDialog(t *testing.T){
	_,ok,err:=servidorPickFileOwned(0)
	if ok||err==nil{t.Fatal("unowned dialog must be rejected")}
}
func TestServidorPickerSelectedMVIsRetained(t *testing.T){
	exe:=servidorFixture(t,"rpg_core.js","rpg_managers.js")
	got:=servidorCompletePickerTest(t,servidorFilePickerResponse{file:exe,chosen:true},"")
	if got!=exe{t.Fatalf("valid MV not retained: %q",got)}
}
func TestServidorPickerMZIsRejectedBeforeInstallation(t *testing.T){
	exe:=servidorFixture(t,"rmmz_core.js","rmmz_managers.js")
	got:=servidorCompletePickerTest(t,servidorFilePickerResponse{file:exe,chosen:true},"")
	if got!=""{t.Fatalf("wrong engine accepted: %q",got)}
}
func TestServidorPickerRejectsOrdinaryNonGameEXE(t *testing.T){
	wrong:=filepath.Join(t.TempDir(),"not-a-game.exe")
	if err:=os.WriteFile(wrong,[]byte("not a game"),0600);err!=nil{t.Fatal(err)}
	got:=servidorCompletePickerTest(t,servidorFilePickerResponse{file:wrong,chosen:true},"")
	if got!=""{t.Fatalf("non-game selected: %q",got)}
}

func TestServidorPickerWindowsFilterMatchesWorkingLegacyDialog(t *testing.T) {
	filter:=servidorEXEFilter()
	want:=[]string{"Juegos Windows (*.exe)","*.exe","Todos los archivos","*.*"}
	position:=0
	for _,part:=range want {
		if position>=len(filter){t.Fatalf("missing filter field: %q",part)}
		got:=syscall.UTF16ToString(filter[position:])
		if got!=part{t.Fatalf("bad Win32 dialog filter: got %q, want %q",got,part)}
		position+=len(syscall.StringToUTF16(part))
	}
	if position!=len(filter)-1 || filter[len(filter)-1]!=0 || filter[len(filter)-2]!=0 {
		t.Fatalf("Win32 filter must end with two NULs, len=%d end=%d",len(filter),position)
	}
}
func TestServidorPickerRegressionEmbeddedNULCannotReachStringToUTF16(t *testing.T) {
	_,bad:=syscall.UTF16FromString("Juegos Windows\x00*.exe\x00")
	if bad==nil{t.Fatal("Go accepted the previously crashing NUL-embedded filter")}
	if len(servidorEXEFilter())==0{t.Fatal("safe filter unexpectedly empty")}
}
