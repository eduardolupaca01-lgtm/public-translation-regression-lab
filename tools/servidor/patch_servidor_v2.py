#!/usr/bin/env python3
"""Servidor v2: fix EXE picker and improve native Win32 layout.

Only changes the disposable, pinned original V95 checkout in Windows CI.
Never weakens the neural, install, restore, cache or SHA-256 gates.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil

ONEFILE=Path("reference/tx541-rpg-onefile")
MAIN="tx777_bootstrap_ui_windows.go"
ADDITIONS=(
    "servidor_picker_windows.go",
    "servidor_picker_windows_test.go",
    "servidor_skin_windows.go",
)

def exactly_once(s: str,old: str,replacement: str,tag: str)->str:
    if s.count(old)!=1:raise ValueError("SERVIDOR_V2_UPSTREAM_CONTRACT_CHANGED_"+tag)
    return s.replace(old,replacement,1)

def transform(s: str)->str:
    s=exactly_once(s,'''    if hwnd!=0{
        f,_,_:=tx777Font.Call(17) // DEFAULT_GUI_FONT
        if f!=0{tx777Send.Call(hwnd,tx777WmSetFont,f,1)}
    }''', '''    if hwnd!=0{servidorApplyFont(hwnd,class,id)}''',"TYPOGRAPHY")
    s=exactly_once(s,
        'Procedure:cb,Module:h,Background:6,Name:name}',
        'Procedure:cb,Module:h,Background:0,Name:name}',"BACKGROUND")
    s=exactly_once(s,
        '    name:=tx777UTF16("TENSHIXGAME_TX777_GAME_LOCAL_STARTUP")',
        '    servidorSkinInitialize()\n    defer servidorSkinDispose()\n    name:=tx777UTF16("TENSHIXGAME_TX777_GAME_LOCAL_STARTUP")',"SKIN_LIFETIME")
    s=exactly_once(s,'    case tx777WmCommand:\n        if st==nil{return 0}', '''    case servidorWMFilePickerResult:
        servidorPickerComplete()
        return 0
    case servidorWMEraseBackground:
        return 1
    case servidorWMPaint:
        return servidorSkinPaintWindow(hwnd)
    case servidorWMDrawItem:
        if servidorSkinDrawControl(lparam){return 1}
    case servidorWMColorStatic:
        return servidorSkinColorStatic(wparam,lparam)
    case servidorWMColorEdit:
        return servidorSkinColorEdit(wparam)
    case tx777WmCommand:
        if servidorHandleSheetCommand(hwnd,wparam&0xffff){return 0}
        if st==nil{return 0}''',"WINDOW_MESSAGES")
    browse_begin="        case tx777CmdBrowse:\n"
    browse_end="        case tx777CmdInstall:\n"
    if s.count(browse_begin)!=1 or s.count(browse_end)!=1:
        raise ValueError("SERVIDOR_V2_UPSTREAM_CONTRACT_CHANGED_PICKER_BRANCH")
    start,end=s.index(browse_begin),s.index(browse_end)
    s=s[:start]+'''        case tx777CmdBrowse:
            if st.running || servidorFilePickerBusy{return 0}
            servidorPickerStart(hwnd)
            return 0
'''+s[end:]
    s=exactly_once(s,'''        case tx777CmdInstall:
            if st.running{return 0}''','''        case tx777CmdInstall:
            if st.running || servidorFilePickerBusy{return 0}''',"NO_INSTALL_DURING_PICKER")
    s=exactly_once(s,'''    case tx777WmClose:
        if st!=nil&&st.running&&!st.finished {''','''    case tx777WmClose:
        if servidorFilePickerBusy{
            servidorSetSummary("Cierra primero el selector de archivos EXE.")
            return 0
        }
        if st!=nil&&st.running&&!st.finished {''',"PROTECTED_CLOSE")
    marker_start='    // Servidor: five independent sheets. Only RPG is active in this pilot.'
    marker_end='    tx777Add("TX777_LISTO","Listo para instalar el traductor. Selecciona el EXE de una copia cerrada.")'
    if s.count(marker_start)!=1 or s.count(marker_end)!=1:
        raise ValueError("SERVIDOR_V2_UPSTREAM_CONTRACT_CHANGED_CONTROLS")
    p,q=s.index(marker_start),s.index(marker_end)
    controls='''    // The only active translation sheet is RPG. The others start empty.
    // Native owner-drawn Win32 controls: no browser, Python or extra runtime.
    tx777Control(hwnd,"STATIC","Servidor",0,20,14,330,56,servidorIDAppTitle)
    servidorPageTitle=tx777Control(hwnd,"STATIC","RPG",0,215,17,660,50,servidorIDPageTitle)
    for i,label := range []string{"01","RPG","03","04","05"} {
        h:=tx777Control(hwnd,"BUTTON",label,servidorOwnerDraw|tx777WSTabstop,
            18,int32(97+i*68),158,56,uintptr(servidorIDNavBase+i+1))
        servidorSidebarButtons=append(servidorSidebarButtons,h)
    }
    servidorAddButton=tx777Control(hwnd,"BUTTON","+",servidorOwnerDraw|tx777WSTabstop,
        18,437,158,56,servidorIDNavAdd)
    servidorAddRPGControl(hwnd,"STATIC",
        "1. Selecciona el archivo EXE del juego (una copia del juego cerrado):",
        0,210,105,770,33,servidorIDPrompt)
    st.selectedField=servidorAddRPGControl(hwnd,"EDIT","",
        tx777WSBorder|tx777ESReadOnly,210,148,575,45,0)
    st.browse=servidorAddRPGControl(hwnd,"BUTTON","EXE",
        servidorOwnerDraw|tx777WSTabstop,800,148,176,45,tx777CmdBrowse)
    st.install=servidorAddRPGControl(hwnd,"BUTTON","2. INSTALAR TRADUCTOR AUTOMÁTICO",
        servidorOwnerDraw|tx777WSTabstop,210,218,766,58,tx777CmdInstall)
    servidorAddRPGControl(hwnd,"STATIC","Estado de instalación:",0,210,299,760,30,
        servidorIDInstallTitle)
    st.statusField=servidorAddRPGControl(hwnd,"EDIT","",
        tx777WSBorder|tx777WSVScroll|tx777ESMultiline|tx777ESReadOnly|tx777ESAutoVScroll,
        210,338,766,237,0)
    servidorSummary=servidorAddRPGControl(hwnd,"STATIC","",
        servidorStaticOwnerDraw,210,588,766,44,servidorIDSummary)
    st.copyButton=servidorAddRPGControl(hwnd,"BUTTON","Copiar diagnóstico",
        servidorOwnerDraw|tx777WSTabstop,210,648,495,43,tx777CmdCopy)
    st.exit=servidorAddRPGControl(hwnd,"BUTTON","Cerrar",
        servidorOwnerDraw|tx777WSTabstop,720,648,256,43,tx777CmdExit)
    servidorSetActivePage(2)
    servidorSetSummary("Listo para instalar el traductor.")
'''
    s=s[:p]+controls+s[q+len(marker_end):]
    if 'tx771ChooseGameEXE()' in s:
        raise ValueError("SERVIDOR_V2_LEGACY_MODAL_PICKER_STILL_CALLED")
    if "servidorPickerStart(hwnd)" not in s or "servidorSetActivePage(2)" not in s:
        raise ValueError("SERVIDOR_V2_CONTROLS_NOT_CONNECTED")
    return s

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--source-root",type=Path)
    parser.add_argument("--overlays",type=Path)
    args=parser.parse_args()
    if args.self_test:
        from patch_servidor import transform as old_transform
        source=Path(__file__).resolve().parents[1]/"tx777"/MAIN
        result=transform(old_transform(source.read_text(encoding="utf-8")))
        assert result.count("servidorPickerStart(hwnd)")==1
        assert "tx771ChooseGameEXE()" not in result
        assert "servidorWMFilePickerResult:" in result
        assert "servidorIDNavBase+i+1" in result
        assert "servidorMVGameRoot(st.game)" in result
        assert 'servidorSetSummary("Listo para instalar el traductor.")' in result
        print("SERVIDOR_V2_GUI_AND_PICKER_SOURCE_PREFLIGHT_PASS")
        return
    if not args.source_root or not args.overlays:
        parser.error("--source-root and --overlays required")
    directory=args.source_root/ONEFILE
    target=directory/MAIN
    if not target.is_file():
        raise RuntimeError("SERVIDOR_V2_AUTHENTIC_PRIVATE_SOURCE_REQUIRED")
    for filename in ADDITIONS:
        src=args.overlays/filename
        if not src.is_file() or (directory/filename).exists():
            raise RuntimeError("SERVIDOR_V2_OVERLAY_INVALID_OR_PRESENT_"+filename)
    patched=transform(target.read_text(encoding="utf-8"))
    target.write_text(patched,encoding="utf-8")
    for filename in ADDITIONS:
        shutil.copyfile(args.overlays/filename,directory/filename)
    print("SERVIDOR_V2_NATIVE_SKIN_AND_NONBLOCKING_PICKER_STAGED")

if __name__=="__main__":
    main()
