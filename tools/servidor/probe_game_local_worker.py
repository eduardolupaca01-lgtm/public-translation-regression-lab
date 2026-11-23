#!/usr/bin/env python3
"""TX781: verify the REAL game-local V95 worker and authenticated Spanish output.

Run exclusively on a disposable Windows CI game fixture after the signed
onefile installed its full neural engine. Never launch the player's Game.exe.
Never disclose tokens, ports, PIDs, game dialogue, or V95 raw logs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

def sha256(filename: Path)->str:
    h=hashlib.sha256()
    with filename.open("rb") as file:
        for block in iter(lambda:file.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def spanish_ready(source:str,translated:str)->bool:
    if not isinstance(translated,str) or not translated.strip() or translated.strip()==source.strip():
        return False
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff]",translated):
        return False
    if "\ufffd" in translated:return False
    return len(translated)<=4000

def request_json(opener, url:str, token:str, obj=None):
    payload=json.dumps(obj,ensure_ascii=False).encode("utf-8") if obj is not None else None
    headers={"X-Tenshixgame-Token":token,"Accept":"application/json"}
    if payload is not None:headers["Content-Type"]="application/json; charset=utf-8"
    req=urllib.request.Request(url,data=payload,headers=headers,
       method="POST" if payload is not None else "GET")
    with opener.open(req,timeout=45 if payload is not None else 12) as res:
        if res.status!=200 or not str(res.headers.get("Content-Type","")).lower().startswith("application/json"):
            raise RuntimeError("TX781_AUTHENTICATED_V95_HTTP_REJECTED")
        raw=res.read(262144+1)
    if len(raw)>262144:raise RuntimeError("TX781_V95_HTTP_RESPONSE_TOO_LARGE")
    return json.loads(raw.decode("utf-8"))

def checked_descriptor(path:Path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>4096:return None
    try:
        data=json.loads(path.read_text("utf-8"))
    except (ValueError,UnicodeError,OSError):return None
    if not isinstance(data,dict) or data.get("schema")!="tenshixgame-bridge-v87":return None
    pid=data.get("pid");port=data.get("port");token=data.get("token")
    if (not isinstance(pid,int) or isinstance(pid,bool) or pid<=0 or
        not isinstance(port,int) or isinstance(port,bool) or not 1024<=port<=65535 or
        not isinstance(token,str) or not re.fullmatch(r"[0-9a-f]{64}",token)):
        return None
    return data

def do_probe(game:Path,runner_temp:Path):
    if os.name!="nt":raise RuntimeError("TX781_WINDOWS_RUNNER_REQUIRED")
    game=game.resolve(strict=True)
    runner_temp=runner_temp.resolve(strict=True)
    if game==runner_temp or runner_temp not in game.parents:
        raise RuntimeError("TX781_ONLY_DISPOSABLE_CI_GAME_ROOT")
    for rel in ("Game.exe","www/js/plugins.js","www/js/rpg_core.js","www/data/System.json"):
        target=game/rel
        if not target.is_file() or target.is_symlink():
            raise RuntimeError("TX781_SYNTHETIC_MV_FIXTURE_INCOMPLETE")
    sidecar=game/"Tenshixgame-IA"
    local=sidecar/".local"
    owner=sidecar/"portable-owner-v1.json"
    worker=local/"TENSHIXGAME-RPG"/"engine"/"engine"/"TenshixgameAI.exe"
    if not owner.is_file() or owner.is_symlink() or not worker.is_file() or worker.is_symlink():
        raise RuntimeError("TX781_VERIFIED_V95_SOURCE_MISSING")
    marker=json.loads(owner.read_text("utf-8"))
    if marker.get("schema")!="tenshixgame-rpg-portable-owner-v1" or (
        marker.get("worker_sha256")!=sha256(worker)
    ):raise RuntimeError("TX781_V95_SHA_NOT_ATTESTED")
    temp=local/"tmp"
    temp.mkdir(parents=True,exist_ok=True)
    if temp.is_symlink() or not temp.is_dir():raise RuntimeError("TX781_PORTABLE_TMP_UNSAFE")
    env=os.environ.copy()
    env.update({"LOCALAPPDATA":str(local),"TEMP":str(temp),"TMP":str(temp),"TMPDIR":str(temp)})
    descriptors=[
        game/"www"/"data"/"TenshigameTranduccion"/"embedded-v87-bridge.json",
        game/"www"/"data"/"TenshigameTraduccion"/"embedded-v87-bridge.json",
        game/"data"/"TenshigameTranduccion"/"embedded-v87-bridge.json",
        game/"data"/"TenshigameTraduccion"/"embedded-v87-bridge.json",
    ]
    # Only this fresh fixture is allowed; no old session/owned game removal.
    if any(p.exists() for p in descriptors):
        raise RuntimeError("TX781_SYNTHETIC_DESCRIPTOR_ALREADY_PRESENT")
    proc=None
    private_log=runner_temp/"servidor-tx781-runtime-private.log"
    try:
        with private_log.open("xb") as log:
            proc=subprocess.Popen(
                [str(worker),"--game-root",str(game),"--parent-pid",str(os.getpid())],
                cwd=game,env=env,stdin=subprocess.DEVNULL,stdout=log,
                stderr=subprocess.STDOUT,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            deadline=time.monotonic()+110
            descriptor=None
            while time.monotonic()<deadline:
                if proc.poll() is not None:
                    raise RuntimeError("TX781_WORKER_EARLY_EXIT_BEFORE_GAME_BRIDGE")
                for candidate in descriptors:
                    descriptor=checked_descriptor(candidate)
                    if descriptor:break
                if descriptor:break
                time.sleep(.4)
            if not descriptor:raise RuntimeError("TX781_GAME_LOCAL_V95_BRIDGE_TIMEOUT")
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            url="http://127.0.0.1:"+str(descriptor["port"])
            status=request_json(opener,url+"/status",descriptor["token"])
            if not isinstance(status,dict) or status.get("active") is not True:
                raise RuntimeError("TX781_V95_WORKER_NOT_ACTIVE")
            original="おはようございます。"
            answer=request_json(opener,url+"/translate",descriptor["token"],
                {"source":"ja","target":"es","text":original})
            if not isinstance(answer,dict) or not spanish_ready(original,answer.get("translated")):
                raise RuntimeError("TX781_REAL_JAPANESE_TO_SPANISH_NOT_DELIVERED")
        print("SERVIDOR_TX781_REAL_PORTABLE_WORKER_START_HTTP_AND_SPANISH_PASS")
    finally:
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        proc.kill();proc.wait(timeout=4)
            except (OSError,subprocess.TimeoutExpired):
                pass

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--game-root",type=Path)
    ap.add_argument("--runner-temp",type=Path)
    a=ap.parse_args()
    if a.self_test:
        assert spanish_ready("おはようございます。","Buenos días.")
        for wrong in ("","おはようございます。","Hola。おはよう","Hola\ufffd"):
            assert not spanish_ready("おはようございます。",wrong)
        print("SERVIDOR_TX781_REAL_WORKER_CONTRACT_PREFLIGHT_PASS")
        return
    if not a.game_root or not a.runner_temp:
        ap.error("--game-root and --runner-temp required")
    try:do_probe(a.game_root,a.runner_temp)
    except Exception as error:
        name=str(error)
        # Never print exception details or private on-disk game/worker logs.
        if not re.fullmatch(r"TX781_[A-Z_]+",name):
            name="TX781_RUNTIME_FAILED_UNCLASSIFIED"
        print(name,file=sys.stderr)
        raise SystemExit(1)
if __name__=="__main__":main()
