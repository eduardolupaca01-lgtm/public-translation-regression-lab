#!/usr/bin/env python3
"""Prueba Windows segura: argv real, sin consola, sin texto ni token en logs."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from probe_new_worker import read_bridge, run as prove_spanish

def diagnostic(file: Path) -> str:
    if not file.is_file() or file.is_symlink() or file.stat().st_size > 512:
        return "IA_BOOTSTRAP_O_ARGUMENTOS_FALLIDOS"
    try:
        doc = json.loads(file.read_text(encoding="utf8"))
    except (ValueError, OSError):
        return "IA_DIAGNOSTICO_FORMATO_INVALIDO"
    code = doc.get("code") if doc.get("schema") == "ia-traductora-startup-v1" else None
    return code if isinstance(code, str) and re.fullmatch(r"IA_[A-Z_]{4,90}", code) else "IA_DIAGNOSTICO_INVALIDO"

def launch(exe: Path, arguments: list[str], diagnostic_file: Path, timeout: int) -> int:
    opts = {
        "cwd": str(exe.parent),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }
    proc = subprocess.Popen([str(exe), *arguments, "--diagnostic-file",
                             str(diagnostic_file)], **opts)
    try:
        if "--check-models" in arguments:
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print("IA_FROZEN_MODEL_LOAD_TIMEOUT")
                return 1
            status = diagnostic(diagnostic_file)
            print("IA_SAFE_FROZEN_LOAD_CATEGORY=" + status)
            return 0 if code == 0 and status == "IA_MODELOS_REALES_CT2_LISTOS" else 1
        if "--game-root" not in arguments:
            print("IA_GAME_ROOT_NO_ESPECIFICADO")
            return 1
        game = Path(arguments[arguments.index("--game-root") + 1]).resolve(strict=True)
        bridge = game / "www" / "data" / "IATraductora" / "bridge.json"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                print("IA_SAFE_GAME_BOOT_CATEGORY=" + diagnostic(diagnostic_file))
                return 1
            if read_bridge(bridge) is not None:
                try:
                    prove_spanish(game)
                    return 0
                except Exception:
                    print("IA_REAL_JA_ES_HTTP_NO_VALIDADO")
                    return 1
            time.sleep(0.4)
        print("IA_SAFE_GAME_BOOT_CATEGORY=" + diagnostic(diagnostic_file))
        return 1
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=4)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--game-root", type=Path)
    parser.add_argument("--diagnostic-file", type=Path, required=True)
    parser.add_argument("--check-models", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=150)
    args = parser.parse_args()
    if os.name != "nt" or not args.worker.is_file() or not args.worker.name == "IATraductora.exe":
        print("IA_WORKER_WINDOWS_FUENTE_INVALIDA")
        return 1
    if args.check_models:
        argv = ["--check-models"]
    elif args.game_root:
        argv = ["--game-root", str(args.game_root.resolve(strict=True)),
                "--parent-pid", str(os.getpid())]
    else:
        print("IA_WORKER_ARGUMENTOS_INVALIDOS")
        return 1
    if not 15 <= args.timeout_seconds <= 300:
        print("IA_TIEMPO_PRUEBA_NO_ADMITIDO")
        return 1
    try:
        return launch(args.worker.resolve(strict=True), argv,
                      args.diagnostic_file, args.timeout_seconds)
    except Exception:
        print("IA_INICIO_WINDOWS_NO_CLASIFICADO")
        return 1

if __name__ == "__main__":
    sys.exit(main())
