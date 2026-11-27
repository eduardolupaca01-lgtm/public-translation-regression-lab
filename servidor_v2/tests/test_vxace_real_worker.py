#!/usr/bin/env python3
"""Windows candidate acceptance on generated resources + desktop Ruby, not RGSS3."""
import argparse, hashlib, os, sqlite3, subprocess, tempfile, time
from pathlib import Path

def hash_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def run(args, timeout=240):
    subprocess.run([str(x) for x in args], check=True, timeout=timeout)

def cache_rows(file):
    with sqlite3.connect(file) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        return dict(db.execute("SELECT key_sha256,created_unix FROM translations"))

def wait_shutdown(game):
    descriptor=game/"IA Traductora"/".local"/"Rpg"/"vxace-session.txt"
    deadline=time.monotonic()+35
    while descriptor.exists() and time.monotonic()<deadline:
        time.sleep(.2)
    assert not descriptor.exists(),"IA_VXACE_WORKER_DID_NOT_EXIT_WITH_PARENT"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--servidor",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args()
    ruby=Path(__file__).with_name("test_vxace_runtime.rb").resolve()
    with tempfile.TemporaryDirectory(prefix="IA VX Ace 日本語 ") as temp:
        for mode in ("loose","packed"):
            game=Path(temp)/mode
            run([a.fixture,"create",game,mode])
            target=game/("Data/Scripts.rvdata2" if mode=="loose" else "Game.rgss3a")
            save=game/"Save01.rvdata2"
            original=hash_file(target)
            save_sha=hash_file(save)
            game_exe=game/"Game.exe"
            run([a.servidor,"--game",game_exe])
            assert hash_file(target)!=original,"IA_VXACE_INSTALL_NO_CHANGE"
            installed=hash_file(target)
            plugin=game/"IA Traductora"/".local"/"Rpg"/"engine"/"vxace"/"IATraductoraVXACE.rb"
            run([a.fixture,"verify",game,plugin])
            run([a.servidor,"--game",game_exe])
            assert hash_file(target)==installed,"IA_VXACE_REINSTALL_CHANGED"
            run(["ruby",ruby,"--real",game],timeout=260)
            wait_shutdown(game)
            cache=game/"IA Traductora"/".local"/"Rpg"/"cache"/"translation-memory-v2.sqlite3"
            rows=cache_rows(cache)
            assert len(rows)>=4,"IA_VXACE_REAL_CACHE_MISSING"
            if mode=="loose":
                run(["ruby",ruby,"--real",game],timeout=260)
                wait_shutdown(game)
                assert cache_rows(cache)==rows,"IA_VXACE_CACHE_NOT_REUSED"
            run([a.servidor,"--recover","--game",game_exe])
            assert hash_file(target)==original and hash_file(save)==save_sha,"IA_VXACE_RECOVERY_HASH"
            assert cache_rows(cache)==rows,"IA_VXACE_RECOVERY_LOST_CACHE"
            print("IA_VXACE_REAL_OPUS_INSTALL_ROUNDTRIP_"+mode.upper()+"_PASS")

if __name__=="__main__":main()
