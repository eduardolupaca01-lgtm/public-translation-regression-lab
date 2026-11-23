//go:build windows

package main

import (
    "runtime"
    "syscall"
    "testing"
    "unsafe"
)

func TestEXEFilterNeverPanicsAndEndsWithDoubleNUL(t *testing.T){
    v:=iaExeFilterUTF16()
    if len(v)<10||v[len(v)-1]!=0||v[len(v)-2]!=0{
        t.Fatalf("OPENFILENAMEW filter must end with 2 NUL bytes: %v",v)
    }
    zeroes:=0
    for _,x:=range v{if x==0{zeroes++}}
    if zeroes!=3{t.Fatalf("expected label, pattern and final NUL, got %d",zeroes)}
    s1:=syscall.UTF16ToString(v)
    if s1!="Juegos Windows (*.exe)"{t.Fatalf("unexpected label: %q",s1)}
    part:=syscall.StringToUTF16("Juegos Windows (*.exe)")
    s2:=syscall.UTF16ToString(v[len(part):])
    if s2!="*.exe"{t.Fatalf("unexpected pattern: %q",s2)}
    runtime.KeepAlive(v)
}
func TestEXEFileDialogStructHasValidFields(t *testing.T){
    // The native struct alignment is essential on 64-bit Windows.
    if unsafe.Sizeof(iaFileDialog{})<80||unsafe.Sizeof(iaFileDialog{})>200{
        t.Fatal("OPENFILENAMEW struct layout suspicious")
    }
    if unsafe.Offsetof(iaFileDialog{}.File)<=unsafe.Offsetof(iaFileDialog{}.Filter){
        t.Fatal("lpstrFile layout must follow lpstrFilter")
    }
}
func TestWinProcSelectorCancelKeepsWindowAlive(t *testing.T){
    // In ordinary CI, a real file-picker is not safe to open unattended.
    // The integration test exercises callback dispatch with an injectable
    // dialog result and ensures normal Cancel never destroys the window.
    previous:=iaSelectFile
    iaSelectFile=func(_ uintptr)(string,error){return "",nil}
    defer func(){iaSelectFile=previous}()
    previousUI:=iaCurrentUI
    iaCurrentUI=iaUI{hwnd:0,browse:42,gameFile:"C:\\Games\\Game.exe"}
    defer func(){iaCurrentUI=previousUI}()
    iaWinProc(0,iaWMCommand,iaCmdBrowse,42)
    if iaCurrentUI.gameFile!="C:\\Games\\Game.exe"{
        t.Fatal("cancelling picker must keep previously selected executable")
    }
}
