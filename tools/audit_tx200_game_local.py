#!/usr/bin/env python3
"""Read-only QA for a copied TENSHIXGAME game with an owned local V95 runtime.

Checks files and hashes, not gameplay, translation quality, network isolation
or whether another Windows computer is compatible. No game/source text, paths,
tokens or model contents are printed. This script is NOT distributed to players.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

SCHEMA="tenshixgame-rpg-portable-owner-v1"
PRODUCT="TENSHIXGAME-RPG"
GAME_SIDECAR="Tenshixgame-IA"
HEX64=re.compile(r"^[a-f0-9]{64}$")

def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as reader:
        for block in iter(lambda:reader.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def ordinary(root:Path,path:Path,*,directory=False)->bool:
    try:
        actual=path.resolve(strict=True)
        actual.relative_to(root.resolve(strict=True))
        if path.is_symlink():
            return False
        return actual.is_dir() if directory else actual.is_file()
    except (ValueError, OSError):
        return False

def json_object(path:Path,limit:int)->dict:
    if path.stat().st_size>limit:
        raise ValueError("OVERSIZED_JSON")
    obj=json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj,dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return obj

def audit(game:Path)->dict:
    checks=[]
    def check(code:str,success:bool,detail:int|None=None)->None:
        entry={"code":code,"result":"PASS" if success else "FAIL"}
        if detail is not None:entry["count"]=detail
        checks.append(entry)

    requested=game
    game=game.resolve()
    root_ok=requested.is_dir() and not requested.is_symlink()
    if not root_ok:
        check("GAME_DIRECTORY",False)
        return {"ok":False,"checks":checks,"runtime_verified":False}
    layouts=[parent for parent in (game,game/"www")
             if (parent/"js/plugins.js").is_file()
             and (parent/"data/System.json").is_file()]
    check("SINGLE_RPG_MV_MZ_LAYOUT",len(layouts)==1)
    game_exe=game/"Game.exe"
    check("GAME_EXECUTABLE_PRESENT",ordinary(game,game_exe))
    side=game/GAME_SIDECAR
    check("GAME_LOCAL_RUNTIME_DIRECTORY",ordinary(game,side,directory=True))
    if not ordinary(game,side,directory=True):
        return {"ok":False,"checks":checks,"runtime_verified":False}
    owner=side/"portable-owner-v1.json"
    marker=None
    if ordinary(game,owner):
        try:marker=json_object(owner,2048)
        except (ValueError,OSError,UnicodeError):pass
    good_marker=bool(marker and marker.get("schema")==SCHEMA
                     and marker.get("product")==PRODUCT
                     and isinstance(marker.get("worker_sha256"),str)
                     and HEX64.fullmatch(marker["worker_sha256"]))
    check("OWNER_MARKER_VALID",good_marker)
    local=side/".local"/"TENSHIXGAME-RPG"
    engine=local/"engine"
    worker=engine/"engine"/"TenshixgameAI.exe"
    check("V95_WORKER_FILE_PRESENT",ordinary(game,worker))
    worker_match=bool(good_marker and ordinary(game,worker)
                      and digest(worker)==marker["worker_sha256"])
    check("V95_WORKER_SHA_MATCHES_OWNER",worker_match)
    manifest=engine/"engine"/"bundle_manifest.json"
    manifest_ok=False
    artifact_count=0
    if ordinary(game,manifest):
        try:
            entries=json_object(manifest,4*1024*1024).get("artifacts")
            if isinstance(entries,dict) and len(entries)>=20:
                manifest_ok=True
                for relative,metadata in entries.items():
                    p=Path(relative)
                    if (p.is_absolute() or ".." in p.parts or
                        not isinstance(metadata,dict) or
                        not isinstance(metadata.get("bytes"),int) or
                        not isinstance(metadata.get("sha256"),str) or
                        not HEX64.fullmatch(metadata["sha256"])):
                        manifest_ok=False;break
                    candidate=engine/p
                    if (not ordinary(game,candidate) or
                        candidate.stat().st_size!=metadata["bytes"] or
                        digest(candidate)!=metadata["sha256"]):
                        manifest_ok=False;break
                    artifact_count+=1
        except (OSError,ValueError,UnicodeError,TypeError):pass
    check("ALL_V95_MANIFEST_ARTIFACTS_VERIFIED",manifest_ok,
          artifact_count if manifest_ok else None)

    cache=local/"live-cache"
    has_cache=ordinary(game,cache,directory=True)
    check("GAME_LOCAL_CACHE_DIRECTORY",has_cache)
    files=0
    if has_cache:
        try:files=sum(1 for x in cache.iterdir()
                      if ordinary(game,x) and x.suffix in (".json",".sqlite3"))
        except OSError:pass
    # An empty cache on initial installation is not falsely reported as
    # successful preservation of earlier translated dialogue.
    check("PREEXISTING_TRANSLATION_CACHE",files>0,files)
    apps=side/"App"
    check("VERIFIED_APP_DIRECTORY_PRESENT",ordinary(game,apps,directory=True)
          and any(x.is_dir() and not x.is_symlink()
                  for x in apps.iterdir()) if apps.is_dir() else False)

    if len(layouts)==1:
        p=layouts[0]
        plugin=p/"js/plugins/TenshixgameRPGLive.js"
        installed=ordinary(game,plugin)
        check("GAME_PLUGIN_INSTALLED",installed)
        registry=p/"js/plugins.js"
        try:registered="TenshixgameRPGLive" in registry.read_text(
                     encoding="utf-8-sig",errors="replace")
        except OSError:registered=False
        check("GAME_PLUGIN_REGISTERED",registered)

    # Historical folders may contain a fixed absolute game_root, stale
    # process PID and port: never interpret them as transferable runtime state.
    old=game/"www/data/TenshigameTranduccion"
    if not old.exists():old=game/"data/TenshigameTranduccion"
    if old.is_dir():
        checks.append({"code":"LEGACY_RUNTIME_STATE_REQUIRES_RUNTIME_REVALIDATION",
                       "result":"WARN"})

    checks.append({"code":"GAME_EXE_LAUNCH_ON_SECOND_WINDOWS_PC",
                   "result":"NOT_TESTED"})
    checks.append({"code":"SECOND_PC_OFFLINE_MODEL_INFERENCE",
                   "result":"NOT_TESTED"})
    checks.append({"code":"PROCESS_EXITS_WITH_GAME_AND_NO_PROFILE_WRITES",
                   "result":"NOT_TESTED"})
    return {"ok":all(x["result"]!="FAIL" for x in checks),
            "checks":checks,"runtime_verified":False}

def self_test()->None:
    with tempfile.TemporaryDirectory() as t:
        root=Path(t)/"A"/"Juego"
        (root/"www/js/plugins").mkdir(parents=True)
        (root/"www/data").mkdir()
        (root/"Game.exe").write_bytes(b"fixture only")
        (root/"www/data/System.json").write_text("{}",encoding="utf8")
        (root/"www/js/plugins.js").write_text(
            "var $plugins=[{name:'TenshixgameRPGLive',status:true}];",
            encoding="utf8")
        (root/"www/js/plugins/TenshixgameRPGLive.js").write_text(
            "// fixture",encoding="utf8")
        side=root/GAME_SIDECAR
        local=side/".local/TENSHIXGAME-RPG"
        (side/"App/approved").mkdir(parents=True)
        (local/"engine/engine").mkdir(parents=True)
        (local/"live-cache").mkdir()
        (local/"live-cache/durable.json").write_text(
            '{"sample":"translated"}',encoding="utf8")
        w=local/"engine/engine/TenshixgameAI.exe"
        w.write_bytes(b"fixture-not-executable")
        artifacts={}
        for i in range(20):
            p=(local/"engine/engine"/f"model-{i:02d}.bin")
            p.write_bytes(str(i).encode("ascii"))
            artifacts[f"engine/{p.name}"]={"bytes":p.stat().st_size,
                                          "sha256":digest(p)}
        artifacts["engine/TenshixgameAI.exe"]={
            "bytes":w.stat().st_size,"sha256":digest(w)}
        (local/"engine/engine/bundle_manifest.json").write_text(
            json.dumps({"artifacts":artifacts}),encoding="utf8")
        (side/"portable-owner-v1.json").write_text(json.dumps({
            "schema":SCHEMA,"product":PRODUCT,"worker_sha256":digest(w)
        }),encoding="utf8")
        assert audit(root)["ok"],"complete verified fixture rejected"
        copy=Path(t)/"B"/"Juego"
        shutil.copytree(root,copy)
        assert audit(copy)["ok"],"relocated relative layout rejected"
        w.write_bytes(b"tampered")
        assert not audit(root)["ok"],"tampered worker accepted"
        owner=copy/"Tenshixgame-IA/portable-owner-v1.json"
        owner.write_text('{"product":"FOREIGN"}',encoding="utf8")
        assert not audit(copy)["ok"],"unknown marker accepted"
    print("TX200_GAME_LOCAL_STATIC_CONTRACT_SELFTEST_PASS")

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("game",type=Path,nargs="?")
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    if args.self_test:self_test();return 0
    if args.game is None:p.error("game path required")
    result=audit(args.game)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["ok"] else 1

if __name__=="__main__":
    raise SystemExit(main())
