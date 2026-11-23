//go:build windows

package main

// Native CF_UNICODETEXT clipboard. Uses a movable Win32 memory allocation
// whose ownership transfers to Windows only after SetClipboardData succeeds.
import(
 "errors"
 "strings"
 "syscall"
 "unsafe"
)

const iaCFUnicodeText=13
const iaGMemMoveable=0x0002

var(
 iaOpenClipboard=iaUser32.NewProc("OpenClipboard")
 iaEmptyClipboard=iaUser32.NewProc("EmptyClipboard")
 iaCloseClipboard=iaUser32.NewProc("CloseClipboard")
 iaSetClipboardData=iaUser32.NewProc("SetClipboardData")
 iaGlobalAlloc=iaKernel32.NewProc("GlobalAlloc")
 iaGlobalLock=iaKernel32.NewProc("GlobalLock")
 iaGlobalUnlock=iaKernel32.NewProc("GlobalUnlock")
 iaGlobalFree=iaKernel32.NewProc("GlobalFree")
 iaWriteProcessMemory=iaKernel32.NewProc("WriteProcessMemory")
)

func iaClipboardText(hwnd uintptr,s string)error{
 if len(s)>96*1024{return errors.New("IA_DIAGNOSTICO_DEMASIADO_LARGO")}
 if s==""{s="[IA_SIN_DIAGNOSTICO]"}
 s=strings.ReplaceAll(s,"\x00"," ")
 utf16,_:=syscall.UTF16FromString(s)
 if len(utf16)==0{return errors.New("IA_COPIAR_TEXTO_INVALIDO")}
 ok,_,_:=iaOpenClipboard.Call(hwnd)
 if ok==0{return errors.New("IA_PORTAPAPELES_OCUPADO")}
 defer iaCloseClipboard.Call()
 ok,_,_=iaEmptyClipboard.Call()
 if ok==0{return errors.New("IA_PORTAPAPELES_NO_SE_PUEDE_VACIAR")}
 size:=uintptr(len(utf16)*2)
 memory,_,_:=iaGlobalAlloc.Call(iaGMemMoveable,size)
 if memory==0{return errors.New("IA_COPIAR_SIN_MEMORIA")}
 transferred:=false
 defer func(){if !transferred{iaGlobalFree.Call(memory)}}()
 target,_,_:=iaGlobalLock.Call(memory)
 if target==0{return errors.New("IA_COPIAR_MEMORIA_INACCESIBLE")}
 var written uintptr
 current,_,_:=iaGetCurrentProcess.Call()
 ok,_,_=iaWriteProcessMemory.Call(
  current,target,uintptr(unsafe.Pointer(&utf16[0])),
  size,uintptr(unsafe.Pointer(&written)))
 iaGlobalUnlock.Call(memory)
 if ok==0||written!=size{return errors.New("IA_COPIAR_MEMORIA_FALLIDA")}
 handle,_,_:=iaSetClipboardData.Call(iaCFUnicodeText,memory)
 if handle==0{return errors.New("IA_COPIAR_PORTAPAPELES_FALLIDO")}
 transferred=true
 return nil
}
