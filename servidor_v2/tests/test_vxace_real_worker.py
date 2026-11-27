#!/usr/bin/env python3
"""Windows candidate acceptance on generated resources + desktop Ruby, not RGSS3."""
import argparse, ctypes, hashlib, json, os, re, shutil, sqlite3, stat, subprocess, tempfile, time
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

def bootloader_pid(receipt,parent):
    try:
        if receipt.is_symlink() or receipt.stat().st_size>1024:
            return None
        data=json.loads(receipt.read_text("ascii"))
        if (isinstance(data,dict) and data.get("schema")=="ia-vxace-process-v1"
                and type(data.get("game_pid")) is int and data["game_pid"]==parent
                and type(data.get("bootloader_pid")) is int
                and 0<data["bootloader_pid"]<=0xffffffff):
            return data["bootloader_pid"]
    except (OSError,ValueError,UnicodeError):
        pass
    return None

def observe_executable(kernel,pid,expected):
    """Obtain a handle while the game is alive and verify its executable."""
    handle=kernel.OpenProcess(0x00101000,0,pid)
    if not handle:
        raise AssertionError("IA_VXACE_PROCESS_OBSERVE_FAILED_%d"%ctypes.get_last_error())
    try:
        name=ctypes.create_unicode_buffer(32768)
        size=ctypes.c_uint32(len(name))
        assert kernel.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)), \
            "IA_VXACE_PROCESS_IMAGE_UNAVAILABLE"
        assert Path(name.value).resolve()==expected.resolve(),"IA_VXACE_PROCESS_IMAGE_MISMATCH"
        return handle
    except BaseException:
        kernel.CloseHandle(handle)
        raise

def wait_clean_exit(kernel,handle,role):
    assert kernel.WaitForSingleObject(handle,35000)==0, \
        "IA_VXACE_%s_DID_NOT_EXIT"%role
    result=ctypes.c_uint32()
    assert kernel.GetExitCodeProcess(handle,ctypes.byref(result)), \
        "IA_VXACE_%s_EXIT_CODE_UNAVAILABLE"%role
    assert result.value==0,"IA_VXACE_%s_EXIT_%d"%(role,result.value)

