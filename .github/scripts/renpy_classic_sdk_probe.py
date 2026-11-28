"""Historical SDK contract test, isolated from packaged models and secrets.
Uses genuine SDK classes and deterministic fixture translations, not neural inference.
"""
import argparse
import os
import struct
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import time
import zipfile

CLIENT=Path(__file__).resolve().parents[2]/"servidor_v2/cmd/servidor/renpy_assets/classic_client.py"
START_MODULE=CLIENT.with_name("classic_start.py")
SCRIPT=r'''
init 999:
    python hide:
        import os
        import sys
        import types
        import traceback
        checkpoint=open(os.environ["IA_CLASSIC_ENTERED"],"wb")
        checkpoint.write("INIT_ENTERED")
        checkpoint.close()
        try:
            import renpy as engine
            import __builtin__ as builtins
            module=types.ModuleType("ia_classic_fixture")
            execfile(os.environ["IA_CLASSIC_CLIENT"],module.__dict__)
            class Fixture(object):
                def enqueue(self, value):
                    pass
                def start_prefetch(self):
                    pass
                def close(self):
                    pass
                def translate(self, value, foreground=True):
                    return {
                        u'Hello world':u'Hola mundo',
                        u'She said "Hello"':u'Ella dijo "Hola"',
                        u'Continue':u'Continuar',
                        u'{b}Save{/b}':u'{b}Guardar{/b}'
                    }.get(value,value)
            version=str(getattr(engine,"version",""))
            if os.environ["IA_CLASSIC_VERSION"] not in version: raise AssertionError(repr(version))
            cls=module.native_text_class(engine)
            if cls is None: raise AssertionError('native Text missing')
            actual=module.Client(os.environ["IA_CLASSIC_TEST_ROOT"])
            if len(actual.nonce)!=32: raise AssertionError('invalid classic client nonce')
            actual.close()
            module.install(engine,Fixture())
            # python hide uses separate globals and locals in classic engines.
            # Capture the module as a default argument, not a store global.
            def check(value,expected,py_builtins=builtins):
                if isinstance(value,(py_builtins.list,py_builtins.tuple)):
                    if py_builtins.tuple(value)!=(expected,): raise AssertionError(repr(value))
                else:
                    if value!=expected: raise AssertionError(repr(value))
            for original,expected in ((u'Hello world',u'Hola mundo'),(u'She said "Hello"',u'Ella dijo "Hola"'),(u'Continue',u'Continuar'),(u'{b}Save{/b}',u'{b}Guardar{/b}')):
                obj=cls(original)
                check(obj.text,expected)
            obj=cls(u'Hello world')
            obj.set_text(u'Continue')
            check(obj.text,u'Continuar')
            from renpy.display.behavior import Input
            entered=Input(default=u'Hello world')
            if entered.content!=u'Hello world': raise AssertionError('player input altered')
            report=open(os.environ["IA_CLASSIC_RESULT"],"wb")
            try:
                report.write("CLASSIC_NATIVE_INIT_OK "+version)
            finally:
                report.close()
        except Exception:
            report=open(os.environ["IA_CLASSIC_ERROR"],"wb")
            try:
                traceback.print_exc(file=report)
            finally:
                report.close()
            raise

label start:
    return
'''
DRIVER=r'''
import os
import sys
import traceback
def record(value):
    f=open(os.environ["IA_CLASSIC_PHASE"],"ab")
    try:
        f.write(str(value)+"\n")
    finally:
        f.close()
try:
    import codecs
    record("PYTHON_DEBUG_FLAG "+str(__debug__))
    sdk=os.environ["IA_CLASSIC_SDK"]
    project=os.environ["IA_CLASSIC_PROJECT"]
    namespace={"__name__":"ia_renpy_classic_start"}
    execfile(os.environ["IA_CLASSIC_START_MODULE"],namespace,namespace)
    path=os.path.join(sdk,"ia_io_probe.rpy")
    raw="first\r\nsecond\rthird\n"
    f=open(path,"wb")
    f.write(raw)
    f.close()
    expected=u"first\nsecond\nthird\n"
    f=open(path,"rU")
    try:
        if f.read().decode("utf-8")!=expected: raise AssertionError("native universal newline mismatch")
    finally:
        f.close()
    try:
        old=codecs.open(path,"rU","utf-8")
        old.close()
        record("ORIGINAL_CODEC_OPEN_SUPPORTED")
    except IOError:
        record("ORIGINAL_CODEC_RUB_REPRODUCED_EXISTING_FILE")
    if not namespace["install_codec_compat"](): raise AssertionError("classic codec compatibility was not installed")
    f=codecs.open(path,"rU","utf-8")
    try:
        if f.read()!=expected: raise AssertionError("compatible newline mismatch")
    finally:
        f.close()
    f=open(path,"rb")
    try:
        if f.read()!=raw: raise AssertionError("original file changed")
    finally:
        f.close()
    os.unlink(path)
    record("PRODUCTION_CODEC_COMPAT_OK")
    namespace["native_main"](sdk,project,True,record)
    record("NATIVE_MAIN_RETURNED")
except:
    out=open(os.environ["IA_CLASSIC_ERROR"],"wb")
    try:
        traceback.print_exc(file=out)
        try:
            import renpy
            out.write("\nENGINE_PHASE "+str(renpy.game.exception_info)+"\n")
        except:
            pass
    finally:
        out.close()
    raise
'''

