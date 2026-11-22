//go:build windows

package main

// Pure native Win32 styling for Servidor. Keeps V95 and the historical
// installer untouched; other numbered sheets start completely blank.
import (
 "fmt"
 "runtime"
 "strings"
 "syscall"
 "unsafe"
)
const (
 servidorIDAppTitle=910
 servidorIDPageTitle=911
 servidorIDPrompt=912
 servidorIDInstallTitle=913
 servidorIDSummary=914
 servidorIDNavBase=820
 servidorIDNavAdd=899
 servidorOwnerDraw=0x0000000B
 servidorStaticOwnerDraw=0x0000000D
 servidorWMPaint=0x000F
 servidorWMEraseBackground=0x0014
 servidorWMDrawItem=0x002B
 servidorWMColorStatic=0x0138
 servidorWMColorEdit=0x0133
)
type servidorRect struct{Left,Top,Right,Bottom int32}
type servidorPaintStruct struct{
 HDC uintptr
 Erase int32
 Paint servidorRect
 Restore int32
 IncUpdate int32
 Reserved [32]byte
}
type servidorDrawItem struct{
 CtlType uint32
 CtlID uint32
 ItemID uint32
 ItemAction uint32
 ItemState uint32
 HwndItem uintptr
 HDC uintptr
 Rect servidorRect
 ItemData uintptr
}
var(
 servidorGDI=syscall.NewLazyDLL("gdi32.dll")
 servidorUser=syscall.NewLazyDLL("user32.dll")
 servidorCreateBrush=servidorGDI.NewProc("CreateSolidBrush")
 servidorDeleteObject=servidorGDI.NewProc("DeleteObject")
 servidorFillRect=servidorUser.NewProc("FillRect")
 servidorGetClientRect=servidorUser.NewProc("GetClientRect")
 servidorGetDlgID=servidorUser.NewProc("GetDlgCtrlID")
 servidorCreateFont=servidorGDI.NewProc("CreateFontW")
 servidorSetTextColor=servidorGDI.NewProc("SetTextColor")
 servidorSetBkMode=servidorGDI.NewProc("SetBkMode")
 servidorSelectObject=servidorGDI.NewProc("SelectObject")
 servidorRoundRect=servidorGDI.NewProc("RoundRect")
 servidorGetStockObject=servidorGDI.NewProc("GetStockObject")
 servidorGetWindowText=servidorUser.NewProc("GetWindowTextW")
 servidorDrawText=servidorUser.NewProc("DrawTextW")
 servidorDrawFocusRect=servidorUser.NewProc("DrawFocusRect")
 servidorBeginPaint=servidorUser.NewProc("BeginPaint")
 servidorEndPaint=servidorUser.NewProc("EndPaint")
 servidorInvalidateRect=servidorUser.NewProc("InvalidateRect")
 servidorMoveWindow=servidorUser.NewProc("MoveWindow")
 // Only the native draw-item structure is copied. No raw Go uintptr-to-pointer
 // cast is retained; RtlMoveMemory is supported by ntdll.dll on Windows 10.
 servidorMoveMemory=syscall.NewLazyDLL("ntdll.dll").NewProc("RtlMoveMemory")
 servidorFontRegular uintptr
 servidorFontStrong uintptr
 servidorFontTitle uintptr
 servidorBrushPage uintptr
 servidorBrushTop uintptr
 servidorBrushSidebar uintptr
 servidorBrushInactive uintptr
 servidorBrushBlue uintptr
 servidorBrushLightBlue uintptr
 servidorBrushWhite uintptr
 servidorBrushNeutral uintptr
 servidorSummary uintptr
 servidorPageTitle uintptr
 servidorAddButton uintptr
 servidorRPGControls []uintptr
 servidorSidebarButtons []uintptr
 servidorActivePage=2
 servidorSheetCount=5
)
func servidorRGB(r,g,b uint32)uintptr{return uintptr((b<<16)|(g<<8)|r)}
func servidorMakeBrush(r,g,b uint32)uintptr{p,_,_:=servidorCreateBrush.Call(servidorRGB(r,g,b));return p}
func servidorMakeFont(height,weight int32)uintptr{
 family,_:=syscall.UTF16PtrFromString("Segoe UI")
 font,_,_:=servidorCreateFont.Call(uintptr(int64(-height)),0,0,0,uintptr(weight),0,0,0,1,0,0,5,0,uintptr(unsafe.Pointer(family)))
 runtime.KeepAlive(family)
 return font
}
func servidorSkinInitialize(){
 servidorBrushPage=servidorMakeBrush(244,247,252)
 servidorBrushTop=servidorMakeBrush(6,23,49)
 servidorBrushSidebar=servidorMakeBrush(8,27,55)
 servidorBrushInactive=servidorMakeBrush(22,47,80)
 servidorBrushBlue=servidorMakeBrush(4,99,229)
 servidorBrushLightBlue=servidorMakeBrush(226,238,255)
 servidorBrushWhite=servidorMakeBrush(255,255,255)
 servidorBrushNeutral=servidorMakeBrush(228,235,244)
 servidorFontRegular=servidorMakeFont(17,400)
 servidorFontStrong=servidorMakeFont(19,700)
 servidorFontTitle=servidorMakeFont(30,700)
 servidorRPGControls=nil
 servidorSidebarButtons=nil
 servidorSummary=0
 servidorPageTitle=0
 servidorAddButton=0
 servidorActivePage=2
 servidorSheetCount=5
}
func servidorSkinDispose(){
 for _,obj:=range []uintptr{
 servidorBrushPage,servidorBrushTop,servidorBrushSidebar,
 servidorBrushInactive,servidorBrushBlue,servidorBrushLightBlue,
 servidorBrushWhite,servidorBrushNeutral,
 servidorFontRegular,servidorFontStrong,servidorFontTitle,
 }{if obj!=0{servidorDeleteObject.Call(obj)}}
}
func servidorApplyFont(hwnd uintptr,class string,id uintptr){
 if hwnd==0{return}
 font:=servidorFontRegular
 switch {
 case id==servidorIDAppTitle,id==servidorIDPageTitle:font=servidorFontTitle
 case id==tx777CmdInstall,id==tx777CmdBrowse,
 id>=servidorIDNavBase+1&&id<=servidorIDNavBase+9,
 id==servidorIDNavAdd,id==servidorIDInstallTitle:font=servidorFontStrong
 case strings.EqualFold(class,"BUTTON"):font=servidorFontStrong
 }
 if font!=0{tx777Send.Call(hwnd,tx777WmSetFont,font,1)}
}
func servidorAddRPGControl(parent uintptr,class,label string,style uintptr,x,y,w,h int32,id uintptr)uintptr{
 handle:=tx777Control(parent,class,label,style,x,y,w,h,id)
 if handle!=0{servidorRPGControls=append(servidorRPGControls,handle)}
 return handle
}
func servidorSetSummary(value string){
 if servidorSummary!=0{tx777Set(servidorSummary,value)}
}
func servidorPaintBackground(hwnd,hdc uintptr){
 if hdc==0{return}
 var bounds servidorRect
 if ok,_,_:=servidorGetClientRect.Call(hwnd,uintptr(unsafe.Pointer(&bounds)));ok==0{return}
 servidorFillRect.Call(hdc,uintptr(unsafe.Pointer(&bounds)),servidorBrushPage)
 header:=servidorRect{0,0,bounds.Right,82}
 servidorFillRect.Call(hdc,uintptr(unsafe.Pointer(&header)),servidorBrushTop)
 side:=servidorRect{0,82,194,bounds.Bottom}
 servidorFillRect.Call(hdc,uintptr(unsafe.Pointer(&side)),servidorBrushSidebar)
 accent:=servidorRect{194,78,bounds.Right,82}
 servidorFillRect.Call(hdc,uintptr(unsafe.Pointer(&accent)),servidorBrushBlue)
}
func servidorSkinPaintWindow(hwnd uintptr)uintptr{
 var paint servidorPaintStruct
 hdc,_,_:=servidorBeginPaint.Call(hwnd,uintptr(unsafe.Pointer(&paint)))
 if hdc!=0{servidorPaintBackground(hwnd,hdc)}
 servidorEndPaint.Call(hwnd,uintptr(unsafe.Pointer(&paint)))
 return 0
}
func servidorSkinColorStatic(hdc,child uintptr)uintptr{
 servidorSetBkMode.Call(hdc,1)
 id,_,_:=servidorGetDlgID.Call(child)
 if id==servidorIDAppTitle||id==servidorIDPageTitle{
  servidorSetTextColor.Call(hdc,servidorRGB(255,255,255))
  return servidorBrushTop
 }
 servidorSetTextColor.Call(hdc,servidorRGB(20,36,62))
 return servidorBrushPage
}
func servidorSkinColorEdit(hdc uintptr)uintptr{
 servidorSetTextColor.Call(hdc,servidorRGB(20,36,62))
 return servidorBrushWhite
}
func servidorGetControlCaption(hwnd uintptr)string{
 buffer:=make([]uint16,512)
 n,_,_:=servidorGetWindowText.Call(hwnd,uintptr(unsafe.Pointer(&buffer[0])),uintptr(len(buffer)))
 runtime.KeepAlive(buffer)
 if n==0{return ""}
 return syscall.UTF16ToString(buffer)
}
func servidorSkinDrawControl(lp uintptr)bool{
 if lp==0{return false}
 var item servidorDrawItem
 // Copy native WM_DRAWITEM data without keeping an unsafe pointer.
 servidorMoveMemory.Call(uintptr(unsafe.Pointer(&item)),lp,unsafe.Sizeof(item))
 id:=uintptr(item.CtlID)
 if item.HDC==0{return false}
 outer:=servidorBrushPage
 fill:=servidorBrushNeutral
 textColor:=servidorRGB(22,45,77)
 if id>=servidorIDNavBase+1&&id<=servidorIDNavBase+9||id==servidorIDNavAdd{
  outer=servidorBrushSidebar
  fill=servidorBrushInactive
  textColor=servidorRGB(241,246,255)
  if id==uintptr(servidorIDNavBase+servidorActivePage){fill=servidorBrushBlue}
 }else if id==tx777CmdInstall||id==tx777CmdBrowse{
  fill=servidorBrushBlue
  textColor=servidorRGB(255,255,255)
 }else if id==servidorIDSummary{
  fill=servidorBrushLightBlue
  textColor=servidorRGB(14,55,112)
 }
 servidorFillRect.Call(item.HDC,uintptr(unsafe.Pointer(&item.Rect)),outer)
 oldBrush,_,_:=servidorSelectObject.Call(item.HDC,fill)
 nullPen,_,_:=servidorGetStockObject.Call(8)
 oldPen,_,_:=servidorSelectObject.Call(item.HDC,nullPen)
 r:=item.Rect
 servidorRoundRect.Call(item.HDC,uintptr(int64(r.Left+1)),uintptr(int64(r.Top+1)),uintptr(int64(r.Right-1)),uintptr(int64(r.Bottom-1)),16,16)
 servidorSelectObject.Call(item.HDC,oldPen)
 servidorSelectObject.Call(item.HDC,oldBrush)
 servidorSetBkMode.Call(item.HDC,1)
 servidorSetTextColor.Call(item.HDC,textColor)
 font:=servidorFontStrong
 if id==servidorIDSummary{font=servidorFontRegular}
 oldFont,_,_:=servidorSelectObject.Call(item.HDC,font)
 content:=servidorGetControlCaption(item.HwndItem)
 u16,_:=syscall.UTF16FromString(content)
 if len(u16)>0{
  captionArea:=item.Rect
  if id==servidorIDSummary{captionArea.Left+=20}
  flags:=uintptr(0x0004|0x0020|0x0001)
  if id==servidorIDSummary{flags=0x0004|0x0020}
  servidorDrawText.Call(item.HDC,uintptr(unsafe.Pointer(&u16[0])),uintptr(len(u16)-1),uintptr(unsafe.Pointer(&captionArea)),flags)
 }
 servidorSelectObject.Call(item.HDC,oldFont)
 if item.ItemState&0x0010!=0{servidorDrawFocusRect.Call(item.HDC,uintptr(unsafe.Pointer(&item.Rect)))}
 return true
}
func servidorHandleSheetCommand(hwnd uintptr,id uintptr)bool{
 if id==servidorIDNavAdd{
  if tx777Screen==nil||tx777Screen.running||servidorFilePickerBusy{return true}
  if servidorSheetCount>=7{
   servidorSetSummary("El panel ya contiene el máximo de hojas visibles de esta prueba.")
   return true
  }
  servidorSheetCount++
  current:=servidorSheetCount
  top:=int32(97+(current-1)*68)
  handle:=tx777Control(hwnd,"BUTTON",fmt.Sprintf("%02d",current),
   servidorOwnerDraw|tx777WSTabstop,18,top,158,56,uintptr(servidorIDNavBase+current))
  servidorSidebarButtons=append(servidorSidebarButtons,handle)
  if servidorAddButton!=0{servidorMoveWindow.Call(servidorAddButton,18,uintptr(top+68),158,56,1)}
  servidorSetActivePage(current)
  return true
 }
 page:=int(id)-servidorIDNavBase
 if page<1||page>servidorSheetCount{return false}
 if tx777Screen==nil||tx777Screen.running||servidorFilePickerBusy{return true}
 servidorSetActivePage(page)
 return true
}
func servidorSetActivePage(page int){
 servidorActivePage=page
 visibility:=uintptr(0)
 if page==2{visibility=5}
 for _,h:=range servidorRPGControls{if h!=0{tx777Show.Call(h,visibility)}}
 if servidorPageTitle!=0{
  if page==2{tx777Set(servidorPageTitle,"RPG")}
  if page!=2{tx777Set(servidorPageTitle,fmt.Sprintf("Hoja %02d",page))}
 }
 for _,h:=range servidorSidebarButtons{
  if h!=0{servidorInvalidateRect.Call(h,0,1)}
 }
}
