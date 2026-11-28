//go:build windows

package main

import (
 "fmt"
 "os"
 "path/filepath"
 "strings"
 "syscall"
 "runtime"
 "unsafe"
)

// WEB has its own selection, diagnostics, controls and results. Only the
// application-wide busy guard and the navigation/footer are shared.
var iaSelectWebFile=iaChooseIndex
var iaWebInstallAction=iaStartWebClone
var iaWebOpenResult=iaShowWebResult

func iaCreateWebControls(ui *iaUI){
 hwnd:=ui.hwnd
 ui.webInfo=iaControl(hwnd,"STATIC","1. Selecciona el EXE original o index.html del juego WEB:",0,230,187,780,34,0)
 ui.webInput=iaControl(hwnd,"EDIT","",iaWSBorder|iaESReadOnly,230,227,597,44,0)
 ui.webBrowse=iaControl(hwnd,"BUTTON","EXE",0,843,226,169,46,iaCmdWebBrowse)
 ui.webInstall=iaControl(hwnd,"BUTTON","2. INSTALAR TRADUCTOR",0,230,302,326,59,iaCmdWebInstall)
 ui.webLogs=iaControl(hwnd,"EDIT","",iaWSBorder|iaWSVScroll|iaESMultiline|iaESReadOnly|iaESAutoVScroll,230,414,782,236,0)
 ui.webStatus=iaControl(hwnd,"STATIC","Listo para seleccionar un juego WEB.",0,230,664,773,39,0)
 iaWebLog(ui,"[IA_WEB_LISTA] Servidor R44 · WEB. EXE integrado Go o index.html extraído; copia independiente, motor OPUS local y ventana WebView2. No se modifica el origen.")
}

func iaWebActionAllowed(ui *iaUI)bool{
 return ui.webActive&&!ui.busy&&ui.webFile!=""
}

func iaRefreshWebActions(ui *iaUI){
 for _,item:=range []struct{handle uintptr;enabled bool}{
  {ui.webBrowse,ui.webActive&&!ui.busy},{ui.webInstall,iaWebActionAllowed(ui)},
 }{
  if item.handle==0{continue}
  value:=uintptr(0);if item.enabled{value=1}
  iaEnableWindow.Call(item.handle,value);iaInvalidateRect.Call(item.handle,0,1)
 }
}

func iaSwitchSection(ui *iaUI,web bool){
 if ui.busy{return}
 ui.webActive=web
 show:=func(h uintptr,visible bool){
  if h==0{return}
  cmd:=uintptr(0);if visible{cmd=5};iaShowWindow.Call(h,cmd)
 }
 for _,h:=range []uintptr{ui.infoLabel,ui.input,ui.browse,ui.install,ui.cloneBtn,ui.jsonBtn,ui.logs,ui.statusLabel,ui.recoverBtn}{show(h,!web)}
 for _,h:=range []uintptr{ui.webInfo,ui.webInput,ui.webBrowse,ui.webInstall,ui.webLogs,ui.webStatus}{show(h,web)}
 label:="RPG";if web{label="WEB"}
 if ui.sectionLabel!=0{iaSet(ui.sectionLabel,label)}
 iaRefreshRPGActions(ui);iaRefreshWebActions(ui)
 for _,h:=range []uintptr{ui.rpgBtn,ui.webBtn,ui.hwnd}{if h!=0{iaInvalidateRect.Call(h,0,1)}}
}

func iaWebLog(ui *iaUI,line string){
 if ui.webLogText!=""{ui.webLogText+="\r\n"}
 ui.webLogText+=line
 if ui.webLogs!=0{
  iaSet(ui.webLogs,ui.webLogText)
  iaSendMessage.Call(ui.webLogs,0x00B1,^uintptr(0),^uintptr(0))
  iaSendMessage.Call(ui.webLogs,0x00B7,0,0)
 }
}

