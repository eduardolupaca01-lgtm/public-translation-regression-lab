//go:build windows

package main

// Win32 visual layer for Servidor RPG. No WebView, no second window, no app
// credentials or neural engine paths are used by the rendering code.
import (
    "runtime"
    "syscall"
    "unsafe"
)

const (
    iaWMSetFont=0x0030
    iaTransparent=1
    iaDTCenter=1
    iaDTVCenter=4
    iaDTSingleLine=0x20
)
type iaRect struct{ Left,Top,Right,Bottom int32 }
type iaPaintStruct struct{
    HDC uintptr
    Erase int32
    Rect iaRect
    Restore int32
    IncUpdate int32
    Reserved [32]byte
}
type iaDrawItemStruct struct{
    ControlType uint32
    ControlID uint32
    ItemID uint32
    ItemAction uint32
    ItemState uint32
    ItemWindow uintptr
    Device uintptr
    Rectangle iaRect
    ItemData uintptr
}
var (
    iaGdi=syscall.NewLazyDLL("gdi32.dll")
    iaBeginPaint=iaUser32.NewProc("BeginPaint")
    iaEndPaint=iaUser32.NewProc("EndPaint")
    iaFillRect=iaUser32.NewProc("FillRect")
    iaDrawText=iaUser32.NewProc("DrawTextW")
    iaSendMessage=iaUser32.NewProc("SendMessageW")
    iaGetClientRect=iaUser32.NewProc("GetClientRect")
    iaSetBkMode=iaGdi.NewProc("SetBkMode")
    iaSetTextColor=iaGdi.NewProc("SetTextColor")
    iaCreateBrush=iaGdi.NewProc("CreateSolidBrush")
    iaDeleteObject=iaGdi.NewProc("DeleteObject")
    iaCreateFontProc=iaGdi.NewProc("CreateFontW")
    iaGetCurrentProcess=iaKernel32.NewProc("GetCurrentProcess")
    iaReadProcessMemory=iaKernel32.NewProc("ReadProcessMemory")
    iaThemeBrushSide uintptr
    iaThemeBrushHeader uintptr
    iaThemeBrushPanel uintptr
    iaThemeBrushWhite uintptr
    iaThemeBrushStatus uintptr
    iaThemeFontNormal uintptr
    iaThemeFontBold uintptr
    iaThemeFontTitle uintptr
    iaThemeFontButton uintptr
    iaThemeFontSection uintptr
)
func iaRGB(red,green,blue uint32)uintptr{return uintptr(red|(green<<8)|(blue<<16))}
func iaBrush(rgb uintptr)uintptr{
    b,_,_:=iaCreateBrush.Call(rgb)
    return b
}
func iaFont(size,weight int32)uintptr{
    height:=-size
    family:=syscall.StringToUTF16Ptr("Segoe UI")
    handle,_,_:=iaCreateFontProc.Call(
        uintptr(height),0,0,0,uintptr(weight),0,0,0,1,0,0,5,0,
        uintptr(unsafe.Pointer(family)))
    runtime.KeepAlive(family)
    return handle
}
func iaThemeInit(){
    iaThemeBrushHeader=iaBrush(iaRGB(5,22,48))
    iaThemeBrushSide=iaBrush(iaRGB(7,29,59))
    iaThemeBrushPanel=iaBrush(iaRGB(245,248,254))
    iaThemeBrushWhite=iaBrush(iaRGB(255,255,255))
    iaThemeBrushStatus=iaBrush(iaRGB(222,236,255))
    iaThemeFontNormal=iaFont(17,400)
    iaThemeFontBold=iaFont(18,700)
    iaThemeFontTitle=iaFont(33,700)
    iaThemeFontSection=iaFont(24,700)
    iaThemeFontButton=iaFont(18,700)
}
func iaThemeDestroy(){
    for _,obj:=range []uintptr{
        iaThemeBrushHeader,iaThemeBrushSide,iaThemeBrushPanel,iaThemeBrushWhite,
        iaThemeBrushStatus,iaThemeFontNormal,iaThemeFontBold,iaThemeFontTitle,
        iaThemeFontButton,iaThemeFontSection,
    }{
        if obj!=0{iaDeleteObject.Call(obj)}
    }
}
func iaApplyControlFont(window uintptr,klass string,id int,title string){
    var font=iaThemeFontNormal
    if id==iaCmdBrowse||id==iaCmdInstall||id==iaCmdClose||id==iaCmdCopy||(id>=300&&id<=305){
        font=iaThemeFontButton
    }
    if klass=="STATIC"&&font!=0{
        font=iaThemeFontBold
        if title=="Servidor"{font=iaThemeFontTitle}
        if title=="RPG"{font=iaThemeFontSection}
        if title=="Listo para instalar el traductor."{font=iaThemeFontNormal}
    }
    if font!=0{iaSendMessage.Call(window,iaWMSetFont,font,1)}
}
func iaRectFill(hdc uintptr,r iaRect,brush uintptr){
    iaFillRect.Call(hdc,uintptr(unsafe.Pointer(&r)),brush)
}
func iaPaintWindow(hwnd uintptr){
    var ps iaPaintStruct
    hdc,_,_:=iaBeginPaint.Call(hwnd,uintptr(unsafe.Pointer(&ps)))
    if hdc==0{return}
    defer iaEndPaint.Call(hwnd,uintptr(unsafe.Pointer(&ps)))
    var bounds iaRect
    iaGetClientRect.Call(hwnd,uintptr(unsafe.Pointer(&bounds)))
    iaRectFill(hdc,bounds,iaThemeBrushPanel)
    iaRectFill(hdc,iaRect{Left:0,Top:0,Right:bounds.Right,Bottom:105},iaThemeBrushHeader)
    iaRectFill(hdc,iaRect{Left:0,Top:105,Right:198,Bottom:bounds.Bottom},iaThemeBrushSide)
    accent:=iaBrush(iaRGB(0,102,233))
    if accent!=0{
        iaRectFill(hdc,iaRect{Left:198,Top:105,Right:bounds.Right,Bottom:110},accent)
        iaDeleteObject.Call(accent)
    }
    iaRectFill(hdc,iaRect{Left:216,Top:115,Right:bounds.Right-22,Bottom:bounds.Bottom-8},iaThemeBrushWhite)
    iaRectFill(hdc,iaRect{Left:225,Top:660,Right:bounds.Right-36,Bottom:704},iaThemeBrushStatus)
}
func iaColorControl(device,window uintptr)uintptr{
    ui:=&iaCurrentUI
    iaSetBkMode.Call(device,iaTransparent)
    if window==ui.titleLabel{
        iaSetTextColor.Call(device,iaRGB(255,255,255))
        return iaThemeBrushHeader
    }
    if window==ui.statusLabel{
        iaSetTextColor.Call(device,iaRGB(6,53,128))
        return iaThemeBrushStatus
    }
    if window==ui.input||window==ui.logs{
        iaSetTextColor.Call(device,iaRGB(19,42,75))
        return iaThemeBrushWhite
    }
    iaSetTextColor.Call(device,iaRGB(13,34,63))
    return iaThemeBrushWhite
}
func iaDrawButton(param uintptr)bool{
    if param==0{return false}
    // Drawitem data is owned by USER32. Copy the validated bytes with the
    // Win32 API instead of casting a callback uintptr to unsafe.Pointer.
    // The direct conversion triggers go vet and a bad LPARAM could fault.
    var data iaDrawItemStruct
    var read uintptr
    current,_,_:=iaGetCurrentProcess.Call()
    ok,_,_:=iaReadProcessMemory.Call(
        current,param,uintptr(unsafe.Pointer(&data)),
        unsafe.Sizeof(data),uintptr(unsafe.Pointer(&read)))
    if ok==0 || read!=uintptr(unsafe.Sizeof(data)){return false}
    id:=int(data.ControlID)
    var text string
    var background uintptr
    var foreground uintptr=iaRGB(255,255,255)
    switch id{
    case 300: text="01"
    case 301: text="RPG"
    case 302: text="03"
    case 303: text="04"
    case 304: text="05"
    case 305: text="+"
    case iaCmdBrowse: text="EXE"
    case iaCmdInstall: text="2. INSTALAR TRADUCTOR AUTOMÁTICO"
    case iaCmdClose: text="Cerrar"
    case iaCmdCopy: text="Copiar diagnóstico"
    case iaCmdRecover: text="Recuperar inicio MV"
    default: return false
    }
    if id==iaCmdInstall||id==iaCmdBrowse||id==301{
        background=iaRGB(0,96,225)
    }else if id==iaCmdClose||id==iaCmdCopy||id==iaCmdRecover{
        background=iaRGB(221,230,244)
        foreground=iaRGB(12,45,82)
    }else{
        background=iaRGB(21,51,88)
        if id!=301{
            foreground=iaRGB(205,219,240)
        }
    }
    if data.ItemState&1!=0{
        if id==iaCmdClose||id==iaCmdCopy||id==iaCmdRecover{background=iaRGB(194,213,237)}else{background=iaRGB(0,72,180)}
    }
    brush:=iaBrush(background)
    if brush!=0{
        iaRectFill(data.Device,data.Rectangle,brush)
        iaDeleteObject.Call(brush)
    }
    iaSetBkMode.Call(data.Device,iaTransparent)
    iaSetTextColor.Call(data.Device,foreground)
    label:=syscall.StringToUTF16(text)
    iaDrawText.Call(data.Device,uintptr(unsafe.Pointer(&label[0])),uintptr(^uint32(0)),
        uintptr(unsafe.Pointer(&data.Rectangle)),iaDTCenter|iaDTVCenter|iaDTSingleLine)
    runtime.KeepAlive(label)
    return true
}
// OPENFILENAMEW requires two *separately terminated* strings plus final NUL.
// syscall.StringToUTF16 panics if one input contains embedded \x00, which
// was the user's reproducible whole-app exit on the EXE button.
func iaExeFilterUTF16()[]uint16{
    label:=syscall.StringToUTF16("Juegos Windows (*.exe)")
    pattern:=syscall.StringToUTF16("*.exe")
    list:=append(label,pattern...)
    return append(list,0)
}
