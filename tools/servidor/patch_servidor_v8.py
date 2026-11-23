#!/usr/bin/env python3
"""TX782: verified game-local V95 publish retry on Windows transient locks."""
from __future__ import annotations
from pathlib import Path
import argparse,subprocess,shutil
OWNER_SHA="aeb9ff9326e418fbabe2d53dff7891f4fb340c37"
ROOT=Path("reference/tx541-rpg-onefile")
FILE=ROOT/"tx771_portable_windows.go"
FILES=("servidor_publication_retry_windows_test.go",)
OLD='''    if err=os.Rename(stage,sidecar);err!=nil{
        return "","",fmt.Errorf("TX771_PORTABLE_PUBLISH_FAILED: %w",err)
    }'''
NEW='''    if err=servidorPublishPortableSidecar(stage,sidecar);err!=nil{
        return "","",fmt.Errorf("TX771_PORTABLE_PUBLISH_FAILED: %w",err)
    }'''
def transform(text):
    if text.count(OLD)!=1 or "servidorPublishedPortableApp(" not in text:
        raise RuntimeError("TX782_PRIVATE_PORTABLE_SOURCE_CONTRACT_CHANGED")
    return text.replace(OLD,NEW,1)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--source-root",type=Path)
    p.add_argument("--overlays",type=Path)
    args=p.parse_args()
    if args.self_test:
        out=transform("servidorPublishedPortableApp(\n"+OLD)
        assert out.count("servidorPublishPortableSidecar(")==1
        print("TX782_WINDOWS_BOUNDED_PUBLICATION_RETRY_PREFLIGHT_PASS")
        return
    if args.source_root is None or args.overlays is None:
        p.error("--source-root and --overlays are required")
    root=args.source_root.resolve()
    actual=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True,
        stderr=subprocess.DEVNULL).strip()
    if actual!=OWNER_SHA:raise RuntimeError("TX782_PRIVATE_SHA_MISMATCH")
    src=root/FILE
    dest=root/ROOT
    for name in FILES+("servidor_publication_retry_windows.go",):
        if not (args.overlays/name).is_file() or (dest/name).exists():
            raise RuntimeError("TX782_GO_OVERLAY_INVALID")
    original=src.read_bytes()
    if b"\r" in original:raise RuntimeError("TX782_REQUIRES_SOURCE_LF")
    src.write_bytes(transform(original.decode("utf-8")).encode("utf-8"))
    for name in FILES+("servidor_publication_retry_windows.go",):
        shutil.copyfile(args.overlays/name,dest/name)
    print("TX782_ATOMIC_PORTABLE_ROOT_RETRY_APPLIED")
if __name__=="__main__":main()