func iaWebSelect(ui *iaUI){
 if ui.busy||!ui.webActive{return}
 file,err:=iaSelectWebFile(ui.hwnd)
 if err!=nil{
  iaWebLog(ui,"[IA_WEB_SELECTOR_ERROR] "+iaSafeInstallCode(err.Error()))
  iaSet(ui.webStatus,"No se pudo abrir el selector WEB.");return
 }
 if file==""{iaWebLog(ui,"[IA_WEB_SELECTOR_CANCELADO] Se conserva la selección anterior.");return}
 // A different invalid selection must never leave the previous game armed.
 ui.webFile="";ui.webOutput="";iaSet(ui.webInput,"")
 defer iaRefreshWebActions(ui)
 if strings.EqualFold(filepath.Ext(file),".exe"){
  if !ordinary(file){
   iaWebLog(ui,"[IA_WEB_EXE_RUTA_INVALIDA] Selecciona un EXE legible.")
   iaSet(ui.webStatus,"El EXE no es un archivo válido.");return
  }
  iaWebLog(ui,"[IA_WEB_EXE_SELECCIONADO] Listo para analizar. El formato se verificará durante la instalación.")
 }else if strings.EqualFold(filepath.Base(file),"index.html"){
  if _,err=webValidateFolder(filepath.Dir(file));err!=nil{
   code:=iaSafeInstallCode(err.Error());msg:=iaWebFriendly(code)
   iaWebLog(ui,"["+code+"] "+msg);iaSet(ui.webStatus,msg);return
  }
  iaWebLog(ui,"[IA_WEB_INDEX_SELECCIONADO] Carpeta web detectada.")
 }else{
  iaWebLog(ui,"[IA_WEB_INDEX_INVALIDO] Selecciona un EXE o index.html.")
  iaSet(ui.webStatus,"Archivo WEB no admitido.");return
 }
 ui.webFile=file;iaSet(ui.webInput,file)
 iaSet(ui.webStatus,"Juego WEB seleccionado. Listo para instalar.")
}

func iaWebFriendly(code string)string{
 switch code{
 case "IA_WEB_COPIA_DESTINO_INVALIDO","IA_WEB_COPIA_DESTINO_DENTRO_DEL_ORIGEN":
  return "No se puede crear la copia en ese destino. Usa una carpeta escribible fuera del origen."
 case "IA_WEB_COPIA_ORIGEN_CAMBIADO":
  return "El origen cambió durante la preparación. Cierra el juego y vuelve a intentar."
 case "IA_WEB_COPIA_RUTA_INSEGURA","IA_WEB_COPIA_RUTA_DUPLICADA","IA_WEB_RUTA_INVALIDA":
  return "Los recursos contienen rutas no admitidas. El original no se modifica."
 case "IA_WEB_COPIA_NO_LEIBLE":
  return "No se pudieron leer todos los recursos. Revisa permisos y copia el diagnóstico."
 case "IA_WEB_COPIA_TAMANO_EXCESIVO":
  return "El tamaño o número de recursos excede el límite del instalador WEB."
 case "IA_WEB_PUERTO_NO_DISPONIBLE":
  return "No se pudo reservar un puerto local para la nueva copia WEB."
 case "IA_WEB_COPIA_MARCADOR_FALLO","IA_WEB_COPIA_FALLO":
  return "No se completó la copia WEB. No ejecutes una copia incompleta; copia el diagnóstico."
 case "IA_NO_SE_PUEDE_LEER_SERVIDOR":
  return "No se pudo leer el paquete de Servidor."
 default:
  return iaFriendlyInstall(code)
 }
}

// Post progress to the GUI message loop; never touch HWNDs from a worker.
func iaWebQueue(ui *iaUI,line string){
 ui.mu.Lock();ui.webPending=append(ui.webPending,line);ui.mu.Unlock()
 iaPostMessage.Call(ui.hwnd,iaWMWebProgress,0,0)
}
func iaWebDrain(ui *iaUI){
 ui.mu.Lock();pending:=ui.webPending;ui.webPending=nil;ui.mu.Unlock()
 for _,line:=range pending{
  iaWebLog(ui,line)
  if i:=strings.Index(line,"] ");i>=0{iaSet(ui.webStatus,line[i+2:])}
 }
}

