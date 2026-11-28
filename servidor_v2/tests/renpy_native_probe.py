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

SOURCE=pathlib.Path(__file__).resolve().parents[1]/"cmd"/"servidor"/"renpy_assets"/"client.py"
SCRIPT=r'''
# coding: utf-8
define config.name = "Servidor RenPy R1 Native Test"
define config.save_directory = "ServidorRenPyR1NativeLab"

init python:
    import os
    import sys
    import renpy
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
    ia_native_client.install(renpy,ia_test_client)

label start:
    python:
        try:
            import io
            native = renpy.text.text.Text
            pairs = [(u'Hello world',u'Hola mundo'),
                (u'She said "Hello"',u'Ella dijo "Hola"'),
                (u'Continue',u'Continuar'),
                (u'Quest complete',u'Mision completada'),
                (u'Inventory',u'Inventario')]
            for original, expected in pairs:
                displayable = native(original)
                actual=displayable.text
                if isinstance(actual,list):
                    actual=actual[0]
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
            with open(os.path.join(config.basedir,"native-error.txt"),"w") as report:
                report.write(traceback.format_exc())
    $ renpy.quit()
    return
'''
def main():
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
        proc=subprocess.Popen([str(candidates[0]),str(root)],cwd=str(candidates[0].parent),env=env)
        try:
            deadline=time.monotonic()+120
            marker=root/"native-result.txt"
            err=root/"native-error.txt"
            while time.monotonic()<deadline:
                if err.exists():raise RuntimeError(err.read_text(encoding="utf-8",errors="replace"))
                if marker.exists() and marker.read_text(encoding="utf-8")=="NATIVE_TEXT_CONTRACT_OK":
                    print("REAL_SDK_NATIVE_CONTRACT",args.version,"PASS (deterministic responses, not OPUS)")
                    return
                time.sleep(.5)
            for name in ("traceback.txt","errors.txt","log.txt"):
                p=root/name
                if p.exists():print(name,p.read_text(encoding="utf-8",errors="replace")[-6000:])
            raise RuntimeError("Native marker missing for "+args.version)
        finally:
            if proc.poll() is None:
                subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],capture_output=True)
                proc.wait(timeout=15)
if __name__=="__main__":
    main()
