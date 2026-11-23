//go:build windows

package main

// The Windows file dialog uses its own nested message loop. It must not be
// launched synchronously from the Win32 window callback on Servidor's UI thread.
// An STA thread owns the picker and posts the result back to the UI.
import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"unsafe"
)

const servidorWMFilePickerResult = 0x8000 + 242

type servidorFilePickerResponse struct {
	file string
	chosen bool
	err error
}
var (
	servidorFilePickerResults chan servidorFilePickerResponse
	servidorFilePickerBusy bool
	servidorPickFile = servidorPickFileOwned
)
func servidorPickerStart(hwnd uintptr) {
	if servidorFilePickerBusy || tx777Screen == nil || tx777Screen.running {return}
	servidorFilePickerBusy=true
	servidorFilePickerResults=make(chan servidorFilePickerResponse,1)
	tx777Enable.Call(tx777Screen.browse,0)
	tx777Enable.Call(tx777Screen.install,0)
	servidorSetSummary("Abriendo selector de archivos EXE…")
	resultChannel:=servidorFilePickerResults
	go func(){
		runtime.LockOSThread()
		defer runtime.UnlockOSThread()
		result:=servidorFilePickerResponse{}
		defer func(){
			if recover()!=nil {result=servidorFilePickerResponse{err:errors.New("SERVIDOR_SELECTOR_PANIC_RECOVERED")}}
			resultChannel<-result
			tx777Post.Call(hwnd,servidorWMFilePickerResult,0,0)
		}()
		ole32:=syscall.NewLazyDLL("ole32.dll")
		initResult,_,_:=ole32.NewProc("CoInitializeEx").Call(0,0x2|0x4)
		if initResult==0 || initResult==1 {
			defer ole32.NewProc("CoUninitialize").Call()
		}else if uint32(initResult)!=0x80010106 {
			result.err=fmt.Errorf("SERVIDOR_SELECTOR_COM_INIT_0x%08X",uint32(initResult))
			return
		}
		result.file,result.chosen,result.err=servidorPickFile(hwnd)
	}()
}
func servidorPickerComplete(){
	if !servidorFilePickerBusy || servidorFilePickerResults==nil{return}
	var result servidorFilePickerResponse
	select {
	case result=<-servidorFilePickerResults:
	default:return
	}
	servidorFilePickerBusy=false
	if tx777Screen==nil{return}
	st:=tx777Screen
	if !st.running{
		tx777Enable.Call(st.browse,1)
		tx777Enable.Call(st.install,1)
	}
	if result.err!=nil {
		tx777Add("SERVIDOR_SELECTOR_ERROR",result.err.Error())
		servidorSetSummary("No se pudo completar la selección. Servidor sigue abierto.")
		return
	}
	if !result.chosen {
		servidorSetSummary("Selección cancelada. Puedes volver a pulsar EXE.")
		return
	}
	if _,err:=servidorMVGameRoot(result.file);err!=nil {
		tx777Add("SERVIDOR_EXE_NO_COMPATIBLE",err.Error())
		servidorSetSummary("El EXE no corresponde a una copia válida de RPG.")
		return
	}
	st.game=result.file
	tx777Set(st.selectedField,result.file)
	tx777Add("SERVIDOR_EXE_VERIFICADO","Se verificó la estructura RPG de la copia seleccionada.")
	servidorSetSummary("EXE verificado. Puedes instalar el traductor automático.")
}
// servidorEXEFilter constructs the OPENFILENAMEW filter exactly as the
// working legacy chooseFile/filters implementation does: a sequence of
// separate UTF-16Z strings with one extra NUL at the very end.
// StringToUTF16 on an already NUL-separated string PANICS in Go on Windows.
func servidorEXEFilter() []uint16 {
	result:=make([]uint16,0,72)
	for _,part:=range []string{
		"Juegos Windows (*.exe)", "*.exe",
		"Todos los archivos", "*.*",
	} {
		result=append(result,syscall.StringToUTF16(part)...)
	}
	return append(result,0)
}

func servidorPickFileOwned(owner uintptr)(string,bool,error){
	if owner==0{return "",false,errors.New("SERVIDOR_SELECTOR_NO_OWNER_WINDOW")}
	buffer:=make([]uint16,32768)
	filter:=servidorEXEFilter()
	title,err:=syscall.UTF16PtrFromString("Servidor — Selecciona el EXE de tu juego RPG cerrado")
	if err!=nil{return "",false,errors.New("SERVIDOR_SELECTOR_TITLE_INVALID")}
	of:=tx771FileDialog{
		Size:uint32(unsafe.Sizeof(tx771FileDialog{})),Owner:owner,
		Filter:&filter[0],FilterIndex:1,File:&buffer[0],MaxFile:uint32(len(buffer)),
		Title:title,Flags:0x00001000|0x00000800|0x00080000|0x00000008,
	}
	common:=syscall.NewLazyDLL("comdlg32.dll")
	accepted,_,_:=common.NewProc("GetOpenFileNameW").Call(uintptr(unsafe.Pointer(&of)))
	var extendedCode uintptr
	if accepted==0{extendedCode,_,_=common.NewProc("CommDlgExtendedError").Call()}
	runtime.KeepAlive(buffer)
	runtime.KeepAlive(filter)
	runtime.KeepAlive(title)
	runtime.KeepAlive(of)
	if accepted==0{
		if extendedCode==0{return "",false,nil}
		return "",false,fmt.Errorf("SERVIDOR_SELECTOR_WINDOWS_0x%04X",extendedCode)
	}
	file:=filepath.Clean(syscall.UTF16ToString(buffer))
	if !filepath.IsAbs(file)||!strings.EqualFold(filepath.Ext(file),".exe"){
		return "",false,errors.New("SERVIDOR_SELECTOR_NOT_AN_ABSOLUTE_EXE")
	}
	info,err:=os.Lstat(file)
	if err!=nil||!info.Mode().IsRegular()||info.Mode()&os.ModeSymlink!=0{
		return "",false,errors.New("SERVIDOR_SELECTOR_FILE_MISSING_OR_LINKED")
	}
	return file,true,nil
}
