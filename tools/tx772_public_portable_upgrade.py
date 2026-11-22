"""TX772 Windows-runner-only compatibility patch for TENSHIXGAME RPG.

The application source stays at its immutable SHA in the owner's existing
checkout. This public orchestration installs a small independent Go upgrade
helper in the disposable Windows runner; it never commits private source,
model weights or executable payloads to the public repository.

The original 26 quality, neural, integrity and encrypted-delivery gates
remain mandatory. Fail closed if any known source anchor has changed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ONEFILE = Path("reference/tx541-rpg-onefile")
TARGET = ONEFILE / "tx771_portable_windows.go"
UPGRADE = ONEFILE / "tx772_public_upgrade_windows.go"
TEST = ONEFILE / "tx772_public_upgrade_windows_test.go"

START = "    if st,err:=os.Lstat(sidecar);err==nil{\n"
END = '    }else if !os.IsNotExist(err){return "","",err}\n'

NEW_EXISTING_BODY = '''        if !st.IsDir()||st.Mode()&os.ModeSymlink!=0{
            return "","",errors.New("TX771_FOREIGN_PORTABLE_FOLDER")
        }
        // TX772: a verified existing game installation may have a different
        // payload checksum from this EXE. Verify and migrate within the game.
        return tx772UpgradeOwnedPortable(payload,gameRoot)
'''

UPGRADE_GO = r'''//go:build windows

package main

// Public runner addition: upgrade ONLY a marker-owned portable translation.
// Game, saves, foreign plugins and the private cache are never rewritten here.
import (
    "encoding/json"
    "errors"
    "fmt"
    "os"
    "path/filepath"
)

func tx772WriteOwnerAtomic(sidecar, workerSHA string) error {
    if len(workerSHA)!=64 {return errors.New("TX772_INVALID_WORKER_SHA")}
    value:=tx771OnefileOwner{
        Schema:tx771OnefileOwnerSchema,
        Product:"TENSHIXGAME-RPG",
        WorkerSHA256:workerSHA,
    }
    raw,err:=json.Marshal(value)
    if err!=nil{return err}
    raw=append(raw,byte(10))
    file,err:=os.CreateTemp(sidecar,".tx772-owner-")
    if err!=nil{return err}
    name:=file.Name()
    defer os.Remove(name)
    if err=file.Chmod(0600);err!=nil{_ =file.Close();return err}
    _,writeErr:=file.Write(raw)
    syncErr:=file.Sync()
    closeErr:=file.Close()
    if writeErr!=nil{return writeErr}
    if syncErr!=nil{return syncErr}
    if closeErr!=nil{return closeErr}
    // The old marker is replaced ONLY after model install and SHA checks.
    if err=os.Rename(name,filepath.Join(sidecar,"portable-owner-v1.json"));err!=nil{
        return fmt.Errorf("TX772_OWNER_MARKER_ATOMIC_RENAME_FAILED: %w",err)
    }
    return nil
}

func tx772UpgradeOwnedPortable(payload *appendedPayload, gameRoot string)(string,string,error){
    sidecar:=filepath.Join(gameRoot,tx771OnefileSidecar)
    local:=filepath.Join(sidecar,".local")
    engine:=filepath.Join(local,"TENSHIXGAME-RPG","engine")
    apps:=filepath.Join(sidecar,"App")
    marker:=filepath.Join(sidecar,"portable-owner-v1.json")
    owner,err:=tx771OwnerFile(marker)
    if err!=nil{return "","",fmt.Errorf("TX772_OWNER_MARKER_REQUIRED: %w",err)}
    for _,p:=range []string{local,engine,apps}{
        info,statErr:=os.Lstat(p)
        if statErr!=nil||!info.IsDir()||info.Mode()&os.ModeSymlink!=0{
            return "","",errors.New("TX772_EXISTING_PORTABLE_TREE_UNSAFE")
        }
    }
    oldWorker:=filepath.Join(engine,"engine","TenshixgameAI.exe")
    oldSHA,err:=shaFile(oldWorker)
    if err!=nil||oldSHA!=owner.WorkerSHA256{
        return "","",errors.New("TX772_EXISTING_WORKER_SHA_MISMATCH")
    }
    // No new file is created before the old worker matches its owner marker.
    // installPrivateAppIn verifies the complete new signed payload by SHA and
    // creates a new App/<digest> on the same volume, preserving old App assets.
    appDir,err:=installPrivateAppIn(payload,apps)
    if err!=nil{return "","",fmt.Errorf("TX772_NEW_APP_INTEGRITY_HOLD: %w",err)}
    // The new, verified host must accept the pre-existing original 22-file
    // engine before a replacement can be considered. Never accept a foreign
    // or altered model directory merely because its filename looks right.
    if err=hostCommandEnv(appDir,local,"verify","--root",engine);err!=nil{
        return "","",errors.New("TX772_EXISTING_ENGINE_INTEGRITY_HOLD")
    }
    matches,err:=engineManifestMatches(appDir,engine)
    if err!=nil{return "","",err}
    if !matches{
        // The original host uses verified same-volume staging and rollback
        // for --replace. A running/locked worker must make this fail closed.
        if err=ensureOriginalEngineAt(appDir,engine);err!=nil{
            return "","",fmt.Errorf("TX772_ENGINE_UPGRADE_NOT_COMMITTED: %w",err)
        }
    }
    if err=hostCommandEnv(appDir,local,"verify","--root",engine);err!=nil{
        return "","",errors.New("TX772_RESULTING_ENGINE_UNVERIFIED")
    }
    matches,err=engineManifestMatches(appDir,engine)
    if err!=nil||!matches{
        return "","",errors.New("TX772_NEW_MODEL_MANIFEST_NOT_MATCHED")
    }
    newSHA,err:=shaFile(filepath.Join(engine,"engine","TenshixgameAI.exe"))
    if err!=nil{return "","",err}
    if newSHA!=owner.WorkerSHA256{
        if err=tx772WriteOwnerAtomic(sidecar,newSHA);err!=nil{return "","",err}
    }
    // The original per-game SQLite, live-cache, journal, game files and save
    // directories are never deleted or moved during this owner-only upgrade.
    return appDir,local,nil
}
'''

TEST_GO = r'''//go:build windows

package main

import (
    "encoding/json"
    "os"
    "path/filepath"
    "strings"
    "testing"
)

func TestTX772RefuseStaleWorkerMarkerWithoutWritingAnApp(t *testing.T){
    game:=t.TempDir()
    side:=filepath.Join(game,tx771OnefileSidecar)
    engine:=filepath.Join(side,".local","TENSHIXGAME-RPG","engine")
    apps:=filepath.Join(side,"App")
    if err:=os.MkdirAll(filepath.Join(engine,"engine"),0700);err!=nil{t.Fatal(err)}
    if err:=os.MkdirAll(apps,0700);err!=nil{t.Fatal(err)}
    worker:=filepath.Join(engine,"engine","TenshixgameAI.exe")
    if err:=os.WriteFile(worker,[]byte("modified"),0600);err!=nil{t.Fatal(err)}
    owner:=tx771OnefileOwner{
        Schema:tx771OnefileOwnerSchema,Product:"TENSHIXGAME-RPG",
        WorkerSHA256:strings.Repeat("a",64),
    }
    raw,err:=json.Marshal(owner);if err!=nil{t.Fatal(err)}
    if err=os.WriteFile(filepath.Join(side,"portable-owner-v1.json"),raw,0600);err!=nil{t.Fatal(err)}
    cache:=filepath.Join(side,".local","TENSHIXGAME-RPG","live-cache")
    if err=os.MkdirAll(cache,0700);err!=nil{t.Fatal(err)}
    proof:=filepath.Join(cache,"keep-existing-cache.json")
    if err=os.WriteFile(proof,[]byte("cache-owned-by-game"),0600);err!=nil{t.Fatal(err)}
    _,_,err=tx772UpgradeOwnedPortable(&appendedPayload{},game)
    if err==nil||!strings.Contains(err.Error(),"TX772_EXISTING_WORKER_SHA_MISMATCH"){
        t.Fatalf("modified worker was not blocked: %v",err)
    }
    entries,err:=os.ReadDir(apps)
    if err!=nil||len(entries)!=0{t.Fatal("unverified update created app payload")}
    cacheBytes,err:=os.ReadFile(proof)
    if err!=nil||string(cacheBytes)!="cache-owned-by-game"{t.Fatal("existing cache was altered")}
}

func TestTX772AtomicOwnerUpgradeDoesNotBindToDriveLetter(t *testing.T){
    side:=t.TempDir()
    marker:=filepath.Join(side,"portable-owner-v1.json")
    previous:=tx771OnefileOwner{
        Schema:tx771OnefileOwnerSchema,Product:"TENSHIXGAME-RPG",
        WorkerSHA256:strings.Repeat("a",64),
    }
    data,_:=json.Marshal(previous)
    if err:=os.WriteFile(marker,data,0600);err!=nil{t.Fatal(err)}
    if err:=tx772WriteOwnerAtomic(side,strings.Repeat("b",64));err!=nil{t.Fatal(err)}
    updated,err:=tx771OwnerFile(marker)
    if err!=nil||updated.WorkerSHA256!=strings.Repeat("b",64){
        t.Fatalf("atomic marker update failed: %v",err)
    }
    if err:=tx772WriteOwnerAtomic(side,"bad");err==nil{t.Fatal("bad digest accepted")}
    check,err:=tx771OwnerFile(marker)
    if err!=nil||check.WorkerSHA256!=strings.Repeat("b",64){
        t.Fatal("bad digest altered previously verified owner")
    }
}
'''

def transformed(value: str) -> str:
    if value.count(START) != 1 or value.count(END) != 1:
        raise RuntimeError("TX772_PINNED_SOURCE_ANCHOR_CHANGED")
    before, remaining = value.split(START, 1)
    original, after = remaining.split(END, 1)
    required = ("tx771OwnerFile(marker)", "verifyDirectory(appDir,payload)",
                "engineManifestMatches(appDir,engine)", "return appDir,runtime,nil")
    if not all(token in original for token in required):
        raise RuntimeError("TX772_UNRECOGNIZED_ORIGINAL_PORTABLE_FLOW")
    patched = before + START + NEW_EXISTING_BODY + END + after
    # The original 'engine' local was read only by the replaced old-path
    # branch. Keeping it would make the Windows Go compiler reject TX772.
    obsolete = '    engine:=filepath.Join(runtime,"TENSHIXGAME-RPG","engine")\n'
    if patched.count(obsolete) != 1:
        raise RuntimeError("TX772_REPLACED_ENGINE_LOCAL_ANCHOR_CHANGED")
    return patched.replace(obsolete, "")



def self_test() -> None:
    sample = '    engine:=filepath.Join(runtime,"TENSHIXGAME-RPG","engine")\n' + START + ("        " + "\n        ".join((
        "tx771OwnerFile(marker)", "verifyDirectory(appDir,payload)",
        "engineManifestMatches(appDir,engine)", "return appDir,runtime,nil")) + "\n") + END
    patched = transformed(sample)
    assert patched.count("tx772UpgradeOwnedPortable(payload,gameRoot)") == 1
    assert "verifyDirectory(appDir,payload)" not in patched
    for corrupted in (sample.replace("tx771OwnerFile(marker)", ""),
                      sample.replace("engineManifestMatches(appDir,engine)", "")):
        try:
            transformed(corrupted)
        except RuntimeError:
            pass
        else:
            raise AssertionError("TX772_SOURCE_PIN_GUARD_WEAK")
    assert "TX772_EXISTING_WORKER_SHA_MISMATCH" in UPGRADE_GO
    assert "TestTX772RefuseStaleWorkerMarkerWithoutWritingAnApp" in TEST_GO
    print("TX772_PUBLIC_SOURCE_FREE_UPGRADE_PREFLIGHT_PASS")


def install(source_root: Path) -> None:
    root = source_root.resolve()
    source = root / TARGET
    if not source.is_file():
        raise RuntimeError("TX772_PINNED_ORIGINAL_BOOTSTRAP_NOT_FOUND")
    original = source.read_text(encoding="utf-8")
    result = transformed(original)
    if (root / UPGRADE).exists() or (root / TEST).exists():
        raise RuntimeError("TX772_OVERLAY_FILE_ALREADY_EXISTS_REVIEW_REQUIRED")
    source.write_text(result, encoding="utf-8")
    (root / UPGRADE).write_text(UPGRADE_GO, encoding="utf-8")
    (root / TEST).write_text(TEST_GO, encoding="utf-8")
    print("TX772_OWNER_ONLY_EPHEMERAL_WINDOWS_PATCH_APPLIED")
    print("TX772_EXTERNAL_GAME_AND_USER_FILES_UNCHANGED")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.source_root is None:
        parser.error("--source-root required")
    self_test()
    install(args.source_root)


if __name__ == "__main__":
    main()