def run_ruby_session(ruby,game):
    """Observe both onefile processes while Ruby is alive, then require exit.

    The handshake only lets Ruby continue after both process handles are open.
    No PID-based killing or cleanup-error suppression.
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
    kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_uint32,
                                               ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint32)]
    kernel.QueryFullProcessImageNameW.restype=ctypes.c_int
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    kernel.CloseHandle.restype=ctypes.c_int
    process=subprocess.Popen(["ruby",str(ruby),"--real",str(game),"--observe-worker-exit"])
    observed=rpg/("qa-observed-%d.txt"%process.pid)
    receipt=rpg/("vxace-startup-process-%d.json"%process.pid)
    expected=rpg/"engine"/"IATraductora.exe"
    handles={}
    deadline=time.monotonic()+260
    try:
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise AssertionError("IA_VXACE_RUBY_EXIT_BEFORE_OBSERVATION_%s"%process.returncode)
            pid=session_worker_pid(descriptor,process.pid)
            outer=bootloader_pid(receipt,process.pid)
            if pid is not None and outer is not None:
                # The acceptance executable is compiled with --onefile.
                # Distinct handles prove we do not mistake Python exit for
                # the end of PyInstaller's outer cleanup process.
                assert pid!=outer,"IA_VXACE_ONEFILE_TWO_PROCESSES_REQUIRED"
                handles["WORKER"]=observe_executable(kernel,pid,expected)
                handles["BOOTLOADER"]=observe_executable(kernel,outer,expected)
                # Publish exact LF bytes atomically; Ruby reads in binary mode.
                # Text-mode writes on Windows would otherwise produce CRLF.
                pending=observed.with_suffix(".tmp")
                with pending.open("xb") as marker:
                    marker.write(b"observed\n")
                os.replace(pending,observed)
                break
            time.sleep(.05)
        assert set(handles)=={"WORKER","BOOTLOADER"},"IA_VXACE_ONEFILE_OBSERVE_TIMEOUT"
        code=process.wait(timeout=max(1,deadline-time.monotonic()))
        assert code==0,"IA_VXACE_RUBY_ACCEPTANCE_EXIT_%d"%code
        wait_clean_exit(kernel,handles["WORKER"],"WORKER")
        wait_clean_exit(kernel,handles["BOOTLOADER"],"BOOTLOADER")
        print("IA_VXACE_ONEFILE_BOTH_PROCESSES_EXIT_PASS",flush=True)
        assert not descriptor.exists(),"IA_VXACE_SESSION_NOT_RELEASED"
        assert not (rpg/"bridge.json").exists(),"IA_VXACE_HTTP_SESSION_NOT_RELEASED"
        assert_cache_released(rpg/"cache"/"translation-memory-v2.sqlite3")
        assert_cache_released(rpg/"vxace-worker.lock")
        print("IA_VXACE_WORKER_EXIT_AND_CACHE_RELEASE_PASS",flush=True)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=15)
        for handle in handles.values():
            kernel.CloseHandle(handle)
        observed.unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--servidor",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args()
    ruby=Path(__file__).with_name("test_vxace_runtime.rb").resolve()
    with tempfile.TemporaryDirectory(prefix="IA VX Ace 日本語 ") as temp:
        for mode in ("loose","packed","packed-large"):
            game=Path(temp)/mode
            large=mode=="packed-large"
            # Allow disk I/O for the genuine 1.2+ GB fixture; keep existing
            # translation, boot and shutdown deadlines unchanged.
            budget=900 if large else 240
            run([a.fixture,"create",game,mode],timeout=budget)
            target=game/("Data/Scripts.rvdata2" if mode=="loose" else "Game.rgss3a")
            if large:
                assert target.stat().st_size>=1216546*1024,"IA_VXACE_LARGE_FIXTURE_TOO_SMALL"
            save=game/"Save01.rvdata2"
            original=hash_file(target)
            save_sha=hash_file(save)
            game_exe=game/"Game.exe"
            if mode=="packed":
                os.chmod(target,stat.S_IREAD)
                assert not target.stat().st_mode&stat.S_IWRITE,"IA_VXACE_READONLY_FIXTURE_INVALID"
            run([a.servidor,"--game",game_exe],timeout=budget)
            if mode=="packed":
                assert not target.stat().st_mode&stat.S_IWRITE,"IA_VXACE_READONLY_FLAG_LOST_INSTALL"
            assert hash_file(target)!=original,"IA_VXACE_INSTALL_NO_CHANGE"
            installed=hash_file(target)
            plugin=game/"IA Traductora"/".local"/"Rpg"/"engine"/"vxace"/"IATraductoraVXACE.rb"
            run([a.fixture,"verify",game,plugin],timeout=budget)
            run([a.servidor,"--game",game_exe],timeout=budget)
            assert hash_file(target)==installed,"IA_VXACE_REINSTALL_CHANGED"
            run_ruby_session(ruby,game)
            cache=game/"IA Traductora"/".local"/"Rpg"/"cache"/"translation-memory-v2.sqlite3"
            rows=cache_rows(cache)
            assert len(rows)>=4,"IA_VXACE_REAL_CACHE_MISSING"
            if mode=="loose":
                run_ruby_session(ruby,game)
                assert cache_rows(cache)==rows,"IA_VXACE_CACHE_NOT_REUSED"
            run([a.servidor,"--recover","--game",game_exe],timeout=budget)
            assert hash_file(target)==original and hash_file(save)==save_sha,"IA_VXACE_RECOVERY_HASH"
            assert cache_rows(cache)==rows,"IA_VXACE_RECOVERY_LOST_CACHE"
            if mode=="packed":
                assert not target.stat().st_mode&stat.S_IWRITE,"IA_VXACE_READONLY_FLAG_LOST_RECOVERY"
                os.chmod(target,stat.S_IREAD|stat.S_IWRITE) # Only disposable QA fixture.
                print("IA_VXACE_READONLY_PACKED_INSTALL_RECOVERY_PASS",flush=True)
            # This is a generated fixture, never a player's game. Verify the
            # actual executable is deletable, only after all restoration,
            # persistence and clean-exit checks. Do not ignore permission errors.
            executable=game/"IA Traductora"/".local"/"Rpg"/"engine"/"IATraductora.exe"
            executable.unlink()
            assert not executable.exists(),"IA_VXACE_EXECUTABLE_NOT_RELEASED"
            print("IA_VXACE_EXECUTABLE_RELEASE_PASS",flush=True)
            # Free only this synthetic fixture before starting another.
            # Strict deletion still fails the build if any handle is left open.
            shutil.rmtree(game)
            print("IA_VXACE_REAL_OPUS_INSTALL_ROUNDTRIP_"+mode.upper().replace("-","_")+"_PASS",flush=True)
    # Reaching this point proves TemporaryDirectory cleanup was strict.
    print("IA_VXACE_STRICT_WORKSPACE_CLEANUP_PASS",flush=True)

if __name__=="__main__":main()
