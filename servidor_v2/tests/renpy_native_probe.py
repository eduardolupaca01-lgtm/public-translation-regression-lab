"""Test real native Ren'Py display contracts, with deterministic test responses.
No old game/translator code, no OPUS claims, no user files.
"""
import argparse
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import sys

SOURCE=pathlib.Path(__file__).resolve().parents[1]/"cmd"/"servidor"/"renpy_assets"/"client.py"
SCRIPT=r'''
# coding: utf-8
define config.name = "Servidor RenPy R1 Native Test"
define config.save_directory = "ServidorRenPyR1NativeLab"

init 999 python hide:
    import os
    import sys
    import renpy as engine
    sys.path.insert(0, config.basedir)
    import ia_native_client
    class IATestClient(object):
        def __init__(self):
            self.seen = []
        def enqueue(self, value):
            self.seen.append(value)
        def start_prefetch(self):
            pass
        def close(self):
            pass
        def translate(self, value, foreground=True):
            return {
                u'Hello world':u'Hola mundo',
                u'She said "Hello"':u'Ella dijo "Hola"',
                u'Continue':u'Continuar',
                u'Quest complete':u'Mision completada',
                u'Inventory':u'Inventario',
            }.get(value,value)
    ia_test_client=IATestClient()
    try:
        ia_native_client.install(engine,ia_test_client)
    except Exception:
        import traceback
        with open(os.path.join(config.basedir,"native-init-error.txt"),"wb") as report:
            report.write(traceback.format_exc().encode("utf-8","backslashreplace"))
        raise
    with open(os.path.join(config.basedir,"native-init-ok.txt"),"wb") as report:
        report.write(b"INIT_OK")

label main_menu:
    return

label start:
    python:
        try:
            import io
            import os
            try:
                import builtins as py_builtins
            except ImportError:
                import __builtin__ as py_builtins
            native = renpy.text.text.Text
            pairs = [(u'Hello world',u'Hola mundo'),
                (u'She said "Hello"',u'Ella dijo "Hola"'),
                (u'Continue',u'Continuar'),
                (u'Quest complete',u'Mision completada'),
                (u'Inventory',u'Inventario')]
            for original, expected in pairs:
                displayable = native(original)
                actual=displayable.text
                if isinstance(actual,(py_builtins.list,py_builtins.tuple)):
                    # Ren'Py store shadows Python's list on modern runtimes.
                    # Require the whole native sequence, not only its first item.
                    assert py_builtins.tuple(actual)==(expected,), "native Text did not receive exact translation: "+repr(actual)
                else:
                    assert actual==expected, "native Text did not receive translation: "+repr(actual)
            if hasattr(config,"say_menu_text_filter"):
                assert config.say_menu_text_filter(u'Hello world')==u'Hola mundo'
            from renpy.display.behavior import Input
            entered = Input(default=u'Hello world')
            assert entered.content == u'Hello world', "player input altered"
            with io.open(os.path.join(config.basedir,"native-result.txt"),"w",encoding="utf-8") as report:
                report.write(u"NATIVE_TEXT_CONTRACT_OK")
        except Exception:
            import traceback
            with open(os.path.join(config.basedir,"native-error.txt"),"wb") as report:
                report.write(traceback.format_exc().encode("utf-8","backslashreplace"))
    $ renpy.quit()
    return
'''
def diagnostics(root):
    for name in ("native-init-error.txt","native-error.txt","native-init-ok.txt","traceback.txt","errors.txt","log.txt"):
        p=root/name
        if p.exists():
            print(name, p.read_text(encoding="utf-8-sig",errors="replace")[-10000:], flush=True)

def main():
    # Windows CI's legacy cp1252 output otherwise masks the Ren'Py exception.
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8",errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8",errors="backslashreplace")
    parser=argparse.ArgumentParser()
    parser.add_argument("--sdk-root",type=pathlib.Path,required=True)
    parser.add_argument("--version",required=True)
    args=parser.parse_args()
    executables=list(args.sdk_root.rglob("renpy.exe"))
    candidates=[p for p in executables if (p.parent/"renpy").is_dir() and (p.parent/"lib").is_dir()]
    if len(candidates)!=1:
        raise RuntimeError("Expected a single official SDK executable: %d"%len(candidates))
    with tempfile.TemporaryDirectory(prefix="ia-renpy-native-") as folder:
        root=pathlib.Path(folder)
        game=root/"game";game.mkdir()
        (game/"script.rpy").write_text(SCRIPT,encoding="utf-8")
        shutil.copyfile(SOURCE,root/"ia_native_client.py")
        env=os.environ.copy()
        env["RENPY_DISABLE_JOYSTICK"]="1"
        env["RENPY_SKIP_MAIN_MENU"]="1"
        # The host PYTHONUTF8 setting is for the outer diagnostic only;
        # do not inject Python 3 settings into a bundled legacy interpreter.
        env.pop("PYTHONUTF8",None)
        env.pop("PYTHONIOENCODING",None)
        proc=subprocess.Popen([str(candidates[0]),str(root)],cwd=str(candidates[0].parent),env=env)
        try:
            deadline=time.monotonic()+120
            marker=root/"native-result.txt"
            err=root/"native-error.txt"
            while time.monotonic()<deadline:
                if err.exists() or (root/"native-init-error.txt").exists() or (root/"traceback.txt").exists() or (root/"errors.txt").exists():
                    diagnostics(root)
                    raise RuntimeError("RenPy reported a native initialization or execution error")
                # Legacy Windows launcher can exit successfully before its
                # delegated interpreter emits the actual game result. A zero
                # launcher exit is never an acceptance result.
                if proc.poll() is not None and proc.returncode!=0 and not marker.exists():
                    diagnostics(root)
                    raise RuntimeError("RenPy launcher failed: "+str(proc.returncode))
                if marker.exists() and marker.read_text(encoding="utf-8")=="NATIVE_TEXT_CONTRACT_OK":
                    print("REAL_SDK_NATIVE_CONTRACT",args.version,"PASS (deterministic responses, not OPUS)")
                    return
                time.sleep(.5)
            diagnostics(root)
            raise RuntimeError("Native marker missing for "+args.version)
        finally:
            if proc.poll() is None:
                subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],capture_output=True)
                proc.wait(timeout=15)
if __name__=="__main__":
    main()