def safe_extract(archive,dest):
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist())>100000 or sum(x.file_size for x in z.infolist())>1024**3:
            raise RuntimeError("Unexpected SDK archive size")
        for item in z.infolist():
            path=PurePosixPath(item.filename.replace("\\","/"))
            if path.is_absolute() or ".." in path.parts or any(":" in x for x in path.parts):
                raise RuntimeError("Unsafe archive path")
            if (item.external_attr>>16)&0o170000==0o120000:
                raise RuntimeError("Unexpected symlink")
        z.extractall(dest)
def find_launcher(base):
    names=("renpy.exe","run_game.exe","game.exe","demo.exe","launcher.exe")
    possible=[]
    for exe in base.rglob("*.exe"):
        name=exe.name.lower()
        if name not in names:continue
        p=exe.parent
        if (p/"renpy").is_dir() or (p/"lib"/"renpy.zip").is_file() or (p/"renpy.zip").is_file() or (p/"renpy.code").is_file():
            possible.append((names.index(name),len(exe.parts),exe))
    if not possible:
        print("Top-level executable inventory:",[str(p.relative_to(base)) for p in base.rglob("*.exe")][:100],flush=True)
        raise RuntimeError("No recognized historical SDK game launcher")
    return sorted(possible,key=lambda x:(x[0],x[1],str(x[2])))[0][2]
def diagnostics(base,project,root,launcher,phase):
    print("Diagnostic phase:",phase,flush=True)
    for p in (root/(phase+"-console.txt"),root/"error.txt",root/"entered.txt",root/"native-phase.txt"):
        if p.is_file():print(p.name,p.read_text("utf-8-sig",errors="replace")[-8000:],flush=True)
    for directory in (project,project/"game",launcher.parent):
        for name in ("traceback.txt","errors.txt","error.txt","log.txt","stderr.txt","renpy.exe.log","run_game.exe.log"):
            p=directory/name
            if p.is_file():print(str(p.relative_to(root)),p.read_text("utf-8-sig",errors="replace")[-8000:],flush=True)

