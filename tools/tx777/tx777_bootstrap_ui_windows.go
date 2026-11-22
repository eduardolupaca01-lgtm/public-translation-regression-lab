//go:build windows

package main

// TX777 native launcher: immediately opens a real UI without TX771's modal
// welcome, then keeps the progress and copyable error codes visible while the
// genuine V95 ZIP/model is checked on a separate goroutine. This NEVER
// changes Windows-wide environment variables or a game's save data.
import (
    "errors"
    "fmt"
    "path/filepath"
    "regexp"
    "reflect"
    "runtime"
    "strings"
    "sync/atomic"
    "syscall"
    "unsafe"
)

const (
    tx777CmdBrowse=701
    tx777CmdInstall=702
    tx777CmdCopy=703
    tx777CmdExit=704
    tx777WmCommand=0x0111
    tx777WmTimer=0x0113
    tx777WmClose=0x0010
    tx777WmDestroy=0x0002
    tx777WmSetFont=0x0030
    tx777WmCopy=0x0301
    tx777EmSetSel=0x00B1
    tx777WSVisible=0x10000000
    tx777WSChild=0x40000000
    tx777WSTabstop=0x00010000
    tx777WSBorder=0x00800000
    tx777WSVScroll=0x00200000
    tx777ESMultiline=0x0004
    tx777ESReadOnly=0x0800
    tx777ESAutoVScroll=0x0040
    tx777WSOverlapped=0x00CF0000
)
type tx777WndClass struct {
    Size uint32
    Style uint32
    Procedure uintptr
    ClsExtra int32
    WndExtra int32
    Module uintptr
    Icon uintptr
    Cursor uintptr
    Background uintptr
    Menu *uint16
    Name *uint16
    IconSmall uintptr
}
type tx777Msg struct {
    Hwnd uintptr
    Message uint32
    Wparam uintptr
    Lparam uintptr
    Time uint32
    X int32
    Y int32
    Private uint32
}
type tx777Selection struct{game string;ok bool;err error}
type tx777Event struct{code,desc string;final bool;failed bool}
type tx777State struct {
    hwnd,selectedField,statusField,browse,install,copyButton,exit uintptr
    game string
    text string
    running bool
    finished bool
    selectionSent bool
}
var (
    tx777User32=syscall.NewLazyDLL("user32.dll")
    tx777Gdi32=syscall.NewLazyDLL("gdi32.dll")
    tx777Register=tx777User32.NewProc("RegisterClassExW")
    tx777Create=tx777User32.NewProc("CreateWindowExW")
    tx777Send=tx777User32.NewProc("SendMessageW")
    tx777SetText=tx777User32.NewProc("SetWindowTextW")
    tx777Enable=tx777User32.NewProc("EnableWindow")
    tx777Show=tx777User32.NewProc("ShowWindow")
    tx777Update=tx777User32.NewProc("UpdateWindow")
    tx777Def=tx777User32.NewProc("DefWindowProcW")
    tx777Destroy=tx777User32.NewProc("DestroyWindow")
    tx777PostQuit=tx777User32.NewProc("PostQuitMessage")
    tx777Post=tx777User32.NewProc("PostMessageW")
    tx777SetTimer=tx777User32.NewProc("SetTimer")
    tx777KillTimer=tx777User32.NewProc("KillTimer")
    tx777GetMsg=tx777User32.NewProc("GetMessageW")
    tx777Translate=tx777User32.NewProc("TranslateMessage")
    tx777Dispatch=tx777User32.NewProc("DispatchMessageW")
    tx777GetModule=syscall.NewLazyDLL("kernel32.dll").NewProc("GetModuleHandleW")
    tx777Font=tx777Gdi32.NewProc("GetStockObject")
    tx777Selections chan tx777Selection
    tx777Messages chan tx777Event
    tx777Closed chan struct{}
    tx777WasVisible atomic.Bool
    tx777Screen *tx777State
    tx777StageCode=regexp.MustCompile(`TX[0-9]{3}_[A-Z0-9_]{3,90}`)
)
func tx777PlainWelcome()(bool,error){return true,nil}

