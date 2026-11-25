//go:build windows

package main

// Ventana Win32 única de Servidor: un motor por hoja, con detección MV/MZ.
// No ejecuta instaladores secundarios y mantiene la interfaz respondiendo.
import(
    "fmt"
    "os"
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
    case "IA_DESTINO_CREACION_DENEGADA":
        return "Windows bloqueó la creación de IA Traductora. No se modificó el registro."
    case "IA_DESTINO_SIN_PERMISO":
        return "Windows no permite inspeccionar la carpeta de destino."
    case "IA_DESTINO_AJENO_NO_MODIFICADO","IA_DESTINO_EXISTENTE_NO_SOBRESCRITO":
        return "Ya hay una carpeta distinta en el destino. No se ha sobrescrito."
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
func iaChooseEXE(owner uintptr)(selected string,err error){
    defer func(){
        if recover()!=nil{
            selected=""
            err=errors.New("IA_SELECTOR_PANICO_RECUPERADO")
        }
    }()
    buffer:=make([]uint16,32768)
    filter:=iaExeFilterUTF16()
    title:=iaUTF16("Selecciona el Game.exe de una COPIA cerrada del videojuego")
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
    ui.busy=true
    iaEnableWindow.Call(ui.install,0)
    iaEnableWindow.Call(ui.browse,0)
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
    if ui.gameFile==""{
        iaLog("[IA_RECUPERACION_GAME_EXE_REQUERIDO] Selecciona Game.exe.")
        return
    }
    if ui.busy{return}
    ui.busy=true
    iaEnableWindow.Call(ui.install,0)
    iaEnableWindow.Call(ui.browse,0)
    iaEnableWindow.Call(ui.recoverBtn,0)
    iaSet(ui.status,"Comprobando respaldo original...")
    iaLog("[IA_RECUPERACION_INICIADA] Solo el registro original de esta copia RPG.")
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
        case iaCmdBrowse:
            if lparam!=ui.browse || ui.busy{return 0}
            file,err:=iaSelectFile(hwnd)
            if err!=nil{
                iaLog("[IA_SELECTOR_ERROR] "+err.Error())
                iaSet(ui.status,"No se pudo abrir el selector. Servidor sigue abierto.")
            }else if file!=""{
                if _,content,e:=detectGame(file);e!=nil{
                    iaLog("[IA_EXE_NO_COMPATIBLE] "+e.Error())
                    iaSet(ui.status,"Selecciona un EXE de una copia de RPG Maker MV o MZ.")
                }else{
                    ui.gameFile=file;iaSet(ui.input,file)
                    iaSet(ui.status,"Juego "+engineAt(content)+" seleccionado. Listo para instalar.")
                    iaLog("[IA_EXE_SELECCIONADO] Motor "+engineAt(content)+" verificado.")
                }
            }else{
                iaLog("[IA_SELECTOR_CANCELADO] Puedes volver a pulsar EXE.")
            }
        case iaCmdInstall:
            if lparam==ui.install {iaStartInstall()}
        case iaCmdRecover:
            if lparam==ui.recoverBtn {iaStartRecover()}
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
        ui.mu.Lock();result:=ui.result;ui.mu.Unlock()
        ui.busy=false
        iaEnableWindow.Call(ui.browse,1)
        iaEnableWindow.Call(ui.recoverBtn,1)
        code:=iaSafeInstallCode(result)
        if code=="IA_RECUPERACION_REGISTRO_ORIGINAL_VERIFICADA"{
            iaLog("[IA_RECUPERACION_REGISTRO_ORIGINAL_VERIFICADA] Registro original restaurado. Los archivos del traductor se conservaron.")
            iaSet(ui.status,"Registro RPG original recuperado. Abre la copia del juego.")
            iaEnableWindow.Call(ui.install,0)
        }else if code=="IA_INSTALACION_COMPLETADA_VERIFICADA"{
            iaLog("[IA_INSTALACION_COMPLETADA_VERIFICADA] Listo para iniciar la copia del juego.")
            if pieces:=strings.SplitN(result,"|",2);len(pieces)==2{iaLog("[IA_VERSION_INSTALADA] "+pieces[1])}
            iaSet(ui.status,"Instalación completa. Reinicia la copia del juego y prueba F10.")
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
        uintptr(unsafe.Pointer(iaUTF16("Servidor"))),iaWSOverlappedWindow|iaWSVisible,
        100,60,1050,760,0,0,instance,0)
    if hwnd==0{fmt.Fprintln(os.Stderr,"IA_NO_SE_PUEDE_ABRIR_VENTANA");return}
    ui:=&iaCurrentUI;ui.hwnd=hwnd
    ui.titleLabel=iaControl(hwnd,"STATIC","Servidor",0,30,20,360,55,0)
    ui.sectionLabel=iaControl(hwnd,"STATIC","RPG",0,233,123,250,40,0)
    for i,label:=range []string{"01","RPG","03","04","05","+"}{
        style:=uint32(0)
        if label!="RPG"{style|=iaWSDisabled}
        iaControl(hwnd,"BUTTON",label,style,20,127+i*70,169,54,300+i)
    }
    ui.infoLabel=iaControl(hwnd,"STATIC","1. Selecciona el archivo EXE del juego (una copia cerrada):",0,230,187,780,34,0)
    ui.input=iaControl(hwnd,"EDIT","",iaWSBorder|iaESReadOnly,230,227,597,44,0)
    ui.browse=iaControl(hwnd,"BUTTON","EXE",0,843,226,169,46,iaCmdBrowse)
    ui.install=iaControl(hwnd,"BUTTON","2. INSTALAR TRADUCTOR AUTOMÁTICO",0,230,302,782,59,iaCmdInstall)
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
    iaLog("[IA_TRADUCTORA_LISTA] RPG-MVMZ-R20-20261125. Selecciona una copia MV, MZ o MZ comprimida compatible. El motor es local.")
    iaShowWindow.Call(hwnd,5);iaUpdateWindow.Call(hwnd)
    var msg iaMsg
    for {
        success,_,_:=iaGetMessage.Call(uintptr(unsafe.Pointer(&msg)),0,0,0)
        if int32(success)<=0{break}
        iaTranslateMessage.Call(uintptr(unsafe.Pointer(&msg)))
        iaDispatchMessage.Call(uintptr(unsafe.Pointer(&msg)))
    }
}
