//go:build windows

package main

// Ventana Win32 única de Servidor: un motor por hoja, con detección MV/MZ.
// No ejecuta instaladores secundarios y mantiene la interfaz respondiendo.
import(
    "fmt"
    "os"
    "path/filepath"
    "errors"
    "runtime"
    "strings"
    "sync"
    "syscall"
    "unsafe"
)

const(
    iaWSOverlappedWindow=0x00CF0000
    iaWSVisible=0x10000000
    iaWSChild=0x40000000
    iaWSBorder=0x00800000
    iaWSVScroll=0x00200000
    iaWSDisabled=0x08000000
    iaESMultiline=0x0004
    iaESReadOnly=0x0800
    iaESAutoVScroll=0x0040
    iaWMCommand=0x0111
    iaWMDestroy=0x0002
    iaWMClose=0x0010
    iaWMAppDone=0x8001
    iaWMDrawItem=0x002B
    iaWMPaint=0x000F
    iaWMEraseBk=0x0014
    iaWMColorStatic=0x0138
    iaWMColorEdit=0x0133
    iaCmdBrowse=100
    iaCmdInstall=101
    iaCmdClose=102
    iaCmdCopy=103
    iaCmdRecover=104
    iaCmdClone=105
)
var(
    iaUser32=syscall.NewLazyDLL("user32.dll")
    iaKernel32=syscall.NewLazyDLL("kernel32.dll")
    iaComdlg32=syscall.NewLazyDLL("comdlg32.dll")
    iaCreateWindow=iaUser32.NewProc("CreateWindowExW")
    iaSetWindowText=iaUser32.NewProc("SetWindowTextW")
    iaEnableWindow=iaUser32.NewProc("EnableWindow")
    iaDestroyWindow=iaUser32.NewProc("DestroyWindow")
    iaPostMessage=iaUser32.NewProc("PostMessageW")
    iaShowWindow=iaUser32.NewProc("ShowWindow")
    iaUpdateWindow=iaUser32.NewProc("UpdateWindow")
    iaGetMessage=iaUser32.NewProc("GetMessageW")
    iaTranslateMessage=iaUser32.NewProc("TranslateMessage")
    iaDispatchMessage=iaUser32.NewProc("DispatchMessageW")
    iaDefWindowProc=iaUser32.NewProc("DefWindowProcW")
    iaPostQuitMessage=iaUser32.NewProc("PostQuitMessage")
    iaRegClass=iaUser32.NewProc("RegisterClassExW")
    iaGetModule=iaKernel32.NewProc("GetModuleHandleW")
    iaInvalidateRect=iaUser32.NewProc("InvalidateRect")
)
type iaWndClass struct{
    Size uint32
    Style uint32
    WndProc uintptr
    ExtraClass int32
    ExtraWindow int32
    Instance uintptr
    Icon uintptr
    Cursor uintptr
    Background uintptr
    MenuName *uint16
    ClassName *uint16
    IconSmall uintptr
}
type iaMsg struct{
    Window uintptr
    Message uint32
    Padding uint32
    WParam uintptr
    LParam uintptr
    Time uint32
    X int32
    Y int32
    Private uint32
}
type iaFileDialog struct{
    Size uint32
    Owner uintptr
    Instance uintptr
    Filter *uint16
    CustomFilter *uint16
    MaxCustomFilter uint32
    FilterIndex uint32
    File *uint16
    MaxFile uint32
    FileTitle *uint16
    MaxFileTitle uint32
    InitialDir *uint16
    Title *uint16
    Flags uint32
    FileOffset uint16
    FileExtension uint16
    DefaultExtension *uint16
    CustomData uintptr
    Hook uintptr
    TemplateName *uint16
    Reserved uintptr
    ReservedInt uint32
    FlagsEx uint32
}
type iaUI struct{
    hwnd uintptr
    gameFile string
    input uintptr
    browse uintptr
    closeBtn uintptr
    copyBtn uintptr
    recoverBtn uintptr
    cloneBtn uintptr
    webBtn uintptr
    cloneAllowed bool
    jsonPilot bool
    jsonSummary string
    resultGame string
    titleLabel uintptr
    sectionLabel uintptr
    statusLabel uintptr
    infoLabel uintptr
    install uintptr
    status uintptr
    logs uintptr
    logText string
    mu sync.Mutex
    result string
    busy bool
}
var iaCurrentUI iaUI
func iaUTF16(s string)*uint16{return syscall.StringToUTF16Ptr(s)}
func iaControl(parent uintptr,klass,title string,style uint32,x,y,width,height,id int)uintptr{
    if klass=="BUTTON"{style|=0x0000000B} // BS_OWNERDRAW
    win,_,_:=iaCreateWindow.Call(0,uintptr(unsafe.Pointer(iaUTF16(klass))),
        uintptr(unsafe.Pointer(iaUTF16(title))),uintptr(style)|iaWSVisible|iaWSChild,
        uintptr(x),uintptr(y),uintptr(width),uintptr(height),parent,uintptr(id),0,0)
    if win!=0{iaApplyControlFont(win,klass,id,title)}
    return win
}
func iaSet(hwnd uintptr,text string){
    iaSetWindowText.Call(hwnd,uintptr(unsafe.Pointer(iaUTF16(text))))
}
func iaLog(line string){
    if iaCurrentUI.logText!=""{iaCurrentUI.logText+="\r\n"}
    iaCurrentUI.logText+=line
    iaSet(iaCurrentUI.logs,iaCurrentUI.logText)
    // Preserve easy reading of the newest diagnostic without a separate window.
    iaSendMessage.Call(iaCurrentUI.logs,0x00B1,^uintptr(0),^uintptr(0)) // EM_SETSEL
    iaSendMessage.Call(iaCurrentUI.logs,0x00B7,0,0) // EM_SCROLLCARET
}
func iaSafeInstallCode(message string)string{
    if !strings.HasPrefix(message,"IA_"){return "IA_ERROR_NO_CLASIFICADO"}
    end:=0
    for i:=0;i<len(message);i++{
        c:=message[i]
        if !((c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'){break}
        end=i+1
    }
    if end<6||end>110{return "IA_ERROR_NO_CLASIFICADO"}
    return message[:end]
}
func iaFriendlyInstall(code string)string{
    switch code{
    case "IA_MV_JSON_SIN_TRADUCCIONES_VALIDAS":
        return "No se obtuvo una traducción válida del mapa inicial. El juego original permanece intacto."
    case "IA_MV_JSON_COPIA_PREVIA_NO_ADMITIDA":
        return "Selecciona una copia limpia del juego, sin IA Traductora ni una prueba JSON anterior."
    case mvnwbinManifestMissing:
        return "RPG Maker MV con NWBin detectado. Falta verificar package.json; no se modificó el juego."
    case mvnwbinExtensionUnavailable:
        return "MV con complementos binarios detectado. Se necesita un registro de complementos autorizado por el juego. Binarios y arranque intactos."
    case mvnwbinInvalid:
        return "MV/NWBin detectado, pero su arranque o recursos no coinciden con el perfil verificado. Juego intacto."
    case "IA_RPGXP_PAQUETE_INCOMPLETO":
        return "Este paquete no contiene el traductor XP. Usa Servidor R43 de prueba."
    case "IA_RPGXP_OPERACION_ACTIVA_O_PENDIENTE","IA_RPGXP_SESION_ACTIVA_O_PENDIENTE":
        return "Cierra el juego y espera a que termine el motor. Conserva la memoria y el respaldo."
    case "IA_RPGXP_SCRIPTS_MARSHAL_INVALIDO","IA_RPGXP_MAIN_NO_ENCONTRADO","IA_RPGXP_MAIN_AMBIGUO":
        return "Scripts.rxdata no coincide con el formato XP admitido. No se reemplazó el original. Copia el diagnóstico."
    case rpgxpPackedCode:
        return "RPG Maker XP con archivo RGSSAD detectado. Formato empaquetado aún no admitido; juego intacto."
    case rpgxpInvalidCode:
        return "RPG Maker XP detectado, pero sus recursos no se han podido verificar. Juego intacto."
    case cookToolPackedCode:
        return "RPG Maker Dragonhouse/Halva detectado. Requiere una exportación o integración autorizada; no se han modificado los paquetes."
    case "IA_HALVA_VERSION_EXISTENTE_CONSERVADA":
        return "Hay una versión Halva previa. No se sobrescribieron los modelos ni la memoria."
    case "IA_HALVA_PAQUETE_CAMBIADO","IA_HALVA_RESPALDO_ALTERADO","IA_HALVA_COPIA_ALTERADA":
        return "El paquete o respaldo cambió. Se conserva intacto; usa una copia original verificada."
    case cookToolUnsafeCode:
        return "Estructura Dragonhouse/Halva incompleta o insegura. No se ha modificado el juego."
    case "IA_WEB_RECURSOS_INCOMPLETOS","IA_WEB_MODULO_NO_ADMITIDO","IA_WEB_INDEX_INVALIDO","IA_WEB_COPIA_RECURSO_NO_ADMITIDO":
        return "Selecciona index.html de una carpeta web extraída completa. No se modificará el origen."
    case "IA_WEB_EXE_FORMATO_NO_ADMITIDO","IA_WEB_EXE_FRONTEND_NO_ENCONTRADO","IA_WEB_EXE_TABLA_AMBIGUA":
        return "No se encontró un frontend Go compatible y único. Se conserva el original; puedes elegir index.html extraído si dispones de él."
    case "IA_WEB_EXE_RECURSO_SHA_INVALIDO","IA_WEB_EXE_RUTA_INSEGURA","IA_WEB_EXE_EXTRACCION_FALLO","IA_WEB_EXE_NO_LEIBLE","IA_WEB_EXE_RUTA_INVALIDA":
        return "No se pudo verificar la extracción del EXE. El archivo de origen permanece intacto."
    case "IA_WEB_HOST_NO_INCLUIDO","IA_WEB_HOST_PAQUETE_INCOMPLETO","IA_WEB_HOST_SHA_INVALIDO":
        return "El paquete de ventana web no se pudo verificar. No ejecutes una copia incompleta."
    case "IA_DESTINO_CREACION_DENEGADA":
        return "Windows bloqueó la creación de IA Traductora. No se modificó el registro."
    case "IA_DESTINO_SIN_PERMISO":
        return "Windows no permite inspeccionar la carpeta de destino."
    case "IA_DESTINO_AJENO_NO_MODIFICADO","IA_DESTINO_EXISTENTE_NO_SOBRESCRITO":
        return "Ya hay una carpeta distinta en el destino. No se ha sobrescrito."
    case "IA_VXACE_REPLACE_SHARING_WIN32_32","IA_VXACE_REPLACE_LOCKED_WIN32_33":
        return "El archivo VX Ace está abierto o bloqueado. Cierra el juego y sus lanzadores. Se conserva el respaldo; no borres los archivos."
    case "IA_VXACE_REPLACE_ACCESS_DENIED_WIN32_5":
        return "Windows negó el reemplazo. Cierra el juego o utiliza Crear copia VX Ace. Se conserva el respaldo."
    case "IA_VXACE_COPIA_SIDECAR_NO_VERIFICADO","IA_VXACE_COPIA_RECIBO_NO_VERIFICADO","IA_VXACE_COPIA_RESPALDO_NO_VERIFICADO":
        return "No se pudo verificar la instalación anterior. Usa una copia original cerrada; no borres respaldos."
    case "IA_VXACE_COPIA_DESTINO_NO_CREADO","IA_VXACE_COPIA_DESTINO_INVALIDO":
        return "No se puede crear otra carpeta junto al juego. Usa una carpeta escribible con espacio libre."
    case "IA_VXACE_COPIA_ORIGEN_CAMBIADO":
        return "El origen cambió durante la copia. Cierra el juego. No ejecutes la copia incompleta."
    case "IA_VXACE_RECURSO_CAMBIO_DURANTE_REEMPLAZO","IA_VXACE_REPLACE_TEMP_SHA_INVALIDO":
        return "El archivo cambió o no coincide con su SHA. Se detuvo el reemplazo; conserva el respaldo."
    case "IA_VXACE_REPLACE_ATTR_RESTORE_FAILED":
        return "Windows no permitió restaurar el atributo del archivo. Conserva el respaldo y usa Recuperar inicio RPG antes de reintentar."
    case "IA_PUBLICACION_CAMBIO_NOMBRE_FALLIDO":
        return "Windows no permitió publicar los modelos. Se conservaron para reintentar."
    case "IA_ESCRITURA_BLOQUEADA","IA_ETAPA_ESCRITURA_BLOQUEADA":
        return "Windows bloqueó la escritura de modelos. Cierra el juego y revisa permisos."
    case "IA_INSTALACION_EXISTENTE_REVISAR":
        return "Existe una instalación previa. No se han sobrescrito sus archivos."
    case "IA_PROPIEDAD_O_VERSION_DIFERENTE":
        return "La carpeta contiene archivos de otra versión. No se han sobrescrito."
    case "IA_MODELO_SHA_NO_COINCIDE":
        return "El modelo no coincide con su firma. No se continuará."
    case "IA_RECUPERACION_REGISTRO_CAMBIADO":
        return "El registro fue editado tras instalar. No se sobrescribió."
    case "IA_RECUPERACION_RESPALDO_ALTERADO":
        return "El respaldo no coincide con su SHA. No se ha restaurado."
    case "IA_RECUPERACION_ESTADO_NO_VERIFICADO":
        return "No se reconoció una instalación nuestra. Nada fue modificado."
    default:
        return "Instalación detenida. Pulsa Copiar diagnóstico para enviar el código."
    }
}

var iaSelectFile=iaChooseEXE
var iaCopyDiagnostics=iaClipboardText
func iaChooseEXE(owner uintptr)(string,error){
    return iaChooseFile(owner,iaExeFilterUTF16(),"Selecciona el Game.exe de una COPIA cerrada del videojuego")
}
func iaWebSourceFilterUTF16()[]uint16{
    filter:=append(syscall.StringToUTF16("Juego web Windows (*.exe)"),syscall.StringToUTF16("*.exe")...)
    filter=append(filter,syscall.StringToUTF16("Interfaz web extraída (index.html)")...)
    filter=append(filter,syscall.StringToUTF16("index.html")...)
    return append(filter,0)
}
func iaChooseIndex(owner uintptr)(string,error){
    return iaChooseFile(owner,iaWebSourceFilterUTF16(),"Selecciona EXE original del juego WEB (o index.html ya extraído)")
}
func iaChooseFile(owner uintptr,filter []uint16,caption string)(selected string,err error){
    defer func(){
        if recover()!=nil{
            selected=""
            err=errors.New("IA_SELECTOR_PANICO_RECUPERADO")
        }
    }()
    buffer:=make([]uint16,32768)
    title:=iaUTF16(caption)
    data:=iaFileDialog{
        Size:uint32(unsafe.Sizeof(iaFileDialog{})),Owner:owner,
        Filter:&filter[0],File:&buffer[0],MaxFile:uint32(len(buffer)),
        Title:title,Flags:0x00080000|0x00001000|0x00000800,
    }
    ok,_,callError:=iaComdlg32.NewProc("GetOpenFileNameW").
        Call(uintptr(unsafe.Pointer(&data)))
    runtime.KeepAlive(buffer)
    runtime.KeepAlive(filter)
    runtime.KeepAlive(title)
    runtime.KeepAlive(data)
    if ok==0{
        errorCode,_,_:=iaComdlg32.NewProc("CommDlgExtendedError").Call()
        if errorCode==0{return "",nil}
        return "",fmt.Errorf("IA_SELECTOR_WINDOWS_0x%X: %w",errorCode,callError)
    }
    path:=syscall.UTF16ToString(buffer)
    if path==""{return "",fmt.Errorf("IA_SELECTOR_SIN_RUTA")}
    return path,nil
}
func iaStartInstall(){
    ui:=&iaCurrentUI
    if ui.gameFile==""{
        iaLog("[IA_EXE_REQUERIDO] Selecciona primero Game.exe.")
        return
    }
    if ui.busy{return}
    if ui.jsonPilot{iaStartJSONPilot();return}
    if kind,e:=detectInstallTarget(ui.gameFile);e==nil&&kind==rpgxpTrialKind{
        yes,_,_:=iaUser32.NewProc("MessageBoxW").Call(ui.hwnd,
            uintptr(unsafe.Pointer(iaUTF16("RPG Maker XP experimental. Usa una copia cerrada del juego, no el original. Se respaldará Scripts.rxdata; podrás usar Recuperar inicio RPG. La compatibilidad con los scripts personalizados aún no está confirmada. ¿Instalar en la copia seleccionada?"))),
            uintptr(unsafe.Pointer(iaUTF16("Servidor R43 — prueba XP"))),0x24|0x100)
        if yes!=6{return}
        iaLog("[IA_RPGXP_PRUEBA] Instalación experimental autorizada en una copia cerrada.")
    }
    ui.busy=true
    iaEnableWindow.Call(ui.install,0)
    iaEnableWindow.Call(ui.browse,0)
    iaEnableWindow.Call(ui.cloneBtn,0)
    iaSet(ui.status,"Preparando IA Traductora...")
    iaLog("[IA_INICIANDO] Verificando el paquete propio y los modelos.")
    game:=ui.gameFile
    go func(){
        info:="IA_ERROR_NO_CLASIFICADO"
        defer func(){
            if recover()!=nil{info="IA_INSTALACION_PANICO_RECUPERADO"}
            ui.mu.Lock();ui.result=info;ui.mu.Unlock()
            iaPostMessage.Call(ui.hwnd,iaWMAppDone,0,0)
        }()
        executable,e:=os.Executable()
        if e!=nil{info="IA_NO_SE_PUEDE_LEER_SERVIDOR"}else{
            pkg,err:=readPackage(executable)
            if err!=nil{info=err.Error()}else{
                defer pkg.Close()
                err=Install(game,pkg)
                if err!=nil{info=err.Error()}else{
                    identity,verifyErr:=installedPackageIdentity(game,pkg)
                    if verifyErr!=nil{info=verifyErr.Error()}else{info="IA_INSTALACION_COMPLETADA_VERIFICADA|"+identity}
                }
            }
        }
    }()
}
func iaStartRecover(){
    ui:=&iaCurrentUI
    if ui.jsonPilot{return}
    if ui.gameFile==""{
        iaLog("[IA_RECUPERACION_GAME_EXE_REQUERIDO] Selecciona Game.exe.")
        return
    }
    if ui.busy{return}
    ui.busy=true
    iaEnableWindow.Call(ui.install,0)
    iaEnableWindow.Call(ui.browse,0)
    iaEnableWindow.Call(ui.recoverBtn,0)
    iaEnableWindow.Call(ui.cloneBtn,0)
    iaSet(ui.status,"Comprobando respaldo original...")
    iaLog("[IA_RECUPERACION_INICIADA] Restaurando el recurso original de esta copia RPG; se conserva la memoria.")
    game:=ui.gameFile
    go func(){
        info:="IA_RECUPERACION_ERROR_NO_CLASIFICADO"
        defer func(){
            if recover()!=nil{info="IA_RECUPERACION_PANICO_RECUPERADO"}
            ui.mu.Lock();ui.result=info;ui.mu.Unlock()
            iaPostMessage.Call(ui.hwnd,iaWMAppDone,0,0)
        }()
        if err:=RecoverGame(game);err!=nil{info=err.Error()}else{
            info="IA_RECUPERACION_REGISTRO_ORIGINAL_VERIFICADA"
        }
    }()
}
func iaStartJSONPilot(){
    ui:=&iaCurrentUI
    if ui.busy||!ui.jsonPilot||ui.gameFile==""{return}
    yes,_,_:=iaUser32.NewProc("MessageBoxW").Call(ui.hwnd,
      uintptr(unsafe.Pointer(iaUTF16("Cierra el juego. Se creará una carpeta independiente junto al original, con sus archivos, menú nativo, diálogos y elecciones del mapa inicial traducidos. No se tocarán los binarios. F10 solo estará disponible en Servidor para ver el estado. Si el juego no admite estos datos, usa el original. ¿Crear copia de prueba?"))),
      uintptr(unsafe.Pointer(iaUTF16("R44 - copia JSON de prueba"))),0x24|0x100)
    if yes!=6{return}
    ui.busy=true
    iaEnableWindow.Call(ui.install,0);iaEnableWindow.Call(ui.browse,0)
    iaEnableWindow.Call(ui.recoverBtn,0);iaEnableWindow.Call(ui.cloneBtn,0);iaEnableWindow.Call(ui.webBtn,0)
    iaSet(ui.status,"Copiando recursos y traduciendo el mapa inicial con OPUS local...")
    iaLog("[IA_MV_JSON_INICIADA] El juego original queda intacto. No abras la copia incompleta.")
    game:=ui.gameFile
    go func(){
        info:="IA_MV_JSON_MOTOR_FALLO";final:=""
        defer func(){
            if recover()!=nil{info="IA_INSTALACION_PANICO_RECUPERADO";final=""}
            ui.mu.Lock();ui.result=info;ui.resultGame=final;ui.mu.Unlock()
            iaPostMessage.Call(ui.hwnd,iaWMAppDone,0,0)
        }()
        executable,e:=os.Executable();if e!=nil{info="IA_NO_SE_PUEDE_LEER_SERVIDOR";return}
        pkg,e:=readPackage(executable);if e!=nil{info=e.Error();return};defer pkg.Close()
        path,report,e:=mvJSONCopyPilot(game,pkg)
        if e!=nil{info=e.Error();return}
        final=path;info=fmt.Sprintf("IA_MV_JSON_COPIA_LISTA|Diálogos: %d · Elecciones: %d · Menú: %d · Ajustes de línea: %d · Avisos de ancho: %d",report.Lines,report.ChoiceLabels,report.Menu,report.Wrapped,report.FitWarnings)
    }()
}
func iaStartClone(){
    ui:=&iaCurrentUI
    if ui.busy||!ui.cloneAllowed||ui.gameFile==""{return}
    yes,_,_:=iaUser32.NewProc("MessageBoxW").Call(ui.hwnd,
        uintptr(unsafe.Pointer(iaUTF16("Cierra el juego y sus lanzadores. Se creará una carpeta Juego-IA-VXACE nueva junto al juego, con copia de recursos y partidas. No se cambiará el origen. No abras la copia si la instalación no termina. ¿Continuar?"))),
        uintptr(unsafe.Pointer(iaUTF16("Crear copia VX Ace"))),0x24|0x100)
    if yes!=6{return}
    ui.busy=true
    iaEnableWindow.Call(ui.install,0);iaEnableWindow.Call(ui.browse,0)
    iaEnableWindow.Call(ui.recoverBtn,0);iaEnableWindow.Call(ui.cloneBtn,0)
    iaSet(ui.status,"Creando copia independiente. No abras el juego.")
    iaLog("[IA_VXACE_COPIA_INICIADA] El original no se reemplazará.")
    game:=ui.gameFile
    go func(){
        info:="IA_ERROR_NO_CLASIFICADO";final:=""
        defer func(){
            if recover()!=nil{info="IA_INSTALACION_PANICO_RECUPERADO";final=""}
            ui.mu.Lock();ui.result=info;ui.resultGame=final;ui.mu.Unlock()
            iaPostMessage.Call(ui.hwnd,iaWMAppDone,0,0)
        }()
        executable,e:=os.Executable()
        if e!=nil{info="IA_NO_SE_PUEDE_LEER_SERVIDOR";return}
        pkg,e:=readPackage(executable)
        if e!=nil{info=e.Error();return}
        defer pkg.Close()
        path,identity,e:=vxaceCloneInstall(game,"",pkg)
        if e!=nil{info=e.Error();return}
        final=path
        info="IA_INSTALACION_COMPLETADA_VERIFICADA|"+identity
    }()
}


func iaStartWebClone(){
 ui:=&iaCurrentUI
 if ui.busy{return}
 file,e:=iaChooseIndex(ui.hwnd)
 if e!=nil{iaLog("[IA_SELECTOR_ERROR] "+iaSafeInstallCode(e.Error()));return}
 if file==""{return}
 fromEXE:=strings.EqualFold(filepath.Ext(file),".exe")
 root:=""
 if !fromEXE{
  if !strings.EqualFold(filepath.Base(file),"index.html"){
   iaSet(ui.status,"Selecciona el EXE original o el index.html de una carpeta web extraída.");return
  }
  root,e=webValidateFolder(filepath.Dir(file))
  if e!=nil{code:=iaSafeInstallCode(e.Error());iaLog("["+code+"] Carpeta web no admitida.");iaSet(ui.status,iaFriendlyInstall(code));return}
 }
 executable,e:=os.Executable()
 if e!=nil{iaLog("[IA_NO_SE_PUEDE_LEER_SERVIDOR]");return}
 parent:=filepath.Dir(executable)
 yes,_,_:=iaUser32.NewProc("MessageBoxW").Call(ui.hwnd,
  uintptr(unsafe.Pointer(iaUTF16("Se buscarán los recursos web y se creará una carpeta Juego-IA-WEB junto al Servidor. El EXE original no se ejecuta ni modifica. Las partidas anteriores no se importan. ¿Continuar?"))),
  uintptr(unsafe.Pointer(iaUTF16("Crear copia web jugable"))),0x24|0x100)
 if yes!=6{return}
 ui.busy=true
 iaEnableWindow.Call(ui.install,0);iaEnableWindow.Call(ui.browse,0)
 iaEnableWindow.Call(ui.recoverBtn,0);iaEnableWindow.Call(ui.cloneBtn,0);iaEnableWindow.Call(ui.webBtn,0)
 if fromEXE{
  iaSet(ui.status,"Analizando EXE y verificando recursos web...")
  iaLog("[IA_WEB_EXE_ANALISIS] Lectura estática. No se ejecutará el original.")
 }else{
  iaSet(ui.status,"Creando copia web con ventana propia...")
  iaLog("[IA_WEB_COPIA_INICIADA] Recursos de origen intactos.")
 }
 go func(){
  info:="IA_ERROR_NO_CLASIFICADO";final:=""
  defer func(){
   if recover()!=nil{info="IA_WEB_COPIA_FALLO";final=""}
   ui.mu.Lock();ui.result=info;ui.resultGame=final;ui.mu.Unlock()
   iaPostMessage.Call(ui.hwnd,iaWMAppDone,0,0)
  }()
  pkg,e:=readPackage(executable)
  if e!=nil{info=e.Error();return}
  defer pkg.Close()
  if fromEXE{final,e=webCloneFromEXE(file,parent,pkg)}else{final,e=webCloneInstall(root,parent,pkg)}
  if e!=nil{info=e.Error();final="";return}
  info="IA_WEB_COPIA_LISTA"
 }()
}

func iaWinProc(hwnd uintptr,message uint32,wparam,lparam uintptr)(ret uintptr){
    defer func(){
        if recover()!=nil{
            if iaCurrentUI.logs!=0 {iaLog("[IA_INTERFAZ_PANICO_RECUPERADO] El programa continúa abierto.")}
            ret=0
        }
    }()
    ui:=&iaCurrentUI
    switch message {
    case iaWMClose:
        if ui.busy{return 0}
        iaDestroyWindow.Call(hwnd);return 0
    case iaWMDestroy:
        iaThemeDestroy()
        iaPostQuitMessage.Call(0);return 0
    case iaWMEraseBk:
        return 1
    case iaWMPaint:
        iaPaintWindow(hwnd)
        return 0
    case iaWMDrawItem:
        if iaDrawButton(lparam){return 1}
    case iaWMColorStatic,iaWMColorEdit:
        return iaColorControl(wparam,lparam)
    case iaWMCommand:
        switch int(wparam&0xFFFF){
        case 302:
            if lparam==ui.webBtn&&!ui.busy{iaStartWebClone()}
        case iaCmdBrowse:
            if lparam!=ui.browse || ui.busy{return 0}
            file,err:=iaSelectFile(hwnd)
            if err!=nil{
                iaLog("[IA_SELECTOR_ERROR] "+err.Error())
                iaSet(ui.status,"No se pudo abrir el selector. Servidor sigue abierto.")
            }else if file!=""{
                ui.jsonPilot=false;iaSet(ui.install,"2. INSTALAR TRADUCTOR")
                if kind,e:=detectInstallTarget(file);e!=nil{
                    // An invalid new selection must never leave a different game armed for installation.
                    ui.gameFile="";iaSet(ui.input,"");ui.cloneAllowed=false
                    iaEnableWindow.Call(ui.install,0);iaEnableWindow.Call(ui.recoverBtn,0);iaEnableWindow.Call(ui.cloneBtn,0)
                    code:=iaSafeInstallCode(e.Error())
                    if code==cookToolPackedCode||code==cookToolUnsafeCode{
                        iaLog("[IA_RPG_HALVA_DETECTADO] "+e.Error())
                        iaSet(ui.status,iaFriendlyInstall(code))
                    }else if strings.HasPrefix(code,"IA_MV_NWBIN_"){
                        iaLog("[IA_MV_NWBIN_DETECTADO] "+code)
                        iaSet(ui.status,iaFriendlyInstall(code))
                        if code==mvnwbinExtensionUnavailable{
                            ui.gameFile=file;ui.jsonPilot=true;iaSet(ui.input,file)
                            iaSet(ui.install,"2. CREAR COPIA JSON");iaEnableWindow.Call(ui.install,1)
                            iaLog("[IA_MV_JSON_PRUEBA_DISPONIBLE] Traducción offline del mapa inicial, sin modificar el arranque.")
                            iaSet(ui.status,"MV/NWBin: crea una copia JSON de prueba.")
                        }
                    }else if strings.HasPrefix(code,"IA_RPGXP_"){
                        iaLog("[IA_RPGXP_DETECTADO] "+code)
                        iaSet(ui.status,iaFriendlyInstall(code))
                    }else{
                        iaLog("[IA_EXE_NO_COMPATIBLE] "+code)
                        iaSet(ui.status,"Selecciona Game.exe de una copia MV, MZ, VX Ace o XP experimental.")
                    }
                }else{
                    ui.gameFile=file;iaSet(ui.input,file)
                    fp,matched,ve:=detectVXAce(file)
                    ui.cloneAllowed=matched&&ve==nil&&fp.Packed
                    if ui.cloneAllowed{iaEnableWindow.Call(ui.cloneBtn,1)}else{iaEnableWindow.Call(ui.cloneBtn,0)}
                    iaEnableWindow.Call(ui.install,1);iaEnableWindow.Call(ui.recoverBtn,1)
                    iaSet(ui.status,"Juego "+kind+" seleccionado. Listo para instalar.")
                    iaLog("[IA_EXE_SELECCIONADO] Motor "+kind+" verificado.")
                    if kind==mvnwbinKind{
                        iaLog("[IA_MV_NWBIN_ADDONS] Registro adicional ya previsto en el arranque. No se sustituyen binarios ni index.html.")
                    }
                    if kind==rpgxpTrialKind{
                        iaLog("[IA_RPGXP_DETECTADO] RGSS1: instalación de prueba, respaldo de Scripts.rxdata y recuperación disponibles.")
                        iaSet(ui.status,"RPG Maker XP detectado. Instala únicamente en una copia cerrada.")
                    }
                    if strings.HasSuffix(kind," Halva"){
                        iaLog("[IA_HALVA_NATIVO_PRUEBA] Copia cerrada; solo se modifica EnginePackage con respaldo. Abre mediante el lanzador habitual.")
                        iaSet(ui.status,"Halva plano compatible con instalación de prueba; arranque por comprobar.")
                    }
                }
            }else{
                iaLog("[IA_SELECTOR_CANCELADO] Puedes volver a pulsar EXE.")
            }
        case iaCmdInstall:
            if lparam==ui.install {iaStartInstall()}
        case iaCmdRecover:
            if lparam==ui.recoverBtn {iaStartRecover()}
        case iaCmdClone:
            if lparam==ui.cloneBtn {iaStartClone()}
        case iaCmdCopy:
            if lparam==ui.copyBtn{
                if err:=iaCopyDiagnostics(hwnd,ui.logText);err!=nil{
                    iaLog("[IA_COPIAR_ERROR] "+iaSafeInstallCode(err.Error()))
                    iaSet(ui.status,"No se pudo copiar. Revisa el diagnóstico en pantalla.")
                }else{
                    iaSet(ui.status,"Diagnóstico copiado. Puedes pegarlo en el chat.")
                }
            }
        case iaCmdClose:
            if lparam==ui.closeBtn && !ui.busy{iaDestroyWindow.Call(hwnd)}
        }
        return 0
    case iaWMAppDone:
        ui.mu.Lock();result:=ui.result;newGame:=ui.resultGame;ui.resultGame="";ui.mu.Unlock()
        ui.busy=false
        iaEnableWindow.Call(ui.browse,1)
        iaEnableWindow.Call(ui.webBtn,1)
        if ui.jsonPilot{iaEnableWindow.Call(ui.recoverBtn,0)}else{iaEnableWindow.Call(ui.recoverBtn,1)}
        if ui.cloneAllowed{iaEnableWindow.Call(ui.cloneBtn,1)}
        code:=iaSafeInstallCode(result)
        if code=="IA_MV_JSON_COPIA_LISTA"&&newGame!=""{
            ui.gameFile="";ui.jsonPilot=false;ui.cloneAllowed=false
            iaSet(ui.input,newGame);iaSet(ui.install,"2. INSTALAR TRADUCTOR")
            iaEnableWindow.Call(ui.install,0);iaEnableWindow.Call(ui.recoverBtn,0);iaEnableWindow.Call(ui.cloneBtn,0)
            lines:=strings.TrimPrefix(result,"IA_MV_JSON_COPIA_LISTA|")
            ui.jsonSummary=lines+"\n\n"+newGame+"\n\nModo JSON previo al juego. F10 en esta ventana consulta el estado; no es un complemento del juego."
            iaLog("[IA_MV_JSON_COPIA_LISTA] "+lines+". Abre el EXE de la nueva copia. F10 en Servidor: estado.")
            iaSet(ui.status,"Copia JSON lista. F10 en Servidor: estado.")
            iaUser32.NewProc("MessageBoxW").Call(hwnd,uintptr(unsafe.Pointer(iaUTF16("Copia de prueba lista:\n"+ui.jsonSummary+"\n\nAbre el EXE de la copia. El original permanece intacto."))),uintptr(unsafe.Pointer(iaUTF16("Servidor R44"))),0x40)
        }else if code=="IA_WEB_COPIA_LISTA"&&newGame!=""{
            ui.gameFile="";ui.jsonPilot=false;ui.cloneAllowed=false;iaSet(ui.install,"2. INSTALAR TRADUCTOR");iaSet(ui.input,newGame)
            iaEnableWindow.Call(ui.install,0);iaEnableWindow.Call(ui.recoverBtn,0);iaEnableWindow.Call(ui.cloneBtn,0)
            iaLog("[IA_WEB_COPIA_LISTA] Abre Jugar-IA.exe en la nueva carpeta. Ventana propia, sin navegador externo.")
            iaSet(ui.status,"Copia web preparada. Abre Jugar-IA.exe y prueba F10.")
            iaUser32.NewProc("MessageBoxW").Call(hwnd,uintptr(unsafe.Pointer(iaUTF16("Copia lista:\n"+newGame+"\n\nAbre Jugar-IA.exe desde esa carpeta."))),uintptr(unsafe.Pointer(iaUTF16("IA Traductora"))),0x40)
            // Open only the newly created local directory, not a URL.
            shell:=syscall.NewLazyDLL("shell32.dll").NewProc("ShellExecuteW")
            folder:=iaUTF16(filepath.Dir(newGame));verb:=iaUTF16("open")
            shell.Call(hwnd,uintptr(unsafe.Pointer(verb)),uintptr(unsafe.Pointer(folder)),0,0,1)
            runtime.KeepAlive(folder);runtime.KeepAlive(verb)
        }else if code=="IA_RECUPERACION_REGISTRO_ORIGINAL_VERIFICADA"{
            iaLog("[IA_RECUPERACION_REGISTRO_ORIGINAL_VERIFICADA] Registro o paquete original restaurado. Los archivos del traductor se conservaron.")
            iaSet(ui.status,"Inicio RPG original recuperado. Abre la copia del juego.")
            iaEnableWindow.Call(ui.install,0)
        }else if code=="IA_INSTALACION_COMPLETADA_VERIFICADA"{
            iaLog("[IA_INSTALACION_COMPLETADA_VERIFICADA] Listo para iniciar la copia del juego.")
            if pieces:=strings.SplitN(result,"|",2);len(pieces)==2{iaLog("[IA_VERSION_INSTALADA] "+pieces[1])}
            if newGame!=""{
                ui.gameFile=newGame;iaSet(ui.input,newGame)
                iaLog("[IA_VXACE_COPIA_LISTA] Abre Game.exe de la NUEVA carpeta indicada arriba. El origen permanece intacto.")
                iaSet(ui.status,"Copia nueva verificada. Abre el EXE indicado arriba y prueba F10.")
            }else if strings.HasPrefix(result,"IA_INSTALACION_COMPLETADA_VERIFICADA|"+xpLabBuild+" "){
                iaLog("[IA_RPGXP_INSTALACION_PRUEBA] Abre Game.exe y comprueba diálogos y elecciones. Si falla, cierra el juego y pulsa Recuperar inicio RPG. No requiere F10.")
                iaSet(ui.status,"XP instalado para prueba. Abre Game.exe. Compatibilidad real pendiente.")
            }else{iaSet(ui.status,"Instalación completa. Reinicia la copia del juego y prueba F10.")}
        }else{
            text:=iaFriendlyInstall(code)
            iaLog("["+code+"] "+text)
            iaSet(ui.status,text)
            iaEnableWindow.Call(ui.install,1)
        }
        return 0
    }
    result,_,_:=iaDefWindowProc.Call(hwnd,uintptr(message),wparam,lparam)
    return result
}
func runUI(){
    runtime.LockOSThread()
    defer runtime.UnlockOSThread()
    iaThemeInit()
    className:=iaUTF16("SERVIDOR_INDEPENDIENTE_RPG_V2")
    instance,_,_:=iaGetModule.Call(0)
    class:=iaWndClass{Size:uint32(unsafe.Sizeof(iaWndClass{})),
        WndProc:syscall.NewCallback(iaWinProc),Instance:instance,
        Background:iaThemeBrushSide,ClassName:className}
    reg,_,_:=iaRegClass.Call(uintptr(unsafe.Pointer(&class)))
    if reg==0{fmt.Fprintln(os.Stderr,"IA_VENTANA_NO_REGISTRADA");return}
    hwnd,_,_:=iaCreateWindow.Call(0,uintptr(unsafe.Pointer(className)),
        uintptr(unsafe.Pointer(iaUTF16("Servidor R44 — prueba JSON"))),iaWSOverlappedWindow|iaWSVisible,
        100,60,1050,760,0,0,instance,0)
    if hwnd==0{fmt.Fprintln(os.Stderr,"IA_NO_SE_PUEDE_ABRIR_VENTANA");return}
    ui:=&iaCurrentUI;ui.hwnd=hwnd
    ui.titleLabel=iaControl(hwnd,"STATIC","Servidor R44",0,30,20,360,55,0)
    ui.sectionLabel=iaControl(hwnd,"STATIC","RPG",0,233,123,250,40,0)
    for i,label:=range []string{"01","RPG","WEB","04","05","+"}{
        style:=uint32(0)
        if label!="RPG"&&label!="WEB"{style|=iaWSDisabled}
        control:=iaControl(hwnd,"BUTTON",label,style,20,127+i*70,169,54,300+i)
        if label=="WEB"{ui.webBtn=control}
    }
    ui.infoLabel=iaControl(hwnd,"STATIC","1. Selecciona el archivo EXE del juego (una copia cerrada):",0,230,187,780,34,0)
    ui.input=iaControl(hwnd,"EDIT","",iaWSBorder|iaESReadOnly,230,227,597,44,0)
    ui.browse=iaControl(hwnd,"BUTTON","EXE",0,843,226,169,46,iaCmdBrowse)
    ui.install=iaControl(hwnd,"BUTTON","2. INSTALAR TRADUCTOR",0,230,302,485,59,iaCmdInstall)
    ui.cloneBtn=iaControl(hwnd,"BUTTON","CREAR COPIA VX ACE",0,725,302,287,59,iaCmdClone)
    iaControl(hwnd,"STATIC","Estado de instalación:",0,230,379,760,31,0)
    ui.logs=iaControl(hwnd,"EDIT","",iaWSBorder|iaWSVScroll|iaESMultiline|
        iaESReadOnly|iaESAutoVScroll,230,414,782,236,0)
    ui.statusLabel=iaControl(hwnd,"STATIC","Listo para instalar el traductor.",0,230,664,773,39,0)
    ui.status=ui.statusLabel
    ui.copyBtn=iaControl(hwnd,"BUTTON","Copiar diagnóstico",0,230,710,264,36,iaCmdCopy)
    ui.recoverBtn=iaControl(hwnd,"BUTTON","Recuperar inicio RPG",0,501,710,274,36,iaCmdRecover)
    ui.closeBtn=iaControl(hwnd,"BUTTON","Cerrar",0,792,710,218,36,iaCmdClose)
    // The header STATIC is painted during CreateWindowExW, before titleLabel
    // receives its HWND. Force a second paint with the dark header brush.
    if ui.titleLabel!=0{iaInvalidateRect.Call(ui.titleLabel,0,1)}
    iaEnableWindow.Call(ui.install,0);iaEnableWindow.Call(ui.recoverBtn,0);iaEnableWindow.Call(ui.cloneBtn,0)
    iaLog("[IA_TRADUCTORA_LISTA] "+packageBuildID+". MV/MZ/VX Ace, XP experimental, SOLData y copia JSON experimental MV/NWBin. Botón WEB: seleccionar EXE original o index.html extraído y crear copia. Motor local OPUS.")
    iaShowWindow.Call(hwnd,5);iaUpdateWindow.Call(hwnd)
    var msg iaMsg
    for {
        success,_,_:=iaGetMessage.Call(uintptr(unsafe.Pointer(&msg)),0,0,0)
        if int32(success)<=0{break}
        // F10 is local to this UI message loop. No global hotkey,
        // hooks, process injection, or interception inside a game.
        if msg.Message==0x0100&&msg.WParam==0x79&&ui.jsonSummary!=""&&!ui.busy{
            if msg.LParam&(1<<30)==0{
                iaUser32.NewProc("MessageBoxW").Call(hwnd,uintptr(unsafe.Pointer(iaUTF16(ui.jsonSummary))),uintptr(unsafe.Pointer(iaUTF16("IA Traductora · Estado JSON"))),0x40)
            }
            continue
        }
        iaTranslateMessage.Call(uintptr(unsafe.Pointer(&msg)))
        iaDispatchMessage.Call(uintptr(unsafe.Pointer(&msg)))
    }
}
