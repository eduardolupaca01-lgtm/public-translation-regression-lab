#!/usr/bin/env python3
"""Integrate the verified RPG Maker MV installer into the one Servidor UI.

No second user-facing installer. Keep the old binary as a signed internal
compatibility resource until payload migration can be audited separately.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil

ROOT=Path("reference/tx541-rpg-onefile")
TARGET="main_windows.go"
PANEL="tx777_bootstrap_ui_windows.go"
SOURCES=("servidor_instalador_integrado_windows.go","servidor_instalador_integrado_windows_test.go")
CLEANHOST="github.com/camachogomez791-byte/tenshixgame-tx20026/reference/tx331-clean-product-host"
SUPERVISOR="github.com/camachogomez791-byte/tenshixgame-tx20026/reference/tx325-session-supervisor"

def one(s,old,new,tag):
    if s.count(old)!=1:
        raise RuntimeError("SERVIDOR_INTEGRATION_SOURCE_DRIFT_"+tag)
    return s.replace(old,new,1)

def transformed(main,panel):
    old='''    tx777Stage("TX777_ABRIENDO_INSTALADOR","El modelo fue preparado; abriendo el instalador con el diagnóstico acumulado.")
    return launchRPGEnv(appDir,portableSmoke,local,gameExe)'''
    new='''    // The old GUI is retained only for original smoke-mode compatibility.
    // Normal Servidor installation updates the game from THIS same process.
    if portableSmoke{return launchRPGEnv(appDir,true,local,gameExe)}
    tx777Stage("TX779_INSTALL_MV","Verificando V95 e instalando el complemento nativo de RPG Maker MV desde Servidor.")
    if err:=servidorInstallMV(gameExe,local);err!=nil{return err}
    tx777Stage("TX779_GAME_PLUGIN_VERIFIED","El complemento MV quedó instalado y verificado. Cierra el juego si estaba abierto; al iniciarlo V95 se conectará en segundo plano.")
    return nil'''
    main=one(main,old,new,"CHILD_GUI_LAUNCH")
    panel=one(panel,
       'event.code="TX777_INTERFAZ_ABIERTA"\n        event.desc="El instalador principal de V95 se abrió. El progreso restante se verá en su panel de diagnóstico."',
       'event.code="TX779_INSTALACION_COMPLETADA"\n        event.desc="Instalación de RPG Maker MV completada en Servidor. El juego puede abrirse normalmente."',
       "SUCCESS_STATUS")
    panel=one(panel,
       '''                    if !e.failed{
                        tx777Destroy.Call(hwnd)
                        return 0
                    }''',
       '''                    if !e.failed{
                        // Keep the only Servidor window available as a receipt.
                        tx777Enable.Call(st.browse,0)
                        tx777Enable.Call(st.install,0)
                        tx777Enable.Call(st.exit,1)
                        return 0
                    }''',"NO_SECOND_WINDOW")
    if "tx777Stage(\"TX777_ABRIENDO_INSTALADOR\"" in main:
        raise RuntimeError("SERVIDOR_OLD_GUI_STILL_EXECUTED")
    return main,panel

def patch_module(raw):
    if "module tenshixgame.local/rpg-onefile" not in raw or CLEANHOST in raw:
        raise RuntimeError("SERVIDOR_GO_MODULE_CONTRACT_CHANGED")
    addition=("\nrequire "+CLEANHOST+" v0.0.0\n"
        "replace "+CLEANHOST+" => ../tx331-clean-product-host\n"
        "replace "+SUPERVISOR+" => ../tx325-session-supervisor\n")
    return raw.rstrip()+"\n"+addition

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--self-test",action="store_true")
    a.add_argument("--source-root",type=Path)
    a.add_argument("--overlays",type=Path)
    x=a.parse_args()
    if x.self_test:
        # Assert the source can be patched before touching private files.
        main_src=Path(__file__).resolve().parents[1]/"tx777"/"tx777_bootstrap_ui_windows.go"
        source=main_src.read_text("utf-8")
        assert 'event.code="TX777_INTERFAZ_ABIERTA"' in source
        assert "tx777Destroy.Call(hwnd)" in source
        assert "TX779_GAME_PLUGIN_VERIFIED" in transformed.__code__.co_consts.__str__()
        print("SERVIDOR_SINGLE_UI_SOURCE_PREFLIGHT_PASS")
        return
    if not x.source_root or not x.overlays:
        a.error("--source-root and --overlays required")
    root=x.source_root/ROOT
    for f in SOURCES:
        if not (x.overlays/f).is_file() or (root/f).exists():
            raise RuntimeError("SERVIDOR_INTEGRATED_OVERLAY_INVALID")
    first,second=transformed((root/TARGET).read_text("utf-8"),
                             (root/PANEL).read_text("utf-8"))
    module=patch_module((root/"go.mod").read_text("utf-8"))
    # All anchors and sources checked before any file is written.
    (root/TARGET).write_text(first,"utf-8")
    (root/PANEL).write_text(second,"utf-8")
    (root/"go.mod").write_text(module,"utf-8")
    for file in SOURCES:
        shutil.copyfile(x.overlays/file,root/file)
    print("SERVIDOR_MV_SINGLE_INTERFACE_NATIVE_INSTALLER_INTEGRATED")

if __name__=="__main__":
    main()