// Own all Windows GUI calls on one locked OS thread. Model operations run
// in the original run() goroutine while the native UI continues pumping.
func tx777SelectGameWithPanel()(string,bool,error){
    tx777Selections=make(chan tx777Selection,1)
    tx777Messages=make(chan tx777Event,64)
    tx777Closed=make(chan struct{})
    tx777WasVisible.Store(false)
    go tx777WindowThread()
    response:=<-tx777Selections
    return response.game,response.ok,response.err
}
func tx777Stage(code,desc string){
    if tx777Messages==nil{return}
    select{case tx777Messages<-tx777Event{code:code,desc:desc}:default:}
}
func tx777Finalize(err error)bool{
    if tx777Messages==nil||tx777Closed==nil{return false}
    select{case <-tx777Closed:return tx777WasVisible.Load();default:}
    event:=tx777Event{final:true}
    if err!=nil {
        event.failed=true
        event.code="TX777_ERROR_NO_CLASIFICADO"
        if x:=tx777StageCode.FindString(strings.ToUpper(err.Error()));x!=""{event.code=x}
        event.desc="La preparación se detuvo. No borres modelos, caché ni copias anteriores; copia este diagnóstico. Los detalles privados se han ocultado."
    }else{
        event.code="TX777_INTERFAZ_ABIERTA"
        event.desc="El instalador principal de V95 se abrió. El progreso restante se verá en su panel de diagnóstico."
    }
    select{
    case tx777Messages<-event:
    case <-tx777Closed:
        return tx777WasVisible.Load()
    }
    <-tx777Closed // error remains visible until the owner closes the panel
    return tx777WasVisible.Load()
}
func tx777UTF16(s string)*uint16{
    p,_:=syscall.UTF16PtrFromString(s)
    return p
}
func tx777Control(parent uintptr,class,label string,style uintptr,x,y,w,h int32,id uintptr)uintptr{
    c,t:=tx777UTF16(class),tx777UTF16(label)
    hwnd,_,_:=tx777Create.Call(0,uintptr(unsafe.Pointer(c)),uintptr(unsafe.Pointer(t)),
        style|tx777WSChild|tx777WSVisible,uintptr(x),uintptr(y),uintptr(w),uintptr(h),
        parent,id,0,0)
    runtime.KeepAlive(c);runtime.KeepAlive(t)
    if hwnd!=0{
        f,_,_:=tx777Font.Call(17) // DEFAULT_GUI_FONT
        if f!=0{tx777Send.Call(hwnd,tx777WmSetFont,f,1)}
    }
    return hwnd
}
func tx777Set(hwnd uintptr,value string){
    if hwnd==0{return}
    p:=tx777UTF16(value)
    tx777SetText.Call(hwnd,uintptr(unsafe.Pointer(p)))
    runtime.KeepAlive(p)
}
func tx777Add(code,desc string){
    state:=tx777Screen
    if state==nil{return}
    if code==""{code="TX777_EVENTO"}
    desc=strings.NewReplacer("\r"," ","\n"," ").Replace(desc)
    if len(desc)>260{desc=desc[:260]}
    line:="\r\n["+code+"] "+desc
    if len(state.text)+len(line)>30000 {
        pieces:=strings.Split(state.text,"\r\n")
        for len(pieces)>2 && len(strings.Join(pieces,"\r\n"))+len(line)>28000 {
            pieces=pieces[1:]
        }
        state.text="[TX777_HISTORIAL_RECORTADO] Se conservan los eventos recientes.\r\n"+strings.Join(pieces,"\r\n")
    }
    state.text+=line
    tx777Set(state.statusField,state.text)
    if state.statusField!=0{
        tx777Send.Call(state.statusField,tx777EmSetSel,^uintptr(0),^uintptr(0))
    }
}
func tx777EnableActions(enable bool){
    state:=tx777Screen
    if state==nil{return}
    v:=uintptr(0);if enable{v=1}
    for _,hwnd:=range []uintptr{state.browse,state.install}{
        if hwnd!=0{tx777Enable.Call(hwnd,v)}
    }
}
func tx777SendChoice(choice tx777Selection){
    state:=tx777Screen
    if state==nil||state.selectionSent{return}
    state.selectionSent=true
    select{case tx777Selections<-choice:default:}
}
func tx777WndProc(hwnd,msg,wparam,lparam uintptr)uintptr{
    st:=tx777Screen
    switch msg{
    case tx777WmCommand:
        if st==nil{return 0}
        switch wparam&0xffff{
        case tx777CmdBrowse:
            if st.running{return 0}
            path,ok,err:=tx771ChooseGameEXE()
            if err!=nil{
                tx777Add("TX777_SELECTOR_WINDOWS", "Windows no pudo abrir el selector de archivos. Cierra el juego y vuelve a intentarlo.")
            }else if ok{
                if _,validation:=tx771GameRoot(path);validation!=nil{
                    tx777Add("TX777_JUEGO_NO_COMPATIBLE","Se rechazó la selección: esta versión instala la IA original solo en RPG Maker MV/MZ.")
                }else{
                    st.game=path
                    tx777Set(st.selectedField,path)
                    tx777Add("TX777_JUEGO_VALIDADO","Carpeta RPG Maker MV/MZ identificada. Pulsa PREPARAR E INSTALAR para continuar.")
                }
            }
            return 0
        case tx777CmdInstall:
            if st.running{return 0}
            if st.game==""{tx777Add("TX777_SELECCION_PENDIENTE","Primero selecciona el Game.exe de una copia del videojuego.");return 0}
            if _,err:=tx771GameRoot(st.game);err!=nil{
                tx777Add("TX777_JUEGO_CAMBIADO","Los archivos del juego cambiaron antes de instalar. Selecciona otra copia.")
                return 0
            }
            st.running=true
            tx777EnableActions(false)
            tx777Add("TX777_INICIANDO","Preparando IA íntegramente en la unidad del juego. La ventana seguirá respondiendo.")
            tx777SendChoice(tx777Selection{game:st.game,ok:true})
            return 0
        case tx777CmdCopy:
            if st.statusField!=0{
                tx777Send.Call(st.statusField,tx777EmSetSel,0,^uintptr(0))
                tx777Send.Call(st.statusField,tx777WmCopy,0,0)
                tx777Send.Call(st.statusField,tx777EmSetSel,^uintptr(0),^uintptr(0))
            }
            return 0
        case tx777CmdExit:
            if !st.running||st.finished{tx777Destroy.Call(hwnd)}
            return 0
        }
    case tx777WmTimer:
        if st==nil{return 0}
        for i:=0;i<32;i++{
            select{
            case e:=<-tx777Messages:
                tx777Add(e.code,e.desc)
                if e.final{
                    st.finished=true
                    st.running=false
                    if !e.failed{
                        tx777Destroy.Call(hwnd)
                        return 0
                    }
                    tx777EnableActions(false)
                }
            default:return 0
            }
        }
        return 0
    case tx777WmClose:
        if st!=nil&&st.running&&!st.finished {
            tx777Add("TX777_CIERRE_PROTEGIDO","La preparación sigue activa; cerrar ahora podría interrumpir el respaldo.")
            return 0
        }
        tx777Destroy.Call(hwnd);return 0
    case tx777WmDestroy:
        tx777KillTimer.Call(hwnd,777)
        tx777SendChoice(tx777Selection{ok:false})
        tx777PostQuit.Call(0)
        return 0
    }
    v,_,_:=tx777Def.Call(hwnd,msg,wparam,lparam)
    return v
}
func tx777WindowThread(){
    runtime.LockOSThread()
    defer runtime.UnlockOSThread()
    defer close(tx777Closed)
    tx777Screen=&tx777State{}
    name:=tx777UTF16("TENSHIXGAME_TX777_GAME_LOCAL_STARTUP")
    cb:=syscall.NewCallback(tx777WndProc)
    h,_,_:=tx777GetModule.Call(0)
    klass:=tx777WndClass{Size:uint32(unsafe.Sizeof(tx777WndClass{})),
        Procedure:cb,Module:h,Background:6,Name:name}
    reg,_,_:=tx777Register.Call(uintptr(unsafe.Pointer(&klass)))
    if reg==0{tx777SendChoice(tx777Selection{err:errors.New("TX777_WINDOWS_CLASS_REGISTRATION_FAILED")});return}
    title:=tx777UTF16("TENSHIXGAME — Instalador portátil de IA")
    hwnd,_,_:=tx777Create.Call(0,uintptr(unsafe.Pointer(name)),uintptr(unsafe.Pointer(title)),
        tx777WSOverlapped|tx777WSVisible,120,80,740,640,0,0,h,0)
    runtime.KeepAlive(name);runtime.KeepAlive(title)
    if hwnd==0{tx777SendChoice(tx777Selection{err:errors.New("TX777_WINDOWS_LAUNCHER_CREATION_FAILED")});return}
    tx777WasVisible.Store(true)
    st:=tx777Screen
    st.hwnd=hwnd
    tx777Control(hwnd,"STATIC","TENSHIXGAME · Traductor de juegos con IA local",0,23,20,675,30,0)
    tx777Control(hwnd,"STATIC","Motor de esta versión: RPG Maker MV / MZ",0,25,65,650,25,0)
    tx777Control(hwnd,"STATIC","1. Selecciona el Game.exe de una COPIA del juego cerrado:",0,25,104,660,26,0)
    st.selectedField=tx777Control(hwnd,"EDIT","",tx777WSBorder|tx777ESReadOnly,25,143,507,34,0)
    st.browse=tx777Control(hwnd,"BUTTON","Seleccionar EXE",tx777WSTabstop,545,140,155,40,tx777CmdBrowse)
    st.install=tx777Control(hwnd,"BUTTON","2. PREPARAR E INSTALAR LA IA",tx777WSTabstop,
        25,205,675,52,tx777CmdInstall)
    tx777Control(hwnd,"STATIC","Estado de preparación y diagnóstico (copia los códigos si hay errores):",
        0,25,279,670,27,0)
    st.statusField=tx777Control(hwnd,"EDIT","",
        tx777WSBorder|tx777WSVScroll|tx777ESMultiline|tx777ESReadOnly|tx777ESAutoVScroll,
        25,312,675,201,0)
    st.copyButton=tx777Control(hwnd,"BUTTON","COPIAR DIAGNÓSTICO",tx777WSTabstop,
        25,531,440,38,tx777CmdCopy)
    st.exit=tx777Control(hwnd,"BUTTON","Cerrar",tx777WSTabstop,477,531,223,38,tx777CmdExit)
    tx777Add("TX777_LISTO","Selecciona una copia RPG Maker MV/MZ. No se ha leído ni instalado el modelo.")
    tx777Show.Call(hwnd,5)
    tx777Update.Call(hwnd)
    tx777SetTimer.Call(hwnd,777,250,0)
    var msg tx777Msg
    for{
        result,_,_:=tx777GetMsg.Call(uintptr(unsafe.Pointer(&msg)),0,0,0)
        if result==0||result==^uintptr(0){break}
        tx777Translate.Call(uintptr(unsafe.Pointer(&msg)))
        tx777Dispatch.Call(uintptr(unsafe.Pointer(&msg)))
    }
    // Child can continue only if a human pressed Install; closing a dialog
    // NEVER silently triggers the 650MB model extraction.
}
func tx777CheckOriginalNoWelcome()error{
    // Compare function pointers rather than an always-false function-vs-nil test.
    if reflect.ValueOf(tx771WelcomeBeforePayload).Pointer()!=reflect.ValueOf(tx777PlainWelcome).Pointer(){
        return fmt.Errorf("TX777_LEGACY_V95_MODAL_WELCOME_RESTORED")
    }
    return nil
}
func tx777StatusCategory(err error)string{
    if err==nil{return "TX777_COMPLETADO"}
    if code:=tx777StageCode.FindString(strings.ToUpper(err.Error()));code!=""{return code}
    return "TX777_ERROR_NO_CLASIFICADO"
}
func tx777GameRootForTest(game string)(string,error){
    return tx771GameRoot(filepath.Clean(game))
}
