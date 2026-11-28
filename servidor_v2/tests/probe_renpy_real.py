"""Installed client -> packaged real OPUS worker, both transports.
Synthetic layouts, no player data and no assertion of universal SDK coverage."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

SIDE="IA Traductora RenPy"
SAMPLES=(
    ("Thank you for your help.",r"gracias|agradezco|ayuda|asistencia"),
    ("おはようございます。",r"buenos|buen|días|día|hola"),
    ('"Thank you for your help."',r"gracias|agradezco|ayuda|asistencia"),
    ("{b}Thank you for your help.{/b} [player_name]",r"gracias|agradezco|ayuda|asistencia"),
)
def command(exe,*args):
    proc=subprocess.run([str(exe),*map(str,args)],capture_output=True,timeout=180)
    if proc.returncode:raise RuntimeError("Installer command failed: "+str(proc.returncode))
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def wait_until(predicate,seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return True
        time.sleep(.2)
    return False
def probe(exe,root,classic):
    game=root/"game";game.mkdir(parents=True)
    runtime=root/"renpy";runtime.mkdir()
    (root/"lib").mkdir()
    version="4.8.7" if classic else "8.3.7"
    (runtime/"__init__.py").write_text("version = \"Ren'Py "+version+"\"\n",encoding="ascii")
    module=runtime/("display" if classic else "text");module.mkdir()
    (module/"text.py").write_text("# synthetic layout only\n",encoding="ascii")
    original=game/"script.rpy"
    original.write_text('label start:\n    "Original script"\n',encoding="utf-8")
    saves=game/"saves";saves.mkdir()
    sentinel=saves/"example.save";sentinel.write_bytes(b"synthetic-save-preservation")
    launcher=root/"Game.exe";launcher.write_bytes(b"MZsynthetic-layout-only")
    hashes={path:sha(path) for path in (original,sentinel,launcher,runtime/"__init__.py")}
    command(exe,"--renpy-inspect","--game",launcher)
    command(exe,"--renpy-install","--game",launcher)
    side=root/SIDE
    receipt=json.loads((side/"owner-v1.json").read_text("utf-8"))
    profile="classic" if classic else "modern"
    assert receipt["profile"]==profile,receipt["profile"]
    assert sha(side/"client.py")==receipt["client_sha256"]
    hook=game/"zz_ia_servidor_renpy.rpy" if classic else game/"ia_servidor_renpy"/"boot.rpy"
    assert sha(hook)==receipt["boot_sha256"]
    spec=importlib.util.spec_from_file_location("ia_acceptance_client",side/"client.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    client=m.Client(str(root))
    def request(source):
        end=time.monotonic()+100
        while time.monotonic()<end:
            value=client.translate(source)
            if value!=source:return value
            time.sleep(.5)
        raise AssertionError("No accepted translation from real packaged worker")
    try:
        for source,expected in SAMPLES:
            target=request(source)
            assert re.search(expected,target,re.I),repr(target)
            if "[" in source:assert "[player_name]" in target and "{b}" in target and "{/b}" in target
            if '"' in source:assert target.count('"')==source.count('"')
        first=SAMPLES[0][0];before=request(first);assert request(first)==before
        state=json.loads((side/"status.json").read_text("utf-8"))
        assert state["translated"]>=len(SAMPLES),state
        with sqlite3.connect(side/"memory-v1.sqlite3") as db:
            rows=db.execute("SELECT original,output FROM memory").fetchall()
        assert all(any(x==source and y!=source for x,y in rows) for source,_ in SAMPLES)
        assert all(sha(path)==digest for path,digest in hashes.items())
        print("REAL_RENPY_PACKAGED_OPUS",profile,"PASS",flush=True)
    finally:client.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--servidor",type=Path,required=True)
    p.add_argument("--child",choices=["classic","modern"])
    p.add_argument("--root",type=Path)
    args=p.parse_args()
    exe=args.servidor.resolve()
    if args.child:
        probe(exe,args.root,args.child=="classic")
        return
    with tempfile.TemporaryDirectory(prefix="ia-renpy-real-",ignore_cleanup_errors=True) as folder:
        for profile in ("modern","classic"):
            root=Path(folder)/profile
            child=subprocess.run([sys.executable,__file__,"--servidor",str(exe),"--child",profile,"--root",str(root)],timeout=650)
            if child.returncode:raise RuntimeError("Real worker integration failed: "+profile)
            side=root/SIDE
            if not wait_until(lambda:not list(side.glob("session-*.json")) and not list(side.glob("classic-session-*")),90):
                raise RuntimeError("Worker session did not close after parent exited: "+profile)
            original=root/"game"/"script.rpy";save=root/"game"/"saves"/"example.save"
            before=(sha(original),sha(save),sha(root/"Game.exe"))
            command(exe,"--renpy-recover","--game",root/"Game.exe")
            hook=root/"game"/("zz_ia_servidor_renpy.rpy" if profile=="classic" else "ia_servidor_renpy")
            assert not hook.exists()
            assert before==(sha(original),sha(save),sha(root/"Game.exe"))
            assert (side/"memory-v1.sqlite3").is_file()
            print("REAL_RENPY_RECOVERY_PRESERVED",profile,flush=True)
if __name__=="__main__":main()