def run_phase(command,env,base,project,root,launcher,phase,marker,expected,seconds):
    print("Phase",phase,"arguments",command[1:],flush=True)
    with (root/(phase+"-console.txt")).open("wb") as output:
        proc=subprocess.Popen(command,cwd=launcher.parent,env=env,stdout=output,stderr=subprocess.STDOUT)
        try:
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                if (root/"error.txt").is_file() and (root/"error.txt").stat().st_size>0:
                    diagnostics(base,project,root,launcher,phase)
                    raise RuntimeError("Historical script reported an exception")
                if marker.is_file() and expected(marker.read_text("utf-8",errors="replace")):
                    print(marker.read_text("utf-8",errors="replace"),flush=True)
                    # --lint and --python normally exit; allow clean completion.
                    try:proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:pass
                    return
                code=proc.poll()
                if code not in (None,0):
                    print("Native exit:",code,hex(code&0xffffffff),flush=True)
                    break
                # A zero launcher exit alone is not evidence of interpreter success.
                time.sleep(.25)
            print("Launcher final status:",proc.poll(),flush=True)
            for path in (project,project/"game",launcher.parent):
                if path.is_dir():
                    print("Fixture files:",str(path.relative_to(root)),[x.name for x in path.glob("*.rpy*")][:30],flush=True)
            diagnostics(base,project,root,launcher,phase)
            raise RuntimeError("Missing verified marker in "+phase)
        finally:
            if proc.poll() is None:
                subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],capture_output=True)
                proc.wait(timeout=15)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--version",required=True)
    args=parser.parse_args()
    # Short ASCII path on the Windows runner; avoid depending on the system
    # profile's long/Unicode temporary-directory name in Python 2.3.
    with tempfile.TemporaryDirectory(prefix="ia-classic-",dir=os.environ.get("RUNNER_TEMP"),ignore_cleanup_errors=True) as d:
        root=Path(d);sdk=root/"sdk";sdk.mkdir()
        safe_extract(args.archive,sdk)
        launcher=find_launcher(sdk)
        binary=launcher.read_bytes()
        offset=struct.unpack_from("<I",binary,0x3c)[0]
        if binary[offset:offset+4]!=b"PE\x00\x00":raise RuntimeError("Not a PE launcher")
        print("Historical launcher:",launcher.relative_to(sdk),"PE machine:",hex(struct.unpack_from("<H",binary,offset+4)[0]),flush=True)
        print("Bundled Python DLLs:",[str(x.relative_to(sdk)) for x in sdk.rglob("python*.dll")][:40],flush=True)
        # These old engines use paths relative to the launcher, plus common/.
        # Keep the synthetic project inside the extracted SDK only.
        project=launcher.parent/"ia_fixture"
        old=args.version.startswith(("4.","5."))
        game=project if old else project/"game"
        game.mkdir(parents=True)
        (game/"script.rpy").write_text(SCRIPT,encoding="ascii")
        marker=root/"result.txt";error=root/"error.txt"
        side=project/"IA Traductora RenPy";side.mkdir()
        (side/"classic-key.txt").write_bytes(b"ab"*16)
        env=os.environ.copy()
        for key in ("PYTHONUTF8","PYTHONIOENCODING","PYTHONHOME","PYTHONPATH"):
            env.pop(key,None)
        env.update(IA_CLASSIC_CLIENT=str(CLIENT),IA_CLASSIC_VERSION=args.version,
                   IA_CLASSIC_TEST_ROOT=str(project),
                   IA_CLASSIC_RESULT=str(marker),IA_CLASSIC_ERROR=str(error),
                   IA_CLASSIC_ENTERED=str(root/"entered.txt"),
                   RENPY_RENDERER="sw",RENPY_PERFORMANCE_TEST="0")
        if old:
            # Official --python switch in historical launchers. First prove
            # their bundled interpreter starts at all, independently of the
            # Ren'Py parser, display classes, graphics, or our translator.
            pre=root/"python-start.txt"
            env["IA_CLASSIC_PYTHON_RESULT"]=str(pre)
            probe=launcher.parent/"ia_boot_probe.py"
            probe.write_text(
                'import os, sys\n'
                'f=open(os.environ["IA_CLASSIC_PYTHON_RESULT"],"wb")\n'
                'f.write("PYTHON_STARTED "+sys.version)\n'
                'f.close()\n',encoding="ascii")
            run_phase([str(launcher),"--python",probe.name],env,sdk,project,root,launcher,
                      "python-start",pre,lambda v:v.startswith("PYTHON_STARTED "),35)
        # Old launchers lose the original exception trying to write wU.
        # Their verified --python mode invokes the real native main instead;
        # retain actual script loading and all Text/Input assertions.
        if old:
            env.update(IA_CLASSIC_SDK=str(launcher.parent),IA_CLASSIC_PROJECT=str(project),
                       IA_CLASSIC_START_MODULE=str(START_MODULE),
                       IA_CLASSIC_PHASE=str(root/"native-phase.txt"))
            (launcher.parent/"ia_native_driver.py").write_text(DRIVER,encoding="ascii")
            (launcher.parent/"ia_native_entry.py").write_text(
                'import os\n'
                'namespace=dict(globals())\n'
                'execfile(os.path.join(os.environ["IA_CLASSIC_SDK"],"ia_native_driver.py"),namespace,namespace)\n',
                encoding="ascii")
            command=[str(launcher),"--python","ia_native_entry.py"]
        else:
            command=[str(launcher),str(project),"--lint"]
        run_phase(command,env,sdk,project,root,launcher,"native-init",marker,
                  lambda v:v.startswith("CLASSIC_NATIVE_INIT_OK ") and args.version in v,85)
if __name__=="__main__":main()
