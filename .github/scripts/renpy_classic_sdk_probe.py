"""Historical SDK contract test, isolated from packaged models and secrets.
Uses genuine SDK classes and deterministic fixture translations, not neural inference.
"""
import argparse
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import time
import zipfile

CLIENT=Path(__file__).resolve().parents[2]/"servidor_v2/cmd/servidor/renpy_assets/classic_client.py"
SCRIPT=r'''
init 999:
    python hide:
        import os
        import sys
        import types
        import traceback
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
            assert os.environ["IA_CLASSIC_VERSION"] in version,repr(version)
            cls=module.native_text_class(engine)
            assert cls is not None
            module.install(engine,Fixture())
            def check(value,expected):
                if isinstance(value,(builtins.list,builtins.tuple)):
                    assert builtins.tuple(value)==(expected,),repr(value)
                else:
                    assert value==expected,repr(value)
            for original,expected in ((u'Hello world',u'Hola mundo'),(u'She said "Hello"',u'Ella dijo "Hola"'),(u'Continue',u'Continuar'),(u'{b}Save{/b}',u'{b}Guardar{/b}')):
                obj=cls(original)
                check(obj.text,expected)
            obj=cls(u'Hello world')
            obj.set_text(u'Continue')
            check(obj.text,u'Continuar')
            from renpy.display.behavior import Input
            entered=Input(default=u'Hello world')
            assert entered.content==u'Hello world'
            report=open(os.environ["IA_CLASSIC_RESULT"],"wb")
            try:
                report.write("CLASSIC_NATIVE_INIT_OK "+version)
            finally:
                report.close()
        except Exception:
            report=open(os.environ["IA_CLASSIC_ERROR"],"wb")
            try:
                report.write(traceback.format_exc())
            finally:
                report.close()
            raise

label start:
    return
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
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--version",required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ia-classic-sdk-",ignore_cleanup_errors=True) as d:
        root=Path(d);sdk=root/"sdk";sdk.mkdir()
        safe_extract(args.archive,sdk)
        launcher=find_launcher(sdk)
        project=root/"fixture"
        game=project if args.version.startswith(("4.","5.")) else project/"game"
        game.mkdir(parents=True)
        (game/"script.rpy").write_text(SCRIPT,encoding="ascii")
        marker=root/"result.txt";error=root/"error.txt"
        env=os.environ.copy()
        env.pop("PYTHONUTF8",None);env.pop("PYTHONIOENCODING",None)
        env.update(IA_CLASSIC_CLIENT=str(CLIENT),IA_CLASSIC_VERSION=args.version,
                   IA_CLASSIC_RESULT=str(marker),IA_CLASSIC_ERROR=str(error),
                   RENPY_RENDERER="sw",RENPY_PERFORMANCE_TEST="0")
        command=[str(launcher),"--game",str(project)] if args.version.startswith(("4.","5.")) else [str(launcher),str(project)]
        print("Historical launcher:",launcher.relative_to(sdk),flush=True)
        proc=subprocess.Popen(command,cwd=launcher.parent,env=env)
        try:
            end=time.monotonic()+100
            while time.monotonic()<end:
                if error.exists():raise RuntimeError(error.read_text("utf-8",errors="replace"))
                if marker.exists():
                    result=marker.read_text("utf-8",errors="replace")
                    if result.startswith("CLASSIC_NATIVE_INIT_OK ") and args.version in result:
                        print(result,flush=True)
                        return
                if proc.poll() not in (None,0):
                    break
                time.sleep(.25)
            for directory in (project,game,launcher.parent):
                for name in ("traceback.txt","errors.txt","log.txt"):
                    p=directory/name
                    if p.is_file():print(name,p.read_text("utf-8-sig",errors="replace")[-8000:],flush=True)
            raise RuntimeError("Historical native initialization marker missing")
        finally:
            if proc.poll() is None:
                subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],capture_output=True)
                proc.wait(timeout=15)
if __name__=="__main__":main()
