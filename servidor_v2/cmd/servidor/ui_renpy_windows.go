//go:build windows

package main

import (
 "os"
 "path/filepath"
 "unsafe"
)

func iaCreateRenpyControls(ui *iaUI){
 h:=ui.hwnd
 ui.renpyInfo=iaControl(h,"STATIC","1. Selecciona el EXE de una copia cerrada del juego Ren'Py:",0,230,187,780,34,0)
 ui.renpyInput=iaControl(h,"EDIT","",iaWSBorder|iaESReadOnly,230,227,597,44,0)
 ui.renpyBrowse=iaControl(h,"BUTTON","EXE",0,843,226,169,46,iaCmdRenpyBrowse)
 ui.renpyInstall=iaControl(h,"BUTTON","2. INSTALAR TRADUCTOR",0,230,302,326,59,iaCmdRenpyInstall)
 ui.renpyCheck=iaControl(h,"BUTTON","Estado IA Traductora",0,566,302,446,59,iaCmdRenpyStatus)
 ui.renpyLogs=iaControl(h,"EDIT","",iaWSBorder|iaWSVScroll|iaESMultiline|iaESReadOnly|iaESAutoVScroll,230,414,782,236,0)
 ui.renpyStatus=iaControl(h,"STATIC","Selecciona un juego Ren'Py.",0,230,664,773,39,0)
 ui.renpyRecover=iaControl(h,"BUTTON","Restaurar Ren'Py",0,501,710,274,36,iaCmdRenpyRecover)
 iaUser32.NewProc("SetTimer").Call(h,0x5245,1000,0)
 iaRenpyLog(ui,"[IA_RENPY_FIX2] Escaneo nativo y traducción OPUS en segundo plano. Progreso automático al abrir el juego.")
}
func iaRenpyLog(ui *iaUI,s string){
 if ui.renpyLogText!=""{ui.renpyLogText+="\r\n"};ui.renpyLogText+=s
 if ui.renpyLogs!=0{iaSet(ui.renpyLogs,ui.renpyLogText);iaSendMessage.Call(ui.renpyLogs,0x00B1,^uintptr(0),^uintptr(0));iaSendMessage.Call(ui.renpyLogs,0x00B7,0,0)}
}
func iaRefreshRenpy(ui *iaUI){
 for _,h:=range []uintptr{ui.renpyBrowse,ui.renpyInstall,ui.renpyRecover,ui.renpyCheck}{
  if h==0{continue};v:=uintptr(0)
  if ui.renpyActive&&!ui.busy&&(h==ui.renpyBrowse||ui.renpyFile!=""){v=1}
  iaEnableWindow.Call(h,v);iaInvalidateRect.Call(h,0,1)
 }
}
func iaSwitchRenpy(ui *iaUI){iaSwitchProgram(ui,0)}
func iaSwitchProgram(ui *iaUI,section int){
 if ui.busy{return};ui.renpyActive=section==0;ui.webActive=section==2
 show:=func(h uintptr,visible bool){if h==0{return};v:=uintptr(0);if visible{v=5};iaShowWindow.Call(h,v)}
 for _,h:=range []uintptr{ui.infoLabel,ui.input,ui.browse,ui.install,ui.cloneBtn,ui.jsonBtn,ui.logs,ui.statusLabel,ui.recoverBtn}{show(h,section==1)}
 for _,h:=range []uintptr{ui.webInfo,ui.webInput,ui.webBrowse,ui.webInstall,ui.webLogs,ui.webStatus}{show(h,section==2)}
 for _,h:=range []uintptr{ui.renpyInfo,ui.renpyInput,ui.renpyBrowse,ui.renpyInstall,ui.renpyRecover,ui.renpyCheck,ui.renpyLogs,ui.renpyStatus}{show(h,section==0)}
 label:=[]string{"REN'PY","RPG","WEB"}[section]
 if ui.sectionLabel!=0{iaSet(ui.sectionLabel,label)}
 iaRefreshRPGActions(ui);iaRefreshWebActions(ui);iaRefreshRenpy(ui)
 for _,h:=range []uintptr{ui.renpyBtn,ui.rpgBtn,ui.webBtn,ui.hwnd}{if h!=0{iaInvalidateRect.Call(h,0,1)}}
}
func iaRenpySelect(ui *iaUI){
 p,e:=iaChooseFile(ui.hwnd,iaExeFilterUTF16(),"Selecciona el EXE de una COPIA cerrada de Ren'Py")
 if e!=nil{iaRenpyLog(ui,"[IA_RENPY_SELECTOR_ERROR]");return};if p==""{return}
 ui.renpyFile="";iaSet(ui.renpyInput,"");defer iaRefreshRenpy(ui)
 d,e:=detectRenpy(p);if e!=nil{iaRenpyLog(ui,"["+iaSafeInstallCode(e.Error())+"]");iaSet(ui.renpyStatus,"No se reconoce un juego Ren'Py compatible.");return}
 ui.renpyFile=p;iaSet(ui.renpyInput,p);iaRenpyLog(ui,d.summary());iaSet(ui.renpyStatus,"Juego detectado; cierra el juego antes de instalar.")
}
func iaStartRenpy(ui *iaUI,restore bool){
 if !ui.renpyActive||ui.busy||ui.renpyFile==""{return}
 question:="Se instalará exclusivamente el complemento Ren'Py en esta copia. No se reescriben guiones, archivos RPA ni partidas. Mantén el juego cerrado. ¿Continuar?"
 if restore{question="Se desactivará el complemento Ren'Py propio. Se conserva la memoria y se guardan sus archivos fuera de game/. Cierra el juego. ¿Continuar?"}
 yes,_,_:=iaUser32.NewProc("MessageBoxW").Call(ui.hwnd,uintptr(unsafe.Pointer(iaUTF16(question))),uintptr(unsafe.Pointer(iaUTF16("Servidor · Ren'Py"))),0x24|0x100)
 if yes!=6{return}
 ui.busy=true;iaRefreshRenpy(ui);iaSet(ui.renpyStatus,"Verificando archivos...")
 p:=ui.renpyFile
 go func(){
  result:="IA_RENPY_FALLO"
  defer func(){if recover()!=nil{result="IA_RENPY_FALLO"};ui.mu.Lock();ui.renpyResult=result;ui.mu.Unlock();iaPostMessage.Call(ui.hwnd,iaWMRenpyDone,0,0)}()
  var e error
  if restore{e=renpyRecover(p);if e==nil{result="IA_RENPY_RESTAURADO"}}else{
   var source string;source,e=os.Executable()
   if e==nil{var pkg *packageReader;pkg,e=readPackage(source);if e==nil{defer pkg.Close();e=renpyInstall(p,pkg)}}
   if e==nil{result="IA_RENPY_INSTALADO"}
  }
  if e!=nil{result=iaSafeInstallCode(renpyStageError("OPERACION",e).Error())}
 }()
}
func iaRenpyFinish(ui *iaUI){
 ui.mu.Lock();s:=ui.renpyResult;ui.renpyResult="";ui.mu.Unlock();ui.busy=false;iaRefreshRenpy(ui)
 iaRenpyLog(ui,"["+s+"]")
 switch s{
 case "IA_RENPY_INSTALADO":iaSet(ui.renpyStatus,"Instalado. Abre normalmente el EXE original del juego.")
 case "IA_RENPY_RESTAURADO":iaSet(ui.renpyStatus,"Complemento desactivado. Partidas y memoria conservadas.")
 case "IA_RENPY_VERSION_ANTERIOR_RESTAURAR":iaSet(ui.renpyStatus,"Cierra el juego, pulsa Restaurar Ren'Py y vuelve a instalar.")
 default:iaSet(ui.renpyStatus,"Operación detenida. Revisa el diagnóstico; no fuerces cambios.")
 }
}
func iaRenpyStatus(ui *iaUI){
 if ui.renpyFile==""{return};s,e:=renpyStatusText(ui.renpyFile)
 if e!=nil{iaRenpyLog(ui,"["+iaSafeInstallCode(e.Error())+"]");return}
 iaRenpyLog(ui,"[IA_RENPY_ESTADO] "+s);iaSet(ui.renpyStatus,s)
}


func iaRenpyTick(ui *iaUI){
 if !ui.renpyActive||ui.busy||ui.renpyFile==""{return}
 side:=filepath.Join(filepath.Dir(ui.renpyFile),renpySide)
 if p,ok:=renpyReadProgress(side);ok{iaSet(ui.renpyStatus,renpyProgressLine(p))}
}
