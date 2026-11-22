#!/usr/bin/env python3
"""TX777: disable original modal V95 welcome and replace with full launcher.

Only a temporary checkout of the exact source SHA is changed in the Windows
owner build. No private game, weights, credentials or binaries are published.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

PRIVATE_SHA="aeb9ff9326e418fbabe2d53dff7891f4fb340c37"
ONEFILE=Path("reference/tx541-rpg-onefile")
HOST=Path("reference/tx331-clean-product-host/cmd/tenshixgame-ui")
FILES=("tx777_bootstrap_ui_windows.go","tx777_bootstrap_ui_windows_test.go")
def replace_once(text: str, before: str, after: str, label: str)->str:
    if text.count(before)!=1:
        raise RuntimeError("TX777_SOURCE_PIN_CHANGED_"+label)
    return text.replace(before,after,1)

def transform_bootstrap(text: str)->str:
    result=text
    result=replace_once(result,
        "var tx771WelcomeBeforePayload = tx771Welcome",
        "var tx771WelcomeBeforePayload = tx777PlainWelcome","NO_MORE_V95_WELCOME")
    result=replace_once(result,
        "var tx771SelectGameBeforePayload = tx771ChooseGameEXE",
        "var tx771SelectGameBeforePayload = tx777SelectGameWithPanel","NATIVE_MAIN_GUI")
    result=replace_once(result,
        "    payload,err:=tx771ReadEmbeddedPayload(own)\n",
        '    tx777Stage("TX777_VERIFICANDO_PAQUETE","Verificando la firma y el SHA-256 del paquete neuronal original V95.")\n    payload,err:=tx771ReadEmbeddedPayload(own)\n',"PAYLOAD_PROGRESS")
    result=replace_once(result,
        "    appDir,local,err:=tx771PreparePortableOnefile(payload,root)\n",
        '    tx777Stage("TX777_PREPARANDO_IA","Comprobando archivos originales y preparando el modelo completo dentro del juego.")\n    appDir,local,err:=tx771PreparePortableOnefile(payload,root)\n',"MODEL_PROGRESS")
    result=replace_once(result,
        "    return launchRPGEnv(appDir,portableSmoke,local,gameExe)\n",
        '    tx777Stage("TX777_ABRIENDO_INSTALADOR","El modelo fue preparado; abriendo el instalador con el diagnóstico acumulado.")\n    return launchRPGEnv(appDir,portableSmoke,local,gameExe)\n',"INNER_DASHBOARD")
    result=replace_once(result,
        "    if err:=run();err!=nil{\n",
        '''    launchedErr:=run()
    // If the native startup UI was shown, display errors there instead of
    // opening a second modal message. CI and --smoke paths stay unchanged.
    if tx777Finalize(launchedErr){
        if launchedErr!=nil{os.Exit(1)}
        return
    }
    if err:=launchedErr;err!=nil{
''',"ERROR_REPORT_IN_SAME_GUI")
    return result

def transform_dashboard(text: str)->str:
    before='''    rpgShowWindow.Call(hwnd,rpgSWShow)
    rpgUpdateWindow.Call(hwnd)
    rpgSetTimer.Call(hwnd,rpgInstallTimerID,400,0)'''
    after='''    rpgShowWindow.Call(hwnd,rpgSWShow)
    rpgUpdateWindow.Call(hwnd)
    // The owner already pressed Install in the fast outer Win32 selector.
    // Avoid a second file choice or second consent button. A direct launch
    // of the inner EXE still behaves exactly like before.
    if selected:=os.Getenv("TX771_PORTABLE_GAME_EXE");selected!=""&&rpgIsValidSelection(selected){
        rpgState.game=selected
        rpgSetWindowText.Call(rpgState.textBox,rpgUTF16(selected))
        tx776StartReport()
        tx776Append("TX777_JUEGO_PREENLAZADO","Se recuperó la copia del juego seleccionada en la ventana inicial.")
        rpgPostMessage.Call(hwnd,rpgWMCommand,uintptr(rpgIDInstall),0)
    }
    rpgSetTimer.Call(hwnd,rpgInstallTimerID,400,0)'''
    return replace_once(text,before,after,"PREFILL_AND_START_TX776")

def patch(root: Path, overlay: Path)->None:
    root=root.resolve()
    sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,
                                text=True,stderr=subprocess.DEVNULL).strip()
    if sha!=PRIVATE_SHA:raise RuntimeError("TX777_PRIVATE_SHA_MISMATCH")
    modifications=[]
    for rel,operation in ((ONEFILE/"main_windows.go",transform_bootstrap),
                          (HOST/"rpg_dashboard_windows.go",transform_dashboard)):
        dest=root/rel
        if not dest.is_file() or dest.is_symlink():
            raise RuntimeError("TX777_EXPECTED_PRIVATE_FILE_NOT_REGULAR")
        raw=dest.read_bytes()
        if b"\r" in raw:raise RuntimeError("TX777_PRIVATE_SOURCE_LINE_ENDINGS_CHANGED")
        changed=operation(raw.decode("utf-8")).encode("utf-8")
        if changed==raw:raise RuntimeError("TX777_NO_SOURCE_CHANGE")
        modifications.append((dest,changed))
    for name in FILES:
        source=overlay/name
        dest=root/ONEFILE/name
        if not source.is_file() or source.is_symlink() or dest.exists():
            raise RuntimeError("TX777_PUBLIC_OVERLAY_INVALID_OR_ALREADY_EXISTS")
        raw=source.read_bytes().replace(b"\r\n",b"\n")
        if b"\r" in raw or b"package main" not in raw:
            raise RuntimeError("TX777_UNEXPECTED_GO_OVERLAY_FORMAT")
        modifications.append((dest,raw))
    for dest,raw in modifications:
        dest.write_bytes(raw)
    print("TX777_FULL_NATIVE_WINDOWS_LAUNCHER_REPLACES_V95_MODAL_AND_PREFILLS_INSTALLER")

def self_test()->None:
    assert replace_once("ABC","B","X","TEST")=="AXC"
    for bad in ("AAA","NO"):
        try:replace_once(bad,"B","X","TEST")
        except RuntimeError:pass
        else:raise AssertionError("TX777_UNSAFE_SOURCE_REPLACER")
    print("TX777_SOURCE_FREE_NO_MODAL_GUI_PATCHER_PASS")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--source-root",type=Path)
    p.add_argument("--overlays",type=Path)
    arg=p.parse_args()
    if arg.self_test:self_test()
    if arg.source_root:
        if not arg.overlays:p.error("--overlays required")
        self_test()
        patch(arg.source_root,arg.overlays)
    if not arg.self_test and not arg.source_root:
        p.error("use --self-test or --source-root with --overlays")
if __name__=="__main__":main()
