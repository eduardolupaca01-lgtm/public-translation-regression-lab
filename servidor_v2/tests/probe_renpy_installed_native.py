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

screen ia_unvisited_screen():
    text "Inventory is empty."
    if True:
        textbutton "Open settings" action NullAction()

label ia_inventory_only:
    $ renpy.notify("Quest completed.")
    "This archived dialogue is never played."
    "Thank you for your help."
    menu:
        "Open the archived door":
            "A second archived dialogue."
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
            if not isinstance(module.__name__,py_builtins.str):
                raise RuntimeError("Boot did not use native interpreter module name")
            if str(engine.version_only)!="7.3.2.320":
                raise RuntimeError("Unexpected SDK version "+str(engine.version_only))
            native=engine.text.text.Text
            # The underlying 7.3.2 package exposes the native interaction
            # functions through exports rather than the script-store facade.
            api=engine.exports
            for method in ("show","hide","pause"):
                if not callable(getattr(api,method,None)):
                    raise RuntimeError("Native display API unavailable: "+method)
            def native_value(obj):
                value=obj.text
                if isinstance(value,(py_builtins.list,py_builtins.tuple)):
                    if len(value)!=1:raise RuntimeError("Unexpected native text sequence")
                    value=value[0]
                return value
            def publish_render_evidence(marker):
                # Unlike Ren'Py's buffered log, this fixture-owned receipt is
                # closed and published atomically after all display checks.
                path=os.environ["IA_RENPY_NATIVE_RENDER_RESULT"]
                temp=path+".tmp"
                with open(temp,"wb") as report:
                    report.write(marker.encode("ascii"))
                    report.flush()
                    os.fsync(report.fileno())
                os.rename(temp,path)
            def present_and_refresh(obj,original,deliver=None):
                # Both gates run the real renderer and its periodic callbacks.
                # Only preflight supplies a deterministic cache arrival.
                api.show("ia_probe_text",what=obj)
                try:
                    api.pause(.12,hard=True,with_none=False)
                    if obj.get_layout() is None:
                        raise RuntimeError("Native Text was not rendered")
                    if deliver is not None:
                        if native_value(obj)!=original:
                            raise RuntimeError("Unexpected prepared value in cold fixture")
                        deliver()
                    until=time.time()+90
                    while native_value(obj)==original and time.time()<until:
                        api.pause(.1,hard=True,with_none=False)
                    value=native_value(obj)
                    if value==original:
                        raise RuntimeError("Native periodic text refresh did not apply result")
                    api.pause(.12,hard=True,with_none=False)
                    if obj.get_layout() is None:
                        raise RuntimeError("Translated native Text was not rendered")
                    return value
                finally:
                    api.hide("ia_probe_text")
            if getattr(native.set_text,"__module__","")!=module.__name__:
                raise RuntimeError("Native Text hook missing")
            if not engine.config.say_menu_text_filter:
                raise RuntimeError("Say/menu hook missing")
            mode=os.environ["IA_RENPY_NATIVE_MODE"]
            if mode=="prepare_forbidden":raise RuntimeError("Preparation entered gameplay")
            c=module.active_client
            expected_inventory=(u"This archived dialogue is never played.",u"Open the archived door",u"A second archived dialogue.",u"Inventory is empty.",u"Open settings",u"Quest completed.")
            if not c.snapshot()["scan_complete"] or not all(s in c.seen for s in expected_inventory):
                raise RuntimeError("Native inventory did not discover archived dialogue, screen and notification: "+repr([s for s in expected_inventory if s not in c.seen]))
            if c.snapshot()["scan"]["archived_scripts"]<1:
                raise RuntimeError("Native archive inventory not recorded")
            if mode=="preflight":
                # Actual native constructors while no worker binary exists.
                begin=time.time()
                for i in range(200):
                    native(u"Cold undiscovered display text %d."%i)
                if time.time()-begin>2.0:
                    raise RuntimeError("Native constructors blocked without worker")
                # Detect actual display API/callback problems before spending
                # time packaging the real models.
                cold=u"Cold native text "+u"awaiting translation."
                translated=u"Texto nativo listo."
                obj=native(cold,slow=False)
                if native_value(obj)!=cold or not c.waiting(cold):
                    raise RuntimeError("Cold native refresh fixture not queued")
                value=present_and_refresh(obj,cold,lambda:c.remember(cold,translated))
                if value!=translated:
                    raise RuntimeError("Native periodic refresh returned wrong text")
                publish_render_evidence("NATIVE_PREBUILD_RENDER_AND_PERIODIC_REFRESH_PASS")
            if mode=="real":
                # The actual previous preparation must already have made
                # this archived sentence available BEFORE any worker wait.
                first=native(u"Thank you for your help.")
                value=native_value(first)
                if c.snapshot()["preloaded"]<1 or not re.search(u"gracias|agradezco|ayuda|asistencia",value,re.I):
                    raise RuntimeError("Prepared dialogue unavailable on first native display")
                deadline=time.time()+90
                # Observe the production automatic startup, without calling
                # get_session() to start or reconnect it from the test.
                while time.time()<deadline and not c.connection:
                    time.sleep(.25)
                if not c.connection:
                    raise RuntimeError("Packaged worker did not connect automatically")
                # Observe the actual independent, non-modal worker window.
                import ctypes
                import json
                user=ctypes.WinDLL("user32",use_last_error=True)
                user.FindWindowW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p]
                user.FindWindowW.restype=ctypes.c_void_p
                end=time.time()+20
                hwnd=None
                while time.time()<end:
                    try:
                        with open(os.path.join(c.side,"window-status.json"),"rb") as report:
                            window=json.loads(report.read(8192))
                        if window.get("schema")=="ia-renpy-progress-window-v1" and window.get("state")=="visible":
                            hwnd=user.FindWindowW(u"IA_RENPY_PROGRESS_"+str(window["pid"]),None)
                            if hwnd:break
                    except (IOError,ValueError,KeyError):pass
                    time.sleep(.1)
                if not hwnd:raise RuntimeError("Independent IA Traductora window missing")
                # Closing the progress window MUST NOT close the worker.
                user.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
                user.PostMessageW.restype=ctypes.c_int
                if not user.PostMessageW(hwnd,0x0010,0,0):
                    raise RuntimeError("Unable to close independent progress view")
                pairs=[(u"Thank you for your help.",u"gracias|agradezco|ayuda|asistencia"),
                       (u"\u304a\u306f\u3088\u3046\u3054\u3056\u3044\u307e\u3059\u3002",u"buenos|buen|d\u00edas|d\u00eda|hola"),
                       (u'{b}"Thank you for your help."{/b}',u"gracias|agradezco|ayuda|asistencia")]
                cold_count=0
                for original,pattern in pairs:
                    begin=time.time()
                    displayable=native(original,slow=False)
                    if time.time()-begin>.25:
                        raise RuntimeError("Native text constructor waited on translation")
                    if native_value(displayable)==original:cold_count+=1
                    value=present_and_refresh(displayable,original)
                    if value==original or not re.search(pattern,value,re.I):
                        raise RuntimeError("Native text was not translated: "+repr(value))
                    if "{" in original and ("{b}" not in value or "{/b}" not in value or value.count('"')!=2):
                        raise RuntimeError("Formatting/quotes lost")
                if not cold_count:
                    raise RuntimeError("No previously unprepared dynamic text exercised real periodic refresh")
                publish_render_evidence("NATIVE_REAL_RENDER_AND_PERIODIC_REFRESH_PASS")
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
    for path in [result/"error.txt",result/"render-result.txt",root/"traceback.txt",root/"errors.txt",root/"log.txt",root/SIDE/"client-startup.txt",root/SIDE/"worker-startup.json",root/SIDE/"status.json",root/SIDE/"client-progress.json",root/SIDE/"window-status.json"]:
        if path.is_file():print(path.name,path.read_text("utf-8-sig",errors="replace")[-12000:],flush=True)

