"""Exact reported Ren'Py 7.3.2.320, actual installed boot, original EXE.
Preflight: original archive-only fixture and real hook initialization.
Final acceptance: genuine packaged OPUS via the game process itself.
No player files, no game-specific substitutions or seeded translations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import tempfile
import time
import zlib

ASSETS=Path(__file__).resolve().parents[1]/"cmd/servidor/renpy_assets"
SIDE="IA Traductora RenPy"
SCRIPT=r'''
define config.name = "Servidor R45 Native 7.3.2 Probe"
define config.save_directory = "ServidorR45Native732Lab"
define config.sound = False

label main_menu:
    return

label start:
    python:
        import os
        import sys
        import traceback
        import time
        import re
        import __builtin__ as py_builtins
        try:
            import renpy as engine
            module=sys.modules.get("_ia_servidor_renpy_r1")
            if module is None or getattr(module,"active_client",None) is None:
                raise RuntimeError("Installed boot did not activate")
            if str(engine.version_only)!="7.3.2.320":
                raise RuntimeError("Unexpected SDK version "+str(engine.version_only))
            native=engine.text.text.Text
            if getattr(native.set_text,"__module__","")!=module.__name__:
                raise RuntimeError("Native Text hook missing")
            if not engine.config.say_menu_text_filter:
                raise RuntimeError("Say/menu hook missing")
            mode=os.environ["IA_RENPY_NATIVE_MODE"]
            if mode=="real":
                c=module.active_client
                deadline=time.time()+90
                while time.time()<deadline and not c.get_session(module.CLOCK()+10):
                    time.sleep(.5)
                if not c.connection:
                    raise RuntimeError("Packaged worker did not connect")
                pairs=[(u"Thank you for your help.",u"gracias|agradezco|ayuda|asistencia"),
                       (u"\u304a\u306f\u3088\u3046\u3054\u3056\u3044\u307e\u3059\u3002",u"buenos|buen|d\u00edas|d\u00eda|hola"),
                       (u'{b}"Thank you for your help."{/b}',u"gracias|agradezco|ayuda|asistencia")]
                for original,pattern in pairs:
                    displayable=native(original)
                    value=displayable.text
                    if isinstance(value,(py_builtins.list,py_builtins.tuple)):
                        if len(value)!=1:raise RuntimeError("Unexpected native text sequence")
                        value=value[0]
                    if value==original or not re.search(pattern,value,re.I):
                        raise RuntimeError("Native text was not translated: "+repr(value))
                    if "{" in original and ("{b}" not in value or "{/b}" not in value or value.count('"')!=2):
                        raise RuntimeError("Formatting/quotes lost")
                source=u"Thank you for your help."
                target=engine.config.say_menu_text_filter(source)
                if target==source or not re.search(u"gracias|agradezco|ayuda|asistencia",target,re.I):
                    raise RuntimeError("Say/menu filter did not translate")
                from renpy.display.behavior import Input
                if Input(default=source).content!=source:
                    raise RuntimeError("Player input modified")
            report=open(os.environ["IA_RENPY_NATIVE_RESULT"],"wb")
            try:report.write(("NATIVE_INSTALLED_732_"+mode.upper()+"_OK").encode("ascii"))
            finally:report.close()
        except Exception:
            report=open(os.environ["IA_RENPY_NATIVE_ERROR"],"wb")
            try:report.write(traceback.format_exc().encode("utf-8","backslashreplace"))
            finally:report.close()
    $ renpy.quit()
    return
'''
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def archive(path,name,content):
    # Original synthetic data only. Official RPA-3.0 format with two-item
    # index tuples; the native SDK owns loading the compiled .rpyc.
    key=0x12345678
    head=("RPA-3.0 %016x %08x\n"%(0,key)).encode("ascii")
    index={name:[(len(head)^key,len(content)^key)]}
    head=("RPA-3.0 %016x %08x\n"%(len(head)+len(content),key)).encode("ascii")
    path.write_bytes(head+content+zlib.compress(pickle.dumps(index,protocol=2)))

def command(exe,*args):
    p=subprocess.run([str(exe),*map(str,args)],capture_output=True,timeout=180)
    if p.returncode:raise RuntimeError("Installer/SDK command failed: "+str(p.returncode)+" "+p.stderr.decode("utf-8","replace")[-1500:])

def diagnostics(root,result):
    for path in [result/"error.txt",root/"traceback.txt",root/"errors.txt",root/"log.txt",root/SIDE/"client-startup.txt",root/SIDE/"worker-startup.json",root/SIDE/"status.json"]:
        if path.is_file():print(path.name,path.read_text("utf-8-sig",errors="replace")[-12000:],flush=True)

def wait_marker(proc,root,result,expected,seconds=180):
    deadline=time.monotonic()+seconds
    try:
        while time.monotonic()<deadline:
            if (result/"error.txt").is_file() or (root/"traceback.txt").is_file() or (root/"errors.txt").is_file():
                diagnostics(root,result);raise RuntimeError("Actual native boot failed")
            p=result/"result.txt"
            if p.is_file() and p.read_text("ascii")==expected:
                print(expected,flush=True)
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:pass
                return
            if proc.poll() not in (None,0):break
            time.sleep(.25)
        diagnostics(root,result);raise RuntimeError("Native installed hook result missing")
    finally:
        if proc.poll() is None:
            subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],capture_output=True)
            proc.wait(timeout=15)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--sdk-root",type=Path,required=True)
    parser.add_argument("--servidor",type=Path)
    args=parser.parse_args()
    candidates=[p for p in args.sdk_root.rglob("renpy.exe") if (p.parent/"renpy").is_dir() and (p.parent/"lib").is_dir()]
    if len(candidates)!=1:raise RuntimeError("Official 7.3.2 SDK layout not unique")
    with tempfile.TemporaryDirectory(prefix="ia-renpy-732-",ignore_cleanup_errors=True) as folder:
        base=Path(folder);root=base/"Game Copy";root.mkdir()
        sdk=candidates[0].parent
        for name in ("renpy","lib"):shutil.copytree(sdk/name,root/name)
        for name in ("renpy.exe","renpy.py"):shutil.copy2(sdk/name,root/name)
        launcher=root/"renpy.exe"
        game=root/"game";game.mkdir()
        original=game/"script.rpy";original.write_text(SCRIPT,encoding="ascii")
        env=os.environ.copy()
        for k in ("PYTHONUTF8","PYTHONIOENCODING"):env.pop(k,None)
        env.update(RENPY_DISABLE_JOYSTICK="1",RENPY_SKIP_MAIN_MENU="1",RENPY_PERFORMANCE_TEST="0",RENPY_RENDERER="sw")
        # Compile using the SDK itself. No injected or reconstructed game AST.
        proc=subprocess.Popen([str(launcher),str(root),"compile"],cwd=root,env=env)
        try:
            if proc.wait(timeout=90)!=0:raise RuntimeError("SDK compile failed")
        finally:
            if proc.poll() is None:
                subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],capture_output=True)
        compiled=game/"script.rpyc"
        end=time.monotonic()+30
        while not compiled.is_file() and time.monotonic()<end:time.sleep(.25)
        if not compiled.is_file():raise RuntimeError("No compiled original fixture")
        # Allow the delegated interpreter to close all source/cache handles.
        time.sleep(2)
        archive(game/"archive.rpa","script.rpyc",compiled.read_bytes())
        original.unlink();compiled.unlink()
        for n in range(4):archive(game/("data%d.rpa"%n),"fixture%d.txt"%n,b"synthetic resource")
        if list(game.rglob("*.rpy")) or list(game.rglob("*.rpyc")):raise RuntimeError("Fixture is not archive-only")
        saves=game/"saves";saves.mkdir(exist_ok=True)
        sentinel=saves/"ia-preserve.bin";sentinel.write_bytes(b"original-save-fixture")
        before={p:sha(p) for p in list(game.glob("*.rpa"))+[launcher,sentinel]}
        side=root/SIDE
        hook=game/"ia_servidor_renpy"/"boot.rpy"
        if args.servidor:
            command(args.servidor,"--renpy-inspect","--game",launcher)
            command(args.servidor,"--renpy-install","--game",launcher)
            mode="real"
        else:
            # Source preflight checks the authentic boot loader and native hooks
            # without pretending the absent OPUS worker translates.
            side.mkdir()
            shutil.copyfile(ASSETS/"client.py",side/"client.py")
            hook.parent.mkdir()
            shutil.copyfile(ASSETS/"boot.rpy",hook)
            (side/"owner-v1.json").write_text(json.dumps({"schema":"ia-servidor-renpy-v1","client_sha256":sha(side/"client.py"),"boot_sha256":sha(hook),"profile":"modern","game_rel":"game"}),encoding="utf-8")
            mode="preflight"
        result=base/"results";result.mkdir()
        env.update(IA_RENPY_NATIVE_MODE=mode,IA_RENPY_NATIVE_RESULT=str(result/"result.txt"),IA_RENPY_NATIVE_ERROR=str(result/"error.txt"))
        # Exactly how the user opens the game: original executable, no flags,
        # no extra launch button or special injection from a host interpreter.
        proc=subprocess.Popen([str(launcher)],cwd=root,env=env)
        wait_marker(proc,root,result,"NATIVE_INSTALLED_732_"+mode.upper()+"_OK",240)
        status=(side/"client-startup.txt").read_text("ascii")
        if "IA_RENPY_HOOKS_LISTOS" not in status or "RENPY_VERSION=7.3.2.320" not in status:
            raise RuntimeError("Missing production boot diagnostics")
        if any(sha(p)!=v for p,v in before.items()):raise RuntimeError("Original archive/launcher/save changed")
        if args.servidor:
            if "IA_RENPY_MOTOR_CONECTADO" not in status:raise RuntimeError("Missing real connection diagnostic")
            if not (side/"memory-v1.sqlite3").is_file():raise RuntimeError("Missing real translation memory")
            end=time.monotonic()+90
            while list(side.glob("session-*.json")) and time.monotonic()<end:time.sleep(.25)
            command(args.servidor,"--renpy-recover","--game",launcher)
            if hook.exists() or any(sha(p)!=v for p,v in before.items()):raise RuntimeError("Native recovery did not preserve original")
            print("NATIVE_INSTALLED_732_REAL_OPUS_AND_RECOVERY_PASS",flush=True)
if __name__=="__main__":main()
