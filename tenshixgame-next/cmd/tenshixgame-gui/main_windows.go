//go:build windows

package main

// TENSHIXGAME - Windows-first selector and read-only exact engine detector.
// This is NOT the V95 translator installer. It NEVER starts a game or model.
import (
    "fmt"
    "runtime"
    "strings"
    "syscall"
    "unsafe"

    "github.com/eduardolupaca01-lgtm/public-translation-regression-lab/tenshixgame-next/internal/engine"
)
const (
    wsVisible=0x10000000
    wsChild=0x40000000
    wsTop=0x00CF0000
    wsBorder=0x00800000
    wsTabstop=0x00010000
    wsVscroll=0x00200000
    esMulti=0x0004
    esReadOnly=0x0800
    esAutoVScroll=0x0040
    cbsDropDownList=0x0003
    wmCreate=0x0001
    wmCommand=0x0111
    wmDestroy=0x0002
    wmClose=0x0010
    wmSetFont=0x0030
    wmResult=0x8000+31
    cbAddString=0x0143
    cbGetCurSel=0x0147
    cbSetCurSel=0x014E
    defaultGUIFont=17
    cmdBrowseFile=301
    cmdBrowseFolder=302
    cmdInspect=303
)
type winPoint struct{X,Y int32}
type winMessage struct{
    HWnd uintptr
    Message uint32
    WParam uintptr
    LParam uintptr
    Time uint32
    Pt winPoint
    Private uint32
}
type winClassEx struct{
    Size uint32
    Style uint32
    Callback uintptr
    ClsExtra int32
    WndExtra int32
    Module uintptr
    Icon uintptr
    Cursor uintptr
    Background uintptr
    MenuName *uint16
    ClassName *uint16
    SmallIcon uintptr
}
type winOpenFile struct{
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
    DefaultExt *uint16
    CustomData uintptr
    Hook uintptr
    TemplateName *uint16
    Reserved uintptr
    ReservedInt uint32
    FlagsEx uint32
}
type winBrowseInfo struct{
    Owner uintptr
    Root uintptr
    DisplayName *uint16
    Title *uint16
    Flags uint32
    Callback uintptr
    UserData uintptr
    Image int32
}
var (
    user32=syscall.NewLazyDLL("user32.dll")
    kernel32=syscall.NewLazyDLL("kernel32.dll")
    shell32=syscall.NewLazyDLL("shell32.dll")
    ole32=syscall.NewLazyDLL("ole32.dll")
    comdlg=syscall.NewLazyDLL("comdlg32.dll")
    pRegister=user32.NewProc("RegisterClassExW")
    pCreate=user32.NewProc("CreateWindowExW")
    pShow=user32.NewProc("ShowWindow")
    pUpdate=user32.NewProc("UpdateWindow")
    pSend=user32.NewProc("SendMessageW")
    pSet=user32.NewProc("SetWindowTextW")
    pGet=user32.NewProc("GetWindowTextW")
    pEnable=user32.NewProc("EnableWindow")
    pPost=user32.NewProc("PostMessageW")
    pDestroy=user32.NewProc("DestroyWindow")
    pDef=user32.NewProc("DefWindowProcW")
    pQuit=user32.NewProc("PostQuitMessage")
    pGetMessage=user32.NewProc("GetMessageW")
    pTranslate=user32.NewProc("TranslateMessage")
    pDispatch=user32.NewProc("DispatchMessageW")
    pGetObject=syscall.NewLazyDLL("gdi32.dll").NewProc("GetStockObject")
    pModule=kernel32.NewProc("GetModuleHandleW")
    pLoadCursor=user32.NewProc("LoadCursorW")
    cbwnd uintptr
    wMain uintptr
    wSelection uintptr
    wFamilies uintptr
    wStatus uintptr
    wInspect uintptr
    normalFont uintptr
    inspectBusy bool
    resultQueue=make(chan inspectOutcome,1)
)
type inspectOutcome struct{
    result engine.Result
    err error
}
func ptr(s string)uintptr{
    p,e:=syscall.UTF16PtrFromString(s)
    if e!=nil{return 0}
    return uintptr(unsafe.Pointer(p))
}
func ctrl(parent uintptr, class,title string,style uintptr,x,y,w,h int32,id uintptr)uintptr{
    hwnd,_,_:=pCreate.Call(0,ptr(class),ptr(title),style|wsVisible|wsChild,
        uintptr(x),uintptr(y),uintptr(w),uintptr(h),parent,id,0,0)
    if hwnd!=0&&normalFont!=0{pSend.Call(hwnd,wmSetFont,normalFont,1)}
    return hwnd
}
func setText(handle uintptr,s string){if handle!=0{pSet.Call(handle,ptr(s))}}
func getText(handle uintptr)string{
    buf:=make([]uint16,32768)
    n,_,_:=pGet.Call(handle,uintptr(unsafe.Pointer(&buf[0])),uintptr(len(buf)))
    runtime.KeepAlive(buf)
    if n>=uintptr(len(buf)){n=uintptr(len(buf)-1)}
    return syscall.UTF16ToString(buf[:int(n)])
}
func pickEXE(owner uintptr)(string,error){
    buffer:=make([]uint16,32768)
    filter:=syscall.StringToUTF16("Juego / EXE / JAR / SWF\x00*.exe;*.jar;*.swf\x00Todos\x00*.*\x00\x00")
    title,err:=syscall.UTF16PtrFromString("Seleccionar ejecutable de una COPIA del juego")
    if err!=nil{return "",err}
    dlg:=winOpenFile{
        Size:uint32(unsafe.Sizeof(winOpenFile{})),Owner:owner,
        Filter:&filter[0],File:&buffer[0],MaxFile:uint32(len(buffer)),
        Title:title,Flags:0x00001000|0x00000800|0x00080000,
    }
    ok,_,_:=comdlg.NewProc("GetOpenFileNameW").Call(uintptr(unsafe.Pointer(&dlg)))
    runtime.KeepAlive(dlg);runtime.KeepAlive(title)
    runtime.KeepAlive(filter);runtime.KeepAlive(buffer)
    if ok==0{
        code,_,_:=comdlg.NewProc("CommDlgExtendedError").Call()
        if code==0{return "",nil}
        return "",fmt.Errorf("error de selector de archivos 0x%X",code)
    }
    return syscall.UTF16ToString(buffer),nil
}
func pickFolder(owner uintptr)(string,error){
    var display [260]uint16
    title,err:=syscall.UTF16PtrFromString("Seleccionar una COPIA del juego")
    if err!=nil{return "",err}
    bi:=winBrowseInfo{Owner:owner,DisplayName:&display[0],Title:title,Flags:0x1|0x10|0x40}
    pidl,_,_:=shell32.NewProc("SHBrowseForFolderW").Call(uintptr(unsafe.Pointer(&bi)))
    runtime.KeepAlive(bi);runtime.KeepAlive(title);runtime.KeepAlive(display)
    if pidl==0{return "",nil}
    defer ole32.NewProc("CoTaskMemFree").Call(pidl)
    var b [32768]uint16
    okay,_,_:=shell32.NewProc("SHGetPathFromIDListW").Call(pidl,uintptr(unsafe.Pointer(&b[0])))
    runtime.KeepAlive(b)
    if okay==0{return "",fmt.Errorf("Windows no pudo resolver la carpeta")}
    return syscall.UTF16ToString(b[:]),nil
}
func formatResult(item engine.Result)string{
    var b strings.Builder
    fmt.Fprintf(&b,"Familia seleccionada: %s\r\n",item.FamilyName)
    fmt.Fprintf(&b,"Estado de inspección: %s\r\n",item.Status)
    if item.DetectedEngine!=""{
        fmt.Fprintf(&b,"Motor detectado: %s\r\n",item.DetectedEngine)
        fmt.Fprintf(&b,"Versión: %s\r\n",item.EngineVersion)
    }
    if len(item.Evidence)>0{
        b.WriteString("Firmas encontradas:\r\n")
        for _,x:=range item.Evidence{fmt.Fprintf(&b,"  • %s\r\n",x)}
    }
    fmt.Fprintf(&b,"\r\n%s\r\n",item.Explanation)
    b.WriteString("\r\nEste diagnóstico NO instala la IA ni modifica archivos.\r\n")
    return b.String()
}
func inspectNow(hwnd uintptr){
    if inspectBusy{return}
    index,_,_:=pSend.Call(wFamilies,cbGetCurSel,0,0)
    families:=engine.CloneCatalog()
    if index>=uintptr(len(families)){
        setText(wStatus,"Selecciona una familia para inspeccionar.")
        return
    }
    path:=strings.TrimSpace(getText(wSelection))
    if path==""{setText(wStatus,"Selecciona un Game.exe o una carpeta de COPIA antes de analizar.");return}
    inspectBusy=true
    pEnable.Call(wInspect,0)
    setText(wStatus,"Leyendo firmas locales de motor sin modificar archivos del juego...")
    selected:=families[index].ID
    go func(){
        res,err:=engine.Inspect(path,selected)
        resultQueue<-inspectOutcome{result:res,err:err}
        pPost.Call(hwnd,wmResult,0,0)
    }()
}
func wndProc(hwnd uintptr,message uint32,wparam,lparam uintptr)uintptr{
    switch message {
    case wmCommand:
        switch uint16(wparam&0xffff){
        case cmdBrowseFile:
            if inspectBusy{return 0}
            value,err:=pickEXE(hwnd)
            if err!=nil{setText(wStatus,"Selector: "+err.Error())}else if value!=""{setText(wSelection,value)}
            return 0
        case cmdBrowseFolder:
            if inspectBusy{return 0}
            value,err:=pickFolder(hwnd)
            if err!=nil{setText(wStatus,"Carpeta: "+err.Error())}else if value!=""{setText(wSelection,value)}
            return 0
        case cmdInspect:
            inspectNow(hwnd)
            return 0
        }
    case wmResult:
        select{
        case completed:=<-resultQueue:
            inspectBusy=false
            pEnable.Call(wInspect,1)
            if completed.err!=nil{setText(wStatus,"INSPECCIÓN BLOQUEADA: "+completed.err.Error())}else{
                setText(wStatus,formatResult(completed.result))
            }
        default:
        }
        return 0
    case wmClose:
        pDestroy.Call(hwnd)
        return 0
    case wmDestroy:
        pQuit.Call(0)
        return 0
    }
    value,_,_:=pDef.Call(hwnd,uintptr(message),wparam,lparam)
    return value
}
func main(){
    runtime.LockOSThread()
    defer runtime.UnlockOSThread()
    module,_,_:=pModule.Call(0)
    normalFont,_,_=pGetObject.Call(defaultGUIFont)
    cbwnd=syscall.NewCallback(wndProc)
    clsName,err:=syscall.UTF16PtrFromString("TENSHIXGAME_NEXT_DETECT_WINDOW")
    if err!=nil{return}
    cursor,_,_:=pLoadCursor.Call(0,32512)
    wc:=winClassEx{
        Size:uint32(unsafe.Sizeof(winClassEx{})),Callback:cbwnd,Module:module,
        Cursor:cursor,Background:uintptr(6),ClassName:clsName,
    }
    if atom,_,_:=pRegister.Call(uintptr(unsafe.Pointer(&wc)));atom==0{return}
    runtime.KeepAlive(wc);runtime.KeepAlive(clsName)
    hwnd,_,_:=pCreate.Call(0,uintptr(unsafe.Pointer(clsName)),
        ptr("TENSHIXGAME — Catálogo y detector de motores"),
        wsTop,140,100,860,590,0,0,module,0)
    if hwnd==0{return}
    wMain=hwnd
    ctrl(hwnd,"STATIC","TENSHIXGAME — Identificación automática del motor",0,24,17,770,29,0)
    ctrl(hwnd,"STATIC","Primero elige la familia; después selecciona Game.exe o la carpeta. Nunca asumimos que RPG significa MV.",0,24,50,780,31,0)
    ctrl(hwnd,"STATIC","01  FAMILIA DEL JUEGO",0,24,95,350,24,0)
    wFamilies=ctrl(hwnd,"COMBOBOX","",wsVscroll|wsTabstop|cbsDropDownList,24,124,795,260,100)
    for _,f:=range engine.Families{
        label:=f.Name
        if f.ID=="rpg-maker"{label="RPG Maker — 2000/2003, XP, VX, VX Ace, MV, MZ y otras generaciones"}
        pSend.Call(wFamilies,cbAddString,0,ptr(label))
    }
    pSend.Call(wFamilies,cbSetCurSel,0,0)
    ctrl(hwnd,"STATIC","02  COPIA DEL VIDEOJUEGO",0,24,178,360,24,0)
    wSelection=ctrl(hwnd,"EDIT","",wsBorder|wsTabstop|0x0080,24,205,493,34,101)
    ctrl(hwnd,"BUTTON","Seleccionar EXE",wsTabstop,527,202,142,40,cmdBrowseFile)
    ctrl(hwnd,"BUTTON","Carpeta",wsTabstop,681,202,138,40,cmdBrowseFolder)
    wInspect=ctrl(hwnd,"BUTTON","03  ANALIZAR MOTOR Y VERSIÓN (SOLO LECTURA)",wsTabstop,24,270,795,52,cmdInspect)
    ctrl(hwnd,"STATIC","RESULTADO Y SEGURIDAD DE COMPATIBILIDAD",0,24,343,660,23,0)
    wStatus=ctrl(hwnd,"EDIT","Selecciona una familia y el juego. Se mostrarán el motor, la versión y las firmas encontradas.",
        wsBorder|wsVscroll|esMulti|esAutoVScroll|esReadOnly,24,372,795,143,102)
    ctrl(hwnd,"STATIC","Instalación de IA deshabilitada hasta aprobar el adaptador específico. No se tocan tus partidas.",0,24,522,795,24,0)
    pShow.Call(hwnd,5);pUpdate.Call(hwnd)
    var msg winMessage
    for {
        result,_,_:=pGetMessage.Call(uintptr(unsafe.Pointer(&msg)),0,0,0)
        if result==0||result==^uintptr(0){break}
        pTranslate.Call(uintptr(unsafe.Pointer(&msg)))
        pDispatch.Call(uintptr(unsafe.Pointer(&msg)))
    }
}
