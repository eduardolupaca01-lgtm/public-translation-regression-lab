#!/usr/bin/env python3
"""Read-only source-pinned integration of safe preparation-stage diagnostics.

Operates ONLY on the disposable CI checkout of the original V95 source,
never changes historical repositories or the user's game. Model hashes,
installation, rollback gates, and runtime behavior are unchanged.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil

ROOT = Path("reference/tx541-rpg-onefile")
GUI = "tx777_bootstrap_ui_windows.go"
PREPARE = "tx771_portable_windows.go"
GO_FILES = (
    "servidor_preparacion_diagnostico_windows.go",
    "servidor_preparacion_diagnostico_windows_test.go",
)

def swap(source: str, old: str, new: str, expected: int = 1) -> str:
    count = source.count(old)
    if count != expected:
        raise RuntimeError("SERVIDOR_DIAG_ORIGINAL_SOURCE_DRIFT")
    return source.replace(old,new,1)

def panel(source: str) -> str:
    original = '''        event.failed=true
        event.code="TX777_ERROR_NO_CLASIFICADO"
        if x:=tx777StageCode.FindString(strings.ToUpper(err.Error()));x!=""{event.code=x}
        event.desc="La preparación se detuvo. No borres modelos, caché ni copias anteriores; copia este diagnóstico. Los detalles privados se han ocultado."'''
    replacement = '''        event.failed=true
        event.code,event.desc=servidorClassifyPreparationFailure(err)'''
    return swap(source,original,replacement)

def portable(source: str) -> str:
    if source.count("func tx771PreparePortableOnefile(")!=1:
        raise RuntimeError("SERVIDOR_DIAG_PREPARE_FUNCTION_MISSING")
    head,body=source.split("func tx771PreparePortableOnefile(",1)
    # TX772 runs FIRST in CI and replaces the old sidecar branch with its
    # verified owner-only upgrade path. We must not match removed legacy code.
    if body.count("return tx772UpgradeOwnedPortable(payload,gameRoot)") != 1:
        raise RuntimeError("SERVIDOR_DIAG_TX772_UPGRADE_SOURCE_REQUIRED")
    body=swap(body,
        '}else if !os.IsNotExist(err){return "","",err}',
        '}else if !os.IsNotExist(err){return "","",fmt.Errorf("TX778_CARPETA_PORTATIL_INACCESIBLE: %w",err)}')
    body=swap(body,
        'stage,err:=os.MkdirTemp(gameRoot,".tx771-onefile-stage-")\n    if err!=nil{return "","",err}',
        'stage,err:=os.MkdirTemp(gameRoot,".tx771-onefile-stage-")\n    if err!=nil{return "","",fmt.Errorf("TX778_CARPETA_PORTATIL_NO_DISPONIBLE: %w",err)}')
    body=swap(body,
        'stagedApp,err:=installPrivateAppIn(payload,stagingAppRoot)\n    if err!=nil{return "","",err}',
        'stagedApp,err:=installPrivateAppIn(payload,stagingAppRoot)\n    if err!=nil{return "","",fmt.Errorf("TX778_EXTRAER_APLICACION_FALLIDO: %w",err)}')
    body=swap(body,
        'if err=ensureOriginalEngineAt(stagedApp,stagedEngine);err!=nil{return "","",err}',
        'if err=ensureOriginalEngineAt(stagedApp,stagedEngine);err!=nil{return "","",fmt.Errorf("TX778_INSTALAR_MOTOR_FALLIDO: %w",err)}')
    body=swap(body,
        'workerSHA,err:=shaFile(filepath.Join(stagedEngine,"engine","TenshixgameAI.exe"))\n    if err!=nil{return "","",err}',
        'workerSHA,err:=shaFile(filepath.Join(stagedEngine,"engine","TenshixgameAI.exe"))\n    if err!=nil{return "","",fmt.Errorf("TX778_HUELLA_MOTOR_FALLIDA: %w",err)}')
    body=swap(body,
        'raw,err:=json.Marshal(owner);if err!=nil{return "","",err}',
        'raw,err:=json.Marshal(owner);if err!=nil{return "","",fmt.Errorf("TX778_CODIFICAR_MARCADOR_FALLIDO: %w",err)}')
    body=swap(body,
        'if err=os.WriteFile(filepath.Join(stage,"portable-owner-v1.json"),raw,0600);err!=nil{\n        return "","",err\n    }',
        'if err=os.WriteFile(filepath.Join(stage,"portable-owner-v1.json"),raw,0600);err!=nil{\n        return "","",fmt.Errorf("TX778_GUARDAR_MARCADOR_FALLIDO: %w",err)\n    }')
    old_verify='if err=verifyDirectory(appDir,payload);err!=nil{return "","",err}'
    body=swap(body,old_verify,
        'if err=verifyDirectory(appDir,payload);err!=nil{return "","",fmt.Errorf("TX778_VERIFICAR_PAQUETE_PUBLICADO_FALLIDO: %w",err)}')
    body=swap(body,
        'if _,err=tx771OwnerFile(marker);err!=nil{return "","",err}',
        'if _,err=tx771OwnerFile(marker);err!=nil{return "","",fmt.Errorf("TX778_VERIFICAR_PROPIETARIO_PUBLICADO_FALLIDO: %w",err)}')
    if body.count("TX778_")<9:
        raise RuntimeError("SERVIDOR_DIAG_MISSING_PHASE_INSTRUMENTATION")
    return head+"func tx771PreparePortableOnefile("+body

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--source-root",type=Path)
    parser.add_argument("--overlays",type=Path)
    args=parser.parse_args()
    if args.self_test:
        original=Path(__file__).resolve().parents[1]/"tx777"/GUI
        transformed=panel(original.read_text(encoding="utf-8"))
        assert "servidorClassifyPreparationFailure(err)" in transformed
        assert 'event.code="TX777_ERROR_NO_CLASIFICADO"' not in transformed
        assert all(".." not in x for x in GO_FILES)
        print("SERVIDOR_PREPARACION_DIAGNOSTICO_SOURCE_PREFLIGHT_PASS")
        return
    if not args.source_root or not args.overlays:
        parser.error("--source-root and --overlays required")
    root=args.source_root/ROOT
    gui=root/GUI
    prep=root/PREPARE
    if not gui.is_file() or not prep.is_file():
        raise RuntimeError("SERVIDOR_DIAG_AUTHENTIC_V95_SOURCE_REQUIRED")
    for file in GO_FILES:
        if not (args.overlays/file).is_file() or (root/file).exists():
            raise RuntimeError("SERVIDOR_DIAG_OVERLAY_INVALID")
    # Generate both outputs and validate their exact contracts BEFORE writing.
    updated_gui=panel(gui.read_text(encoding="utf-8"))
    updated_prep=portable(prep.read_text(encoding="utf-8"))
    gui.write_text(updated_gui,encoding="utf-8")
    prep.write_text(updated_prep,encoding="utf-8")
    for file in GO_FILES:
        shutil.copyfile(args.overlays/file,root/file)
    print("SERVIDOR_PREPARACION_DIAGNOSTICOS_SEGUROS_ACTIVADOS")

if __name__=="__main__":
    main()