def verify_render_evidence(result,real):
    expected="NATIVE_REAL_RENDER_AND_PERIODIC_REFRESH_PASS" if real else "NATIVE_PREBUILD_RENDER_AND_PERIODIC_REFRESH_PASS"
    path=result/"render-result.txt"
    if not path.is_file() or path.stat().st_size!=len(expected):
        raise RuntimeError("Missing actual native render/refresh evidence")
    if path.read_text("ascii")!=expected:
        raise RuntimeError("Incorrect native render/refresh evidence for this mode")
    return expected

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
        # Exact 7.3.2 CI renderer workaround; applies to this temporary
        # fixture only. No production environment or game config is changed.
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
        # Explicitly verify the actual registered native command before
        # normal gameplay. The source preflight cancels without a worker;
        # packaged acceptance performs the whole real OPUS preparation.
        prep_env=dict(env,IA_RENPY_NATIVE_MODE="prepare_forbidden",
                      IA_RENPY_NATIVE_RESULT=str(result/"forbidden-result.txt"),
                      IA_RENPY_NATIVE_ERROR=str(result/"forbidden-error.txt"),
                      IA_RENPY_NATIVE_RENDER_RESULT=str(result/"forbidden-render-result.txt"))
        if args.servidor:
            prep=subprocess.run([str(args.servidor),"--renpy-prepare","--game",str(launcher)],
                                env=prep_env,capture_output=True,timeout=900)
            if prep.returncode:
                diagnostics(root,result)
                raise RuntimeError("Packaged native preparation failed: "+prep.stderr.decode("utf-8","replace")[-2000:])
            reports=list(side.glob("prepare-result-*.json"))
            if len(reports)!=1:raise RuntimeError("Missing preparation completion report")
            data=json.loads(reports[0].read_text("utf-8"))
            if data["result"]!="IA_RENPY_PREPARACION_LISTA" or data["pending"] or not data["scan_complete"] or not data["snapshot_saved"]:
                raise RuntimeError("Preparation did not complete: "+repr(data))
            if not (side/"prepared-cache-v1.jsonl").is_file():raise RuntimeError("Prepared fast-start cache missing")
            import sqlite3
            with sqlite3.connect(side/"memory-v1.sqlite3") as db:
                rows=db.execute("SELECT output FROM memory WHERE original=?",("Thank you for your help.",)).fetchall()
                if not rows or not any(x[0]!="Thank you for your help." for x in rows):
                    raise RuntimeError("Unvisited archived dialogue missing from real prepared memory")
            print("NATIVE_PREPLAY_REAL_OPUS_INVENTORY_PASS",data["inventory"],data["accepted"],data["unchanged"],flush=True)
        else:
            import secrets
            nonce=secrets.token_hex(16)
            request=side/"prepare-request.json"
            cancel=side/("prepare-cancel-"+nonce+".txt")
            marker=side/("prepare-result-"+nonce+".json")
            request.write_text(json.dumps({"schema":"ia-servidor-renpy-v1","id":nonce}),encoding="utf-8")
            cancel.write_text("cancel",encoding="ascii")
            save=side/("prepare-saves-"+nonce);save.mkdir()
            prep_env["IA_RENPY_PREPARE_ID"]=nonce
            proc=subprocess.Popen([str(launcher),str(root),"ia_renpy_prepare","--savedir",str(save)],cwd=root,env=prep_env)
            try:
                until=time.monotonic()+90
                while not marker.is_file() and time.monotonic()<until:
                    if (result/"forbidden-error.txt").is_file() or (root/"traceback.txt").is_file():break
                    time.sleep(.25)
                if not marker.is_file():
                    diagnostics(root,result);raise RuntimeError("Native preparation command did not execute")
                data=json.loads(marker.read_text("utf-8"))
                if data["result"]!="IA_RENPY_PREPARACION_CANCELADA" or not data["scan_complete"] or data["inventory"]<6:
                    raise RuntimeError("Native preparation command/cancellation failed: "+repr(data))
                print("NATIVE_PREPLAY_COMMAND_AND_CANCEL_PASS",data["inventory"],flush=True)
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:pass
            finally:
                if proc.poll() is None:
                    subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],capture_output=True)
                    proc.wait(timeout=15)
                request.unlink(missing_ok=True);cancel.unlink(missing_ok=True)
            time.sleep(1)
        if any((result/name).is_file() for name in ("forbidden-result.txt","forbidden-error.txt","forbidden-render-result.txt")):
            raise RuntimeError("Preparation unexpectedly entered the game's start label")
        if any(sha(p)!=v for p,v in before.items()):raise RuntimeError("Preparation changed original archive/launcher/save")
        env.update(IA_RENPY_NATIVE_MODE=mode,IA_RENPY_NATIVE_RESULT=str(result/"result.txt"),
                   IA_RENPY_NATIVE_ERROR=str(result/"error.txt"),
                   IA_RENPY_NATIVE_RENDER_RESULT=str(result/"render-result.txt"))
        # Exactly how the user opens the game: original executable, no flags,
        # no extra launch button or special injection from a host interpreter.
        proc=subprocess.Popen([str(launcher)],cwd=root,env=env)
        wait_marker(proc,root,result,"NATIVE_INSTALLED_732_"+mode.upper()+"_OK",240)
        status=(side/"client-startup.txt").read_text("ascii")
        if "IA_RENPY_HOOKS_LISTOS" not in status or "RENPY_VERSION=7.3.2.320" not in status:
            raise RuntimeError("Missing production boot diagnostics")
        try:render_marker=verify_render_evidence(result,bool(args.servidor))
        except (RuntimeError,OSError,UnicodeError):
            diagnostics(root,result)
            raise
        print(render_marker,flush=True)
        if any(sha(p)!=v for p,v in before.items()):raise RuntimeError("Original archive/launcher/save changed")
        if args.servidor:
            if "IA_RENPY_MOTOR_CONECTADO" not in status:raise RuntimeError("Missing real connection diagnostic")
            if not (side/"memory-v1.sqlite3").is_file():raise RuntimeError("Missing real translation memory")
            progress=json.loads((side/"client-progress.json").read_text("utf-8"))
            if not progress["scan_complete"] or progress["inventory"]<3 or progress["discovered"]<3:
                raise RuntimeError("Missing real native scan/progress evidence")
            print("NATIVE_RENPY_NONBLOCKING_VISIBLE_REFRESH_AND_INDEPENDENT_WINDOW_PASS",flush=True)
            end=time.monotonic()+90
            while list(side.glob("session-*.json")) and time.monotonic()<end:time.sleep(.25)
            command(args.servidor,"--renpy-recover","--game",launcher)
            if hook.exists() or any(sha(p)!=v for p,v in before.items()):raise RuntimeError("Native recovery did not preserve original")
            print("NATIVE_INSTALLED_732_REAL_OPUS_AND_RECOVERY_PASS",flush=True)
if __name__=="__main__":main()
