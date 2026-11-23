//go:build windows

package main

// Ventana Win32 única de Servidor: un motor por hoja, por ahora sólo MV.
// No ejecuta instaladores secundarios y mantiene la interfaz respondiendo.
import(
    "fmt"
    "os"
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
    iaCmdBrowse=100
    iaCmdInstall=101
    iaCmdClose=102
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
    install uintptr
    status uintptr
    logs uintptr
    logText string
    mu sync.Mutex
    result string
}
var iaCurrentUI iaUI
func iaUTF16(s string)*uint16{return syscall.StringToUTF16Ptr(s)}
func iaControl(parent uintptr,klass,title string,style uint32,x,y,width,height,id int)uintptr{
    win,_,_:=iaCreateWindow.Call(0,uintptr(unsafe.Pointer(iaUTF16(klass))),
        uintptr(unsafe.Pointer(iaUTF16(title))),uintptr(style)|iaWSVisible|iaWSChild,
        uintptr(x),uintptr(y),uintptr(width),uintptr(height),parent,uintptr(id),0,0)
    return win
}
func iaSet(hwnd uintptr,text string){
    iaSetWindowText.Call(hwnd,uintptr(unsafe.Pointer(iaUTF16(text))))
}
func iaLog(line string){
    if iaCurrentUI.logText!=""{iaCurrentUI.logText+="\r\n"}
    iaCurrentUI.logText+=line
    iaSet(iaCurrentUI.logs,iaCurrentUI.logText)
}
func iaChooseEXE(owner uintptr)(string,error){
    buffer:=make([]uint16,32768)
    filter:=syscall.StringToUTF16("Juegos Windows (*.exe)\x00*.exe\x00\x00")
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
    iaEnableWindow.Call(ui.install,0)
    iaSet(ui.status,"Preparando IA Traductora...")
    iaLog("[IA_INICIANDO] Verificando el paquete propio y los modelos.")
    game:=ui.gameFile
    go func(){
        info:="IA_ERROR_NO_CLASIFICADO"
        executable,e:=os.Executable()
        if e!=nil{info="IA_NO_SE_PUEDE_LEER_SERVIDOR"}else{
            pkg,err:=readPackage(executable)
            if err!=nil{info=err.Error()}else{
                defer pkg.Close()
                err=Install(game,pkg)
                if err!=nil{info=err.Error()}else{info="IA_INSTALACION_COMPLETADA_VERIFICADA"}
            }
        }
        ui.mu.Lock();ui.result=info;ui.mu.Unlock()
        iaPostMessage.Call(ui.hwnd,iaWMAppDone,0,0)
    }()
}
func iaWinProc(hwnd uintptr,message uint32,wparam,lparam uintptr)uintptr{
    ui:=&iaCurrentUI
    switch message {
    case iaWMClose:
        iaDestroyWindow.Call(hwnd);return 0
    case iaWMDestroy:
        iaPostQuitMessage.Call(0);return 0
    case iaWMCommand:
        switch int(wparam&0xFFFF){
        case iaCmdBrowse:
            file,err:=iaChooseEXE(hwnd)
            if err!=nil{iaLog("[IA_SELECTOR_ERROR] "+err.Error())}else if file!=""{
                ui.gameFile=file;iaSet(ui.input,file)
                iaSet(ui.status,"Listo para instalar el traductor.")
                iaLog("[IA_EXE_SELECCIONADO] Se usará una copia cerrada del juego.")
            }
        case iaCmdInstall:
            iaStartInstall()
        case iaCmdClose:
            iaDestroyWindow.Call(hwnd)
        }
        return 0
    case iaWMAppDone:
        ui.mu.Lock();result:=ui.result;ui.mu.Unlock()
        iaLog("["+result+"]")
        if strings.HasPrefix(result,"IA_INSTALACION_COMPLETADA"){
            iaSet(ui.status,"Instalación finalizada. Reinicia el juego para probar.")
        }else{
            iaSet(ui.status,"No se completó la instalación: "+result)
            iaEnableWindow.Call(ui.install,1)
        }
        return 0
    }
    result,_,_:=iaDefWindowProc.Call(hwnd,uintptr(message),wparam,lparam)
    return result
}
func runUI(){
    className:=iaUTF16("SERVIDOR_INDEPENDIENTE_RPG_V2")
    instance,_,_:=iaGetModule.Call(0)
    class:=iaWndClass{Size:uint32(unsafe.Sizeof(iaWndClass{})),
        WndProc:syscall.NewCallback(iaWinProc),Instance:instance,
        Background:uintptr(16),ClassName:className}
    reg,_,_:=iaRegClass.Call(uintptr(unsafe.Pointer(&class)))
    if reg==0{fmt.Fprintln(os.Stderr,"IA_VENTANA_NO_REGISTRADA");return}
    hwnd,_,_:=iaCreateWindow.Call(0,uintptr(unsafe.Pointer(className)),
        uintptr(unsafe.Pointer(iaUTF16("Servidor"))),iaWSOverlappedWindow|iaWSVisible,
        100,60,1050,760,0,0,instance,0)
    if hwnd==0{fmt.Fprintln(os.Stderr,"IA_NO_SE_PUEDE_ABRIR_VENTANA");return}
    ui:=&iaCurrentUI;ui.hwnd=hwnd
    iaControl(hwnd,"STATIC","Servidor",0,21,20,230,46,0)
    iaControl(hwnd,"STATIC","RPG",0,218,75,180,37,0)
    for i,label:=range []string{"01","RPG","03","04","05","+"}{
        style:=uint32(0)
        if label!="RPG"{style|=iaWSDisabled}
        iaControl(hwnd,"BUTTON",label,style,20,125+i*69,169,52,300+i)
    }
    iaControl(hwnd,"STATIC","1. Selecciona el archivo EXE de una COPIA del juego cerrado:",0,220,132,740,33,0)
    ui.input=iaControl(hwnd,"EDIT","",iaWSBorder|iaESReadOnly,218,169,604,42,0)
    iaControl(hwnd,"BUTTON","EXE",0,841,169,171,43,iaCmdBrowse)
    ui.install=iaControl(hwnd,"BUTTON","2. INSTALAR TRADUCTOR AUTOMÁTICO",0,219,243,793,59,iaCmdInstall)
    iaControl(hwnd,"STATIC","Estado de instalación:",0,219,333,740,30,0)
    ui.logs=iaControl(hwnd,"EDIT","",iaWSBorder|iaWSVScroll|iaESMultiline|
        iaESReadOnly|iaESAutoVScroll,219,370,793,246,0)
    ui.status=iaControl(hwnd,"STATIC","Listo para instalar el traductor.",0,219,627,790,38,0)
    iaControl(hwnd,"BUTTON","Cerrar",0,740,679,270,42,iaCmdClose)
    iaLog("[IA_TRADUCTORA_LISTA] Selecciona una copia MV. El motor es local y propio.")
    iaShowWindow.Call(hwnd,5);iaUpdateWindow.Call(hwnd)
    var msg iaMsg
    for {
        success,_,_:=iaGetMessage.Call(uintptr(unsafe.Pointer(&msg)),0,0,0)
        if int32(success)<=0{break}
        iaTranslateMessage.Call(uintptr(unsafe.Pointer(&msg)))
        iaDispatchMessage.Call(uintptr(unsafe.Pointer(&msg)))
    }
}
