#!/usr/bin/env python3
"""Fast native Windows launcher preflight, not an OPUS inference test."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

BUILD = "VXACE-RGSS3-20261126-D"

def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()

def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, timeout=60, **kwargs)

def wait_code(path, code):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            if json.loads(path.read_text("utf8")).get("code") == code:
                return
        except (OSError, ValueError):
            pass
        time.sleep(.1)
    raise AssertionError("IA_VXACE_PROBE_CHILD_DID_NOT_START")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", type=Path, required=True)
    a = p.parse_args()
    target = a.target.resolve(strict=True)
    source = Path(__file__).resolve().parents[1]/"vxace"/"IATraductoraVXACE.rb"
    harness = Path(__file__).with_name("test_vxace_runtime.rb").resolve()
    with tempfile.TemporaryDirectory(prefix="IA VX Ace 日本語 ") as tmp:
        root = Path(tmp)/"Juego con espacios 日本語"
        run([target/"examples"/"vxace_fixture.exe", "create", root, "loose"])
        sidecar = root/"IA Traductora"
        rpg = sidecar/".local"/"Rpg"
        engine = rpg/"engine"
        (engine/"vxace").mkdir(parents=True)
        (sidecar/"install").mkdir()
        helper = engine/"vxace-helper.exe"
        worker = engine/"IATraductora.exe"
        plugin = engine/"vxace"/"IATraductoraVXACE.rb"
        shutil.copyfile(target/"servidor-vxace-helper.exe", helper)
        shutil.copyfile(target/"examples"/"vxace_launch_probe.exe", worker)
        shutil.copyfile(source, plugin)
        scripts = root/"Data"/"Scripts.rvdata2"
        before = digest(scripts)
        staged = rpg/"staged.rvdata2"
        run([helper, "install", "--game-root", root, "--plugin", plugin, "--output", staged])
        staged.replace(scripts)
        owner = {"schema":"ia-traductora-owner-v1","product":"SERVIDOR-IA-TRADUCTORA",
                 "vxace_plugin_build":BUILD,"worker_sha256":digest(worker),
                 "vxace_helper_sha256":digest(helper),"vxace_plugin_sha256":digest(plugin)}
        receipt = {"schema":"ia-traductora-vxace-install-v1","status":"INSTALLED","build":BUILD,
                   "target_rel":"Data/Scripts.rvdata2","mode":"loose",
                   "before_sha256":before,"after_sha256":digest(scripts),
                   "worker_sha256":digest(worker),"helper_sha256":digest(helper),
                   "plugin_sha256":digest(plugin)}
        (sidecar/"owner-v1.json").write_text(json.dumps(owner), encoding="utf8")
        (sidecar/"install"/"vxace-receipt.json").write_text(json.dumps(receipt), encoding="utf8")
        parent = os.getpid()
        # Deliberately not launched with cwd=root; helper must derive root from itself.
        run([helper,"launch-worker","--parent-pid",str(parent)],cwd=tmp)
        wait_code(rpg/f"vxace-startup-worker-{parent}.json","IA_VXACE_PROBE_READY")
        assert (rpg/f"vxace-startup-helper-{parent}.txt").read_text("ascii").strip()=="IA_VXACE_WORKER_SPAWNED"
        print("IA_VXACE_HELPER_UNICODE_NATIVE_CHILD_PASS")
        run(["ruby",harness,"--launch-probe",root])
        # A modified plugin must not be allowed to start a child.
        with plugin.open("ab") as stream:
            stream.write(b"\n# altered\n")
        failed = subprocess.run([str(helper),"launch-worker","--parent-pid",str(parent)],
                                cwd=tmp, capture_output=True,timeout=30)
        assert failed.returncode!=0
        assert (rpg/f"vxace-startup-helper-{parent}.txt").read_text("ascii").strip()=="IA_VXACE_RUNTIME_SHA_INVALIDO"
        print("IA_VXACE_LAUNCH_TAMPER_REFUSED_PASS")

if __name__=="__main__":
    main()
