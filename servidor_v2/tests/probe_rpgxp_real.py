"""Actual packaged Windows installer/launcher/OPUS; synthetic XP archive/window."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import zlib

BASE=Path(__file__).resolve().parents[1]
from probe_rpgxp_bridge import pe

def integer(n):
    if n==0:return b"\0"
    if 0<n<123:return bytes([n+5])
    raw=n.to_bytes(4,"little").rstrip(b"\0")
    return bytes([len(raw)])+raw

def string(value):
    return b'"'+integer(len(value))+value

def scripts():
    rows=[]
    for index,name in enumerate((b"Window_Message",b"Main"),1):
        rows.append(b"["+integer(3)+b"i"+integer(index)+string(name)+string(zlib.compress(b"# synthetic fixture only")))
    return b"\x04\x08["+integer(len(rows))+b"".join(rows)

def invoke(exe,*args):
    result=subprocess.run([str(exe),*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=240)
    if result.returncode:
        raise AssertionError("XP installer failed: "+result.stderr.decode("utf8","replace")[-600:])

def wait_closed(engine):
    deadline=time.monotonic()+120
    session=engine.parent/"rpgxp-session.txt"
    lock=engine.parent.parent.parent/"install"/"rpgxp"/"operation.lock"
    while time.monotonic()<deadline and (session.exists() or lock.exists()):
        time.sleep(.2)
    assert not session.exists() and not lock.exists(),"XP worker did not stop with parent"

def read_translation_count(database):
    # This reader belongs to the acceptance harness, not the worker.
    # sqlite3.Connection's context manager only manages transactions;
    # explicitly close the connection even if querying/asserting fails.
    uri=database.resolve(strict=True).as_uri()+"?mode=ro"
    with closing(sqlite3.connect(uri,uri=True)) as conn:
        with closing(conn.execute("SELECT COUNT(*) FROM translations")) as cursor:
            return cursor.fetchone()[0]

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--servidor",type=Path,required=True);args=ap.parse_args()
    exe=args.servidor.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="ia-xp-lab-") as tmp:
        root=Path(tmp)/"XP fixture";data=root/"Data";data.mkdir(parents=True)
        game=root/"Game.exe";game.write_bytes(pe())
        (root/"RGSS104E.dll").write_bytes(pe(True))
        (root/"Game.ini").write_text("[Game]\nLibrary=RGSS104E.dll\nScripts=Data\\Scripts.rxdata\n",encoding="ascii")
        target=data/"Scripts.rxdata";original=scripts();target.write_bytes(original)
        for name in ("System.rxdata","MapInfos.rxdata"):(data/name).write_bytes(b"\x04\x08[6")
        untouched={f.name:f.read_bytes() for f in data.iterdir() if f!=target}
        invoke(exe,"--game",game)
        sidecar=root/"IA Traductora";engine=sidecar/".local"/"Rpg"/"engine"
        receipt=sidecar/"install"/"rpgxp"/"receipt.json"
        state=json.loads(receipt.read_text("utf8"))
        assert state["status"]=="INSTALLED" and hashlib.sha256(target.read_bytes()).hexdigest()==state["after_sha256"]
        for attempt in range(2):
            run=subprocess.run(["ruby",str(BASE/"tests"/"probe_rpgxp_real.rb")],cwd=root,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=160)
            if run.returncode or b"IA_RPGXP_REAL_OPUS_INSTALLED_NATIVE_CONTRACT_PASS" not in run.stdout:
                raise AssertionError("XP real worker fixture failed: "+run.stderr.decode("utf8","replace")[-1000:])
            wait_closed(engine)
            count=read_translation_count(engine.parent/"cache"/"translation-memory-v2.sqlite3")
            assert count==3, "missing or duplicate memory keys"
        invoke(exe,"--recover","--game",game)
        assert target.read_bytes()==original
        assert json.loads(receipt.read_text("utf8"))["status"]=="RESTORED"
        assert untouched=={f.name:f.read_bytes() for f in data.iterdir() if f!=target}
        assert (engine.parent/"cache"/"translation-memory-v2.sqlite3").is_file()
    # Announce success only after strict TemporaryDirectory cleanup has
    # completed. Never suppress WinError 32 or delete a player's cache.
    print("IA_RPGXP_REAL_OPUS_AUTOSTART_CACHE_RESTORE_PASS")

if __name__=="__main__":main()
