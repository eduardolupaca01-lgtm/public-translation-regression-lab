#!/usr/bin/env python3
"""TX776 fail-closed installer diagnostics overlay for ORIGINAL V95 Windows.

Only the exact private SHA checkout is modified, and only in the temporary
Actions runner. Public files are source-free adapters + tests. Neither model
weights, game paths nor original source are published to the public branch.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

SOURCE_SHA="aeb9ff9326e418fbabe2d53dff7891f4fb340c37"
BASE=Path("reference/tx331-clean-product-host/cmd/tenshixgame-ui")
DASH=BASE/"rpg_dashboard_windows.go"
INSTALL=BASE/"rpg_install_windows.go"
PORTABLE=BASE/"rpg_portable_tx771_windows.go"
OVERLAYS=("tx776_installer_diagnostics_windows.go","tx776_installer_diagnostics_windows_test.go")

def replace_once(source: str, before: str, after: str, label: str)->str:
    count=source.count(before)
    if count!=1:
        raise RuntimeError(f"TX776_UNRECOGNIZED_PRIVATE_SOURCE_{label}_{count}")
    return source.replace(before,after,1)

def dashboard(original:str)->str:
    s=original
    s=replace_once(s,"rpgIDInstall=103","rpgIDInstall=103\n    rpgIDCopyDiagnostic=104","COPY_BUTTON_ID")
    s=replace_once(s,"rpgDashboardWindowHeight=690","rpgDashboardWindowHeight=735","GUI_HEIGHT")
    s=replace_once(s,"rpgDashboardFooterY=618","rpgDashboardFooterY=670","GUI_FOOTER")
    s=replace_once(s,"func rpgApplyInstallResponse()bool{\n    select{",
        "func rpgApplyInstallResponse()bool{\n    tx776DrainEvents()\n    select{","DRAIN_BEFORE_COMPLETE")
    s=replace_once(s,
'''        if response.err!=nil{
            rpgStatus("No se instaló el traductor: "+response.err.Error())
        }else{
            rpgState.completed=true
            rpgStatus(response.text)
        }''',
'''        if response.err!=nil{
            code,advice:=tx776ExplainError(response.err)
            tx776Append(code,advice)
        }else{
            rpgState.completed=true
            tx776Append("TX776_INSTALACION_VERIFICADA",response.text)
        }''',"ERROR_REPORT")
    s=replace_once(s,
'''    case rpgWMCommand:
        if rpgState.busy{return 0}
        switch uint16(wparam&0xffff){''',
'''    case rpgWMCommand:
        // Copy remains available even while the installer is running.
        if uint16(wparam&0xffff)==rpgIDCopyDiagnostic{
            tx776CopyReport()
            return 0
        }
        if rpgState.busy{return 0}
        switch uint16(wparam&0xffff){''',"COPY_EVENT")
    s=replace_once(s,
'''            rpgStatus("Comprobando el motor V95 original, los modelos y los complementos del juego. La ventana continuará abierta...")''',
'''            tx776StartReport()
            tx776Append("TX776_INICIO","Comprobando motor V95 original, modelos, integridad y puente del juego. Ventana activa; juego cerrado.")''',"START_REPORT")
    s=replace_once(s,
'''    response.text,response.err=rpgInstallWorker(gamePath)''',
'''    tx776StageEvent("TX776_TRABAJO_INICIADO","El instalador inició la comprobación en segundo plano.")
    response.text,response.err=rpgInstallWorker(gamePath)
    if response.err==nil {
        tx776StageEvent("TX776_TRABAJO_TERMINADO","El instalador devolvió un resultado. Verificando el estado final.")
    }''',"WORKER_EVENTS")
    s=replace_once(s,
'''            if !rpgApplyInstallResponse() && !rpgState.startedAt.IsZero(){''',
'''            tx776DrainEvents()
            if !rpgApplyInstallResponse() && !rpgState.startedAt.IsZero(){''',"TIMER_EVENTS")
    s=replace_once(s,
'''                    rpgStatus(fmt.Sprintf("Instalación en curso (%d s de actividad). La ventana sigue respondiendo; no cierres el juego hasta terminar.",elapsed))''',
'''                    tx776Append("TX776_EN_CURSO",fmt.Sprintf("Instalación en curso (%d s). No cierres esta ventana ni abras el videojuego hasta terminar.",elapsed))''',"HEARTBEAT_APPEND")
    s=replace_once(s,
'''            rpgStatus("Instalación en curso. Espera a que termine para cerrar sin interrumpir el respaldo.")''',
'''            tx776Append("TX776_CIERRE_BLOQUEADO","La instalación está trabajando. Cerrar ahora podría interrumpir el respaldo; finaliza primero.")''',"CLOSE_DOES_NOT_CLEAR")
    s=replace_once(s,
'''    rpgUIControl(hwnd,"STATIC","V95 local incluido · Sin cuentas, Python, Ollama ni API · F10 en juegos compatibles",''',
'''    rpgUIControl(hwnd,"BUTTON","COPIAR DIAGNÓSTICO PARA ENVIAR",rpgWSTabstop,0,
        27,611,648,40,rpgIDCopyDiagnostic)
    rpgUIControl(hwnd,"STATIC","V95 local incluido · Sin cuentas, Python, Ollama ni API · F10 en juegos compatibles",''',"VISUAL_COPY_BUTTON")
    s=replace_once(s,
'''    rpgUIControl(hwnd,"STATIC","Estado de instalación:",0,0,28,330,640,27,0)''',
'''    rpgUIControl(hwnd,"STATIC","Estado de instalación y diagnóstico acumulado:",0,0,28,330,640,27,0)''',"PANEL_TITLE")
    return s

def install(original:str)->str:
    s=original
    s=replace_once(s,
'''    exe,err:=rpgResolveSelection(selection)
    if err!=nil{return "",err}''',
'''    tx776StageEvent("TX776_VERIFICANDO_JUEGO","Comprobando la ruta y la presencia de un ejecutable normal de una copia del juego.")
    exe,err:=rpgResolveSelection(selection)
    if err!=nil{return "",err}
    tx776StageEvent("TX776_JUEGO_SELECCIONADO","Ejecutable del juego reconocido. Ruta personal omitida del informe.")''',"SELECT_GAME")
    s=replace_once(s,
'''    inspected,err:=cleanhost.InspectGameEngine(exe)''',
'''    tx776StageEvent("TX776_DETECTANDO_MOTOR","Detectando la variante del motor RPG sin ejecutar el juego.")
    inspected,err:=cleanhost.InspectGameEngine(exe)''',"ENGINE_DETECT")
    s=replace_once(s,
'''    engine,err:=engineRoot()
    if err!=nil{return "",err}''',
'''    tx776StageEvent("TX776_MOTOR_COMPATIBLE","RPG Maker MV/MZ detectado. Comprobando la IA neuronal original.")
    engine,err:=engineRoot()
    if err!=nil{return "",err}''',"ENGINE_ROOT")
    s=replace_once(s,
'''    if _,err=cleanhost.VerifyInstalledIntegrity(engine);err!=nil{''',
'''    tx776StageEvent("TX776_VERIFICANDO_BINARIOS","Verificando el motor V95 y los hashes del paquete original.")
    if _,err=cleanhost.VerifyInstalledIntegrity(engine);err!=nil{''',"ENGINE_HASHES")
    s=replace_once(s,
'''    if err=cleanhost.VerifyRPGOriginalModelIntegrityForSelectedGame(engine,inspected.GameRoot);err!=nil{''',
'''    tx776StageEvent("TX776_VERIFICANDO_MODELOS","Comprobando que los modelos de traducción originales están íntegros.")
    if err=cleanhost.VerifyRPGOriginalModelIntegrityForSelectedGame(engine,inspected.GameRoot);err!=nil{''',"MODEL_VERIFY")
    s=replace_once(s,
'''    if err=tx771EnsurePortableEngine(inspected.GameRoot);err!=nil{''',
'''    tx776StageEvent("TX776_IA_EN_CARPETA","Preparando la IA completa dentro de la carpeta del juego. No utiliza un servicio global.")
    if err=tx771EnsurePortableEngine(inspected.GameRoot);err!=nil{''',"ENGINE_PORTABLE")
    s=replace_once(s,
'''    workspace,err:=gameWorkspace(inspected.GameRoot,"rpgmaker-mv-mz","auto")''',
'''    tx776StageEvent("TX776_PORTATIL_VERIFICADO","El motor del juego pasó las comprobaciones de instalación portátil.")
    workspace,err:=gameWorkspace(inspected.GameRoot,"rpgmaker-mv-mz","auto")''',"WORKSPACE")
    s=replace_once(s,
'''    err = rpgInstallWithJournalDiagnosticsAndEvidence(''',
'''    tx776StageEvent("TX776_REVISANDO_RESPALDO","Verificando diario, respaldo y plugins anteriores antes de modificar el registro.")
    err = rpgInstallWithJournalDiagnosticsAndEvidence(''',"JOURNAL")
    s=replace_once(s,
'''    if result.Status=="UPGRADED_VERIFIED" {''',
'''    tx776StageEvent("TX776_PUENTE_VERIFICADO","El complemento de diálogos fue instalado/verificado y mantiene opciones, nombres y códigos del juego.")
    if result.Status=="UPGRADED_VERIFIED" {''',"PLUGIN_RECEIPT")
    return s

def portable(original:str)->str:
    s=original
    s=replace_once(s,
'''    if err=tx771PlainDir(sidecar);err==nil{''',
'''    if err=tx771PlainDir(sidecar);err==nil{
        tx776StageEvent("TX776_INSTALACION_EXISTENTE","Carpeta portátil existente: verificando propietario, modelos y SHA sin sobrescribir archivos desconocidos.")''',"EXISTING_OWNER")
    s=replace_once(s,
'''    stage,err:=os.MkdirTemp(filepath.Dir(sidecar),".tx771-stage-")''',
'''    tx776StageEvent("TX776_PREPARANDO_COPIA","Preparando el modelo neuronal en el disco del juego. Se preserva la carpeta anterior ante un error.")
    stage,err:=os.MkdirTemp(filepath.Dir(sidecar),".tx771-stage-")''',"STAGE_CREATE")
    s=replace_once(s,
'''    if err=cmd.Run();err!=nil{return fmt.Errorf("TX771_PORTABLE_ENGINE_INSTALL_FAILED: %w",err)}''',
'''    tx776StageEvent("TX776_COPIANDO_MODELO","Instalando y verificando archivos del motor V95; esta etapa puede tardar.")
    if err=cmd.Run();err!=nil{return fmt.Errorf("TX771_PORTABLE_ENGINE_INSTALL_FAILED: %w",err)}''',"STAGE_EXECUTE")
    s=replace_once(s,
'''    if err=os.Rename(stage,sidecar);err!=nil{''',
'''    tx776StageEvent("TX776_PUBLICACION_ATOMICA","Motor y modelos comprobados. Publicando la instalación portátil de forma atómica.")
    if err=os.Rename(stage,sidecar);err!=nil{''',"PUBLISH")
    return s

def self_test() -> None:
    if replace_once("A","A","B","CASE")!="B":raise AssertionError("TX776_REPLACER_NOT_WORKING")
    for broken in ("no anchor","AA"):
        try:replace_once(broken,"A","B","CASE")
        except RuntimeError:pass
        else:raise AssertionError("TX776_SOURCE_ANCHOR_FAIL_OPEN")
    for maker in (dashboard,install,portable):
        if not callable(maker):raise AssertionError("TX776_MISSING_PRIVATE_TRANSFORM")
    print("TX776_SOURCE_PINNED_INSTALL_DIAGNOSTICS_PRECHECK_PASS")

def patch_private(root:Path,overlays:Path) ->None:
    root=root.resolve()
    actual=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,
                                  text=True,stderr=subprocess.DEVNULL).strip()
    if actual!=SOURCE_SHA:raise RuntimeError("TX776_PRIVATE_SOURCE_SHA_MISMATCH")
    overlay=overlays.resolve()
    planned=[]
    for file,transform in ((DASH,dashboard),(INSTALL,install),(PORTABLE,portable)):
        target=root/file
        if not target.is_file() or target.is_symlink():
            raise RuntimeError("TX776_ORIGINAL_WINDOWS_INSTALL_SOURCE_MISSING")
        original=target.read_bytes()
        if b"\r" in original:raise RuntimeError("TX776_UNEXPECTED_CRLF_IN_PRIVATE_WINDOWS_SOURCE")
        updated=transform(original.decode("utf-8")).encode("utf-8")
        if updated==original:raise RuntimeError("TX776_INSTALL_PATCH_NOOP")
        planned.append((target,updated))
    for filename in OVERLAYS:
        origin=overlay/filename
        dest=root/BASE/filename
        if not origin.is_file() or origin.is_symlink() or dest.exists():
            raise RuntimeError("TX776_OVERLAY_SOURCE_MISSING_OR_ALREADY_PRESENT")
        # A public Go file can be checked out by Windows with CRLF while
        # the immutable private source uses LF. Normalize ONLY new overlays.
        payload=origin.read_bytes().replace(b"\r\n",b"\n")
        if b"\r" in payload:
            raise RuntimeError("TX776_PUBLIC_OVERLAY_NONSTANDARD_LINE_ENDINGS")
        if b"package main" not in payload:
            raise RuntimeError("TX776_PUBLIC_OVERLAY_GO_PACKAGE_MISSING")
        planned.append((dest,payload))
    # No file is touched unless ALL source pins and anchors have passed.
    for dest,payload in planned:
        dest.write_bytes(payload)
    print("TX776_PRIVATE_OWNER_WINDOWS_INSTALLER_DIAGNOSTIC_OVERLAY_APPLIED")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--source-root",type=Path)
    p.add_argument("--overlays",type=Path)
    opts=p.parse_args()
    if opts.self_test:self_test()
    if opts.source_root:
        if not opts.overlays:p.error("--source-root requires --overlays")
        self_test()
        patch_private(opts.source_root,opts.overlays)
    if not opts.self_test and not opts.source_root:
        p.error("use --self-test or --source-root with --overlays")
if __name__=="__main__":main()
