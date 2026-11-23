//go:build windows

package main

import(
 "errors"
 "strings"
 "testing"
)

func TestInstallErrorIsSanitizedNotUserPrivateWindowsPath(t *testing.T){
 raw:="rename E:\\Juegos\\日本語\\.ia-stage-123 E:\\Juegos\\日本語\\IA Traductora: Access is denied."
 if got:=iaSafeInstallCode(raw);got!="IA_ERROR_NO_CLASIFICADO"{
  t.Fatalf("failed to sanitize windows path: %q",got)
 }
 raw="IA_DESTINO_CREACION_DENEGADA: E:\\private\\game"
 if got:=iaSafeInstallCode(raw);got!="IA_DESTINO_CREACION_DENEGADA"{
  t.Fatalf("failed to isolate diagnostic code: %q",got)
 }
 msg:=iaFriendlyInstall("IA_DESTINO_CREACION_DENEGADA")
 if strings.Contains(msg,"E:\\")||!strings.Contains(msg,"Windows"){
  t.Fatalf("friendly error unsafe or uninformative: %s",msg)
 }
}
func TestCopyDiagnosticButtonDoesNotCloseApp(t *testing.T){
 oldCopy:=iaCopyDiagnostics
 oldHwnd:=iaCurrentUI.hwnd
 oldCopyBtn:=iaCurrentUI.copyBtn
 oldStatus:=iaCurrentUI.status
 oldLogs:=iaCurrentUI.logText
 defer func(){
  iaCopyDiagnostics=oldCopy
  iaCurrentUI.hwnd=oldHwnd
  iaCurrentUI.copyBtn=oldCopyBtn
  iaCurrentUI.status=oldStatus
  iaCurrentUI.logText=oldLogs
 }()
 wanted:="[IA_TRADUCTORA_LISTA] Lista\r\n[IA_DESTINO_CREACION_DENEGADA] Acceso bloqueado"
 called:=0
 iaCopyDiagnostics=func(_ uintptr,s string)error{
  called++
  if s!=wanted{return errors.New("unexpected clipboard source")}
  return nil
 }
 iaCurrentUI.hwnd=0
 iaCurrentUI.copyBtn=991
 iaCurrentUI.status=0
 iaCurrentUI.logText=wanted
 iaWinProc(0,iaWMCommand,uintptr(iaCmdCopy),991)
 if called!=1{t.Fatalf("copy was not invoked exactly once: %d",called)}
 if iaCurrentUI.logText!=wanted{t.Fatal("copy changed diagnostic data")}
}
