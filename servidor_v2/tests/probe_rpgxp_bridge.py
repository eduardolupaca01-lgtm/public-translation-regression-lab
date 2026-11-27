"""Cross-language XP adapter -> real worker Service -> SQLite laboratory.
Only the neural response is controlled; no proprietary DLL or model weights.
"""
import importlib.util
from pathlib import Path
import subprocess
import tempfile

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ia_r43",BASE/"worker"/"IATraductora.py")
ia=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ia)

def pe(dll=False):
    b=bytearray(256)
    b[:2]=b"MZ";b[60:64]=(64).to_bytes(4,"little")
    b[64:68]=b"PE\0\0";b[68:70]=(0x14c).to_bytes(2,"little")
    b[84:86]=(2).to_bytes(2,"little")
    b[86:88]=(0x2002 if dll else 2).to_bytes(2,"little")
    b[88:90]=(0x10b).to_bytes(2,"little")
    return b

class Neural:
    answers={("en","Please open the door."):"Abre la puerta.",
             ("en","Wait here."):"Espera aquí.",
             ("ja","おはようございます。"):"Buenos días."}
    def __init__(self,allow):
        self.allow=allow
        self.calls=[]
    def translate(self,lang,text):
        self.calls.append((lang,text))
        if not self.allow:raise AssertionError("unexpected repeated inference")
        return self.answers[(lang,text)]

def run_once(root,engine,allow):
    model=Neural(allow)
    service=ia.Service(root,engine,neural=model,rpgxp_mode=True)
    bridge=None
    child=None
    try:
        child=subprocess.Popen(["ruby",str(BASE/"tests"/"probe_rpgxp_bridge.rb")],
                               cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        bridge=ia.RPGXPFileBridge(service,child.pid)
        bridge.start()
        out,err=child.communicate(timeout=25)
        if child.returncode or b"IA_RPGXP_NATIVE_IPC_FIRST_VIEW_PASS" not in out:
            raise AssertionError("XP native IPC fixture failed: "+err.decode("utf8","replace")[-1000:])
        assert service.translations==(3 if allow else 0),service.translations
        assert len(model.calls)==(3 if allow else 0),len(model.calls)
    finally:
        if child is not None and child.poll() is None:
            child.kill();child.communicate()
        if bridge is not None:bridge.stop_serving()
        service.close()
        if bridge is not None:bridge.close()
    assert not (engine.parent/"rpgxp-session.txt").exists()
    assert not (engine.parent/"vxace-session.txt").exists()

def main():
    with tempfile.TemporaryDirectory(prefix="r43-xp-") as tmp:
        root=Path(tmp)/"XP fixture"
        data=root/"Data";data.mkdir(parents=True)
        (root/"Game.exe").write_bytes(pe())
        (root/"RGSS104E.dll").write_bytes(pe(True))
        (root/"Game.ini").write_text("[Game]\nLibrary=RGSS104E.dll\nScripts=Data\\Scripts.rxdata\n",encoding="ascii")
        for n in ("Scripts.rxdata","System.rxdata","MapInfos.rxdata"):
            (data/n).write_bytes(b"\x04\x08[6")
        engine=root/"IA Traductora"/".local"/"Rpg"/"engine"
        engine.mkdir(parents=True)
        before={p.name:p.read_bytes() for p in data.iterdir()}
        run_once(root,engine,True)
        run_once(root,engine,False)
        assert before=={p.name:p.read_bytes() for p in data.iterdir()}
        assert (engine.parent/"cache"/"translation-memory-v2.sqlite3").is_file()
        print("IA_RPGXP_NATIVE_IPC_WORKER_SQLITE_RESTART_PASS")
        # A foreign or packed engine is never accepted in this explicit mode.
        (root/"Game.rgssad").write_bytes(b"RGSSAD\0\1")
        try:ia.rpgxp_game_root(root)
        except ValueError:pass
        else:raise AssertionError("packed XP should remain blocked")

if __name__=="__main__":main()
