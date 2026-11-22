#!/usr/bin/env python3
"""Servidor: adapt the existing TX777 authentic V95 Win32 bootstrap for MV only.

This modifies an exact, disposable private checkout in CI, not historical repos.
The 26 original V95/installation/rollback gates remain mandatory.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil

ONEFILE = Path("reference/tx541-rpg-onefile")
OVERLAY_FILE = "tx777_bootstrap_ui_windows.go"
GUARD_FILES = ("servidor_mv_guard_windows.go", "servidor_mv_guard_windows_test.go")

def replace_one(text: str, old: str, new: str, name: str) -> str:
    if text.count(old) != 1:
        raise ValueError("SERVIDOR_SOURCE_CONTRACT_CHANGED_" + name)
    return text.replace(old, new, 1)

def transform(source: str) -> str:
    result = source
    result = replace_one(result,
        'title:=tx777UTF16("TENSHIXGAME — Instalador portátil de IA")',
        'title:=tx777UTF16("Servidor")', "WINDOW_TITLE")
    result = replace_one(result,
        'tx777WSOverlapped|tx777WSVisible,120,80,740,640,0,0,h,0',
        'tx777WSOverlapped|tx777WSVisible,120,80,1020,750,0,0,h,0',
        "WINDOW_GEOMETRY")
    result = replace_one(result,
        'tx771GameRoot(path)', 'servidorMVGameRoot(path)',
        "MV_ONLY_FILE_DIALOG")
    result = replace_one(result,
        'tx771GameRoot(st.game)', 'servidorMVGameRoot(st.game)',
        "MV_ONLY_RECHECK")
    result = replace_one(result,
        'esta versión instala la IA original solo en RPG Maker MV/MZ.',
        'esta primera prueba admite únicamente RPG Maker MV.',
        "MV_ONLY_FAILURE")
    result = replace_one(result,
        'Carpeta RPG Maker MV/MZ identificada. Pulsa PREPARAR E INSTALAR para continuar.',
        'Carpeta RPG verificada. Pulsa INSTALAR TRADUCTOR AUTOMÁTICO para continuar.',
        "SELECTED_MESSAGE")
    result = replace_one(result,
        'tx777Add("TX777_LISTO","Selecciona una copia RPG Maker MV/MZ. No se ha leído ni instalado el modelo.")',
        'tx777Add("TX777_LISTO","Listo para instalar el traductor. Selecciona el EXE de una copia cerrada.")',
        "INITIAL_STATE")
    first = '    tx777Control(hwnd,"STATIC","TENSHIXGAME · Traductor de juegos con IA local",0,23,20,675,30,0)'
    last = '    tx777Add("TX777_LISTO"'
    if result.count(first) != 1 or result.count(last) != 1:
        raise ValueError("SERVIDOR_SOURCE_CONTRACT_CHANGED_WINDOW_CONTROLS")
    start, end = result.index(first), result.index(last)
    controls = """    // Servidor: five independent sheets. Only RPG is active in this pilot.
    for _,slot := range []struct{label string; y int32}{
        {"01",42},{"RPG",116},{"03",190},{"04",264},{"05",338},{"+",412},
    } {
        tx777Control(hwnd,"STATIC",slot.label,tx777WSBorder|0x0001,20,slot.y,150,60,0)
    }
    tx777Control(hwnd,"STATIC","RPG",0,208,20,740,40,0)
    tx777Control(hwnd,"STATIC",
        "1. Selecciona el archivo EXE del juego (una copia del juego cerrado):",
        0,208,88,755,28,0)
    st.selectedField=tx777Control(hwnd,"EDIT","",tx777WSBorder|tx777ESReadOnly,208,125,587,41,0)
    st.browse=tx777Control(hwnd,"BUTTON","EXE",tx777WSTabstop,809,124,165,43,tx777CmdBrowse)
    st.install=tx777Control(hwnd,"BUTTON","2. INSTALAR TRADUCTOR AUTOMÁTICO",
        tx777WSTabstop,208,204,766,63,tx777CmdInstall)
    tx777Control(hwnd,"STATIC","Estado de instalación:",0,208,294,760,29,0)
    st.statusField=tx777Control(hwnd,"EDIT","",
        tx777WSBorder|tx777WSVScroll|tx777ESMultiline|tx777ESReadOnly|tx777ESAutoVScroll,
        208,330,766,258,0)
    st.copyButton=tx777Control(hwnd,"BUTTON","Copiar diagnóstico",tx777WSTabstop,
        208,608,495,40,tx777CmdCopy)
    st.exit=tx777Control(hwnd,"BUTTON","Cerrar",tx777WSTabstop,715,608,259,40,tx777CmdExit)
"""
    result = result[:start] + controls + result[end:]
    if "Motor de esta versión:" in result or "Seleccionar EXE" in result:
        raise ValueError("SERVIDOR_OLD_ENGINE_SELECTOR_REMAINS")
    return result

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--overlays", type=Path)
    args = parser.parse_args()
    if args.self_test:
        source=(Path(__file__).resolve().parents[1] / "tx777" / OVERLAY_FILE).read_text(encoding="utf-8")
        transformed=transform(source)
        assert transformed.count("servidorMVGameRoot(")==2
        assert 'tx777UTF16("Servidor")' in transformed
        assert "2. INSTALAR TRADUCTOR AUTOMÁTICO" in transformed
        assert 'RPG",tx777WSBorder|0x0001' not in transformed or "slot.label" in transformed
        assert 'tx777GameRootForTest' in transformed
        print("SERVIDOR_MV_SOURCE_FREE_PATCH_PASS")
        return
    if not args.source_root or not args.overlays:
        parser.error("--source-root and --overlays are required")
    source_dir=args.source_root / ONEFILE
    target=source_dir / OVERLAY_FILE
    if not target.is_file():
        raise RuntimeError("SERVIDOR_AUTHENTIC_TX777_SOURCE_NOT_INSTALLED")
    converted=transform(target.read_text(encoding="utf-8"))
    for filename in GUARD_FILES:
        src=args.overlays / filename
        if not src.is_file() or (source_dir / filename).exists():
            raise RuntimeError("SERVIDOR_MV_GUARD_SOURCE_INVALID_OR_PRESENT")
    target.write_text(converted,encoding="utf-8")
    for filename in GUARD_FILES:
        shutil.copyfile(args.overlays / filename,source_dir / filename)
    print("SERVIDOR_MV_NATIVE_UI_AND_GUARD_STAGED")

if __name__ == "__main__":
    main()