func iaStartWebClone(){
 ui:=&iaCurrentUI
 if !iaWebActionAllowed(ui){return}
 file:=ui.webFile
 fromEXE:=strings.EqualFold(filepath.Ext(file),".exe")
 executable,e:=os.Executable()
 if e!=nil{iaWebLog(ui,"[IA_NO_SE_PUEDE_LEER_SERVIDOR]");iaSet(ui.webStatus,iaWebFriendly("IA_NO_SE_PUEDE_LEER_SERVIDOR"));return}
 parent:=filepath.Dir(executable)
 yes,_,_:=iaUser32.NewProc("MessageBoxW").Call(ui.hwnd,
  uintptr(unsafe.Pointer(iaUTF16("Se buscarán los recursos web y se creará una carpeta Juego-IA-WEB junto al Servidor. El EXE original no se ejecuta ni modifica. Las partidas anteriores no se importan. ¿Continuar?"))),
  uintptr(unsafe.Pointer(iaUTF16("Instalar traductor WEB"))),0x24|0x100)
 if yes!=6{iaWebLog(ui,"[IA_WEB_INSTALACION_CANCELADA] No se modificó el origen.");return}
 ui.busy=true;ui.webOutput=""
 iaRefreshRPGActions(ui);iaRefreshWebActions(ui)
 for _,h:=range []uintptr{ui.rpgBtn,ui.webBtn}{if h!=0{iaEnableWindow.Call(h,0)}}
 iaSet(ui.webStatus,"Verificando el paquete de Servidor...")
 iaWebLog(ui,"[IA_WEB_INSTALACION_INICIADA] Preparando copia independiente.")
 go func(){
  info:="IA_ERROR_NO_CLASIFICADO";final:=""
  defer func(){
   if recover()!=nil{info="IA_WEB_COPIA_FALLO";final=""}
   ui.mu.Lock();ui.webResult=info;ui.webResultGame=final;ui.mu.Unlock()
   iaPostMessage.Call(ui.hwnd,iaWMWebDone,0,0)
  }()
  pkg,e:=readPackage(executable)
  if e!=nil{info=e.Error();return}
  defer pkg.Close()
  report:=func(line string){iaWebQueue(ui,line)}
  report("[IA_WEB_PAQUETE_LEIDO] Paquete leído; comenzando la preparación.")
  if fromEXE{final,e=webCloneFromEXEProgress(file,parent,pkg,report)}else{final,e=webCloneInstallProgress(filepath.Dir(file),parent,pkg,report)}
  if e!=nil{info=e.Error();final="";return}
  info="IA_WEB_COPIA_LISTA"
 }()
}

func iaWebFinish(ui *iaUI){
 iaWebDrain(ui)
 ui.mu.Lock();result:=ui.webResult;newGame:=ui.webResultGame;ui.webResult="";ui.webResultGame="";ui.mu.Unlock()
 ui.busy=false
 for _,h:=range []uintptr{ui.rpgBtn,ui.webBtn}{if h!=0{iaEnableWindow.Call(h,1);iaInvalidateRect.Call(h,0,1)}}
 iaRefreshRPGActions(ui);iaRefreshWebActions(ui)
 code:=iaSafeInstallCode(result)
 if code=="IA_WEB_COPIA_LISTA"&&newGame!=""{
  ui.webOutput=newGame
  iaWebLog(ui,"[IA_WEB_COPIA_LISTA] Copia independiente creada y verificada. Jugar-IA.exe, WebView2, motor OPUS y manifiesto instalados. Abre el EXE y prueba F10.")
  iaSet(ui.webStatus,"Instalación WEB completa. Abre Jugar-IA.exe.")
  iaWebOpenResult(ui.hwnd,newGame)
 }else{
  ui.webOutput=""
  if code=="IA_WEB_COPIA_LISTA"{code="IA_WEB_COPIA_FALLO"}
  msg:=iaWebFriendly(code)
  iaWebLog(ui,fmt.Sprintf("[%s] %s",code,msg))
  iaSet(ui.webStatus,msg)
 }
}

func iaShowWebResult(hwnd uintptr,newGame string){
 iaUser32.NewProc("MessageBoxW").Call(hwnd,uintptr(unsafe.Pointer(iaUTF16("Copia lista:\n"+newGame+"\n\nAbre Jugar-IA.exe desde esa carpeta."))),uintptr(unsafe.Pointer(iaUTF16("IA Traductora · WEB"))),0x40)
 // Open only the completed local directory; never launch the game here.
 shell:=syscall.NewLazyDLL("shell32.dll").NewProc("ShellExecuteW")
 folder:=iaUTF16(filepath.Dir(newGame));verb:=iaUTF16("open")
 shell.Call(hwnd,uintptr(unsafe.Pointer(verb)),uintptr(unsafe.Pointer(folder)),0,0,1)
 runtime.KeepAlive(folder);runtime.KeepAlive(verb)
}
