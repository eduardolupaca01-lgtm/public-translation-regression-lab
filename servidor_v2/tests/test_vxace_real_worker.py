#!/usr/bin/env python3
"""Windows candidate acceptance on generated resources + desktop Ruby, not RGSS3."""
import argparse, ctypes, hashlib, os, re, sqlite3, subprocess, tempfile, time
from contextlib import closing
from pathlib import Path

def hash_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def run(args, timeout=240):
    subprocess.run([str(x) for x in args], check=True, timeout=timeout)

def cache_rows(file):
    # sqlite3.Connection's context manager commits/rolls back; it does not close.
    # A QA inspection must neither create a missing cache nor keep a Win32 handle.
    assert file.is_file() and not file.is_symlink(),"IA_VXACE_CACHE_MISSING"
    with closing(sqlite3.connect(file.resolve().as_uri()+"?mode=ro",uri=True)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        rows=dict(db.execute("SELECT key_sha256,created_unix FROM translations"))
    assert_cache_released(file)
    return rows

def assert_cache_released(file):
    """Check an actual Windows sharing handle without modifying the database."""
    if os.name!="nt":
        return
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,
                                 ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    kernel.CreateFileW.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    kernel.CloseHandle.restype=ctypes.c_int
    handle=kernel.CreateFileW(str(file.resolve()),0x80000000,0,None,3,0x80,None)
    if handle in (None,ctypes.c_void_p(-1).value):
        raise AssertionError("IA_VXACE_CACHE_HANDLE_OPEN_WINERROR_%d"%ctypes.get_last_error())
    assert kernel.CloseHandle(handle),"IA_VXACE_CACHE_PROBE_CLOSE_FAILED"

def session_worker_pid(descriptor,parent):
    try:
        fields=descriptor.read_text("ascii").splitlines()
        if (len(fields)==4 and fields[0]=="IA-VXACE-SESSION-1"
                and re.fullmatch(r"[0-9a-f]{64}",fields[1])
                and int(fields[3])==parent and int(fields[2])>0):
            return int(fields[2])
    except (OSError,ValueError,UnicodeError):
        pass
    return None

def run_ruby_session(ruby,game):
    """Observe the worker handle while the fixture is alive, then wait for exit.

    The optional QA handshake keeps Ruby alive until the observer has captured
    the process handle. No PID-based killing and no cleanup-error suppression.
    """
    rpg=game/"IA Traductora"/".local"/"Rpg"
    descriptor=rpg/"vxace-session.txt"
    assert not descriptor.exists(),"IA_VXACE_PREVIOUS_SESSION_PRESENT"
    assert os.name=="nt","IA_VXACE_WINDOWS_ACCEPTANCE_REQUIRED"
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    kernel.WaitForSingleObject.restype=ctypes.c_uint32
    kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32)]
    kernel.GetExitCodeProcess.restype=ctypes.c_int
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    kernel.CloseHandle.restype=ctypes.c_int
    process=subprocess.Popen(["ruby",str(ruby),"--real",str(game),"--observe-worker-exit"])
    observed=rpg/("qa-observed-%d.txt"%process.pid)
    handle=None
    deadline=time.monotonic()+260
    try:
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise AssertionError("IA_VXACE_RUBY_EXIT_BEFORE_OBSERVATION_%s"%process.returncode)
            pid=session_worker_pid(descriptor,process.pid)
            if pid is not None:
                # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION. Only observe.
                handle=kernel.OpenProcess(0x00101000,0,pid)
                if not handle:
                    raise AssertionError("IA_VXACE_WORKER_OBSERVE_FAILED_%d"%ctypes.get_last_error())
                # Publish exact LF bytes atomically; Ruby reads in binary mode.
                # Text-mode writes on Windows would otherwise produce CRLF.
                pending=observed.with_suffix(".tmp")
                with pending.open("xb") as marker:
                    marker.write(b"observed\n")
                os.replace(pending,observed)
                break
            time.sleep(.05)
        assert handle,"IA_VXACE_WORKER_OBSERVE_TIMEOUT"
        code=process.wait(timeout=max(1,deadline-time.monotonic()))
        assert code==0,"IA_VXACE_RUBY_ACCEPTANCE_EXIT_%d"%code
        assert kernel.WaitForSingleObject(handle,35000)==0,"IA_VXACE_WORKER_DID_NOT_EXIT_WITH_PARENT"
        result=ctypes.c_uint32()
        assert kernel.GetExitCodeProcess(handle,ctypes.byref(result)),"IA_VXACE_WORKER_EXIT_CODE_UNAVAILABLE"
        assert result.value==0,"IA_VXACE_WORKER_EXIT_%d"%result.value
        assert not descriptor.exists(),"IA_VXACE_SESSION_NOT_RELEASED"
        assert not (rpg/"bridge.json").exists(),"IA_VXACE_HTTP_SESSION_NOT_RELEASED"
        assert_cache_released(rpg/"cache"/"translation-memory-v2.sqlite3")
        assert_cache_released(rpg/"vxace-worker.lock")
        print("IA_VXACE_WORKER_EXIT_AND_CACHE_RELEASE_PASS",flush=True)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=15)
        if handle:
            kernel.CloseHandle(handle)
        observed.unlink(missing_ok=True)

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
            run_ruby_session(ruby,game)
            cache=game/"IA Traductora"/".local"/"Rpg"/"cache"/"translation-memory-v2.sqlite3"
            rows=cache_rows(cache)
            assert len(rows)>=4,"IA_VXACE_REAL_CACHE_MISSING"
            if mode=="loose":
                run_ruby_session(ruby,game)
                assert cache_rows(cache)==rows,"IA_VXACE_CACHE_NOT_REUSED"
            run([a.servidor,"--recover","--game",game_exe])
            assert hash_file(target)==original and hash_file(save)==save_sha,"IA_VXACE_RECOVERY_HASH"
            assert cache_rows(cache)==rows,"IA_VXACE_RECOVERY_LOST_CACHE"
            print("IA_VXACE_REAL_OPUS_INSTALL_ROUNDTRIP_"+mode.upper()+"_PASS",flush=True)
    # Reaching this point proves TemporaryDirectory cleanup was strict.
    print("IA_VXACE_STRICT_WORKSPACE_CLEANUP_PASS",flush=True)

if __name__=="__main__":main()
