#!/usr/bin/env python3
"""Fix TX567 verified fallback publication with source-pinned V95 contracts.

Runs only after TX772+Servidor v3 on the disposable Windows CI checkout.
Never renames original V95 worker files or user game folders.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
ROOT=Path("reference/tx541-rpg-onefile")
TARGET="tx771_portable_windows.go"
OVERLAYS=(
    "servidor_publication_windows.go",
    "servidor_publication_windows_test.go",
)
OLD='''    if err=os.Rename(stage,sidecar);err!=nil{
        return "","",fmt.Errorf("TX771_PORTABLE_PUBLISH_FAILED: %w",err)
    }
    published=true
    if err=verifyDirectory(appDir,payload);err!=nil{return "","",fmt.Errorf("TX778_VERIFICAR_PAQUETE_PUBLICADO_FALLIDO: %w",err)}
    if _,err=tx771OwnerFile(marker);err!=nil{return "","",fmt.Errorf("TX778_VERIFICAR_PROPIETARIO_PUBLICADO_FALLIDO: %w",err)}
    return appDir,runtime,nil'''
NEW='''    // TX567 can return App/.stage-* when Windows Defender briefly locks
    // a newly extracted executable. That verified location is authoritative.
    publishedApp,resolveErr:=servidorPublishedPortableApp(stage,stagedApp,sidecar,key)
    if resolveErr!=nil{return "","",resolveErr}
    if err=os.Rename(stage,sidecar);err!=nil{
        return "","",fmt.Errorf("TX771_PORTABLE_PUBLISH_FAILED: %w",err)
    }
    published=true
    if err=verifyDirectory(publishedApp,payload);err!=nil{return "","",fmt.Errorf("TX778_VERIFICAR_PAQUETE_PUBLICADO_FALLIDO: %w",err)}
    if _,err=tx771OwnerFile(marker);err!=nil{return "","",fmt.Errorf("TX778_VERIFICAR_PROPIETARIO_PUBLICADO_FALLIDO: %w",err)}
    return publishedApp,runtime,nil'''

def transform(source:str)->str:
    if source.count(OLD)!=1:raise RuntimeError("SERVIDOR_TX567_PUBLICATION_SOURCE_CONTRACT_CHANGED")
    result=source.replace(OLD,NEW,1)
    # TX772 removed the legacy existing-directory branch. The old App/<hash>
    # locals became dead once the post-publish verifier switched to the
    # *actual* TX567 verified App path. Go forbids unused local variables.
    old_locals='''    appRoot:=filepath.Join(sidecar,"App")
    key:=hex.EncodeToString(payload.checksum[:12])
    appDir:=filepath.Join(appRoot,key)'''
    if result.count(old_locals)!=1:
        raise RuntimeError("SERVIDOR_TX567_UNUSED_LEGACY_PATH_CONTRACT_CHANGED")
    result=result.replace(old_locals,
        '    key:=hex.EncodeToString(payload.checksum[:12])',1)
    if result.count("servidorPublishedPortableApp(")!=1:
        raise RuntimeError("SERVIDOR_TX567_RESOLVED_APP_PATH_REQUIRED")
    return result

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--source-root",type=Path)
    p.add_argument("--overlays",type=Path)
    args=p.parse_args()
    if args.self_test:
        candidate=transform("prefix\n"+
            '    appRoot:=filepath.Join(sidecar,"App")\n'+
            '    key:=hex.EncodeToString(payload.checksum[:12])\n'+
            '    appDir:=filepath.Join(appRoot,key)\n'+OLD+"\nsuffix")
        assert "return publishedApp,runtime,nil" in candidate
        assert "return appDir,runtime,nil" not in candidate
        print("SERVIDOR_TX567_VERIFIED_APP_LOCATION_PREFLIGHT_PASS")
        return
    if not args.source_root or not args.overlays:
        p.error("--source-root and --overlays required")
    root=args.source_root/ROOT
    source=root/TARGET
    if not source.is_file():raise RuntimeError("SERVIDOR_AUTHENTIC_V95_SOURCE_REQUIRED")
    for n in OVERLAYS:
        if not (args.overlays/n).is_file() or (root/n).exists():
            raise RuntimeError("SERVIDOR_TX567_OVERLAY_ALREADY_PRESENT_OR_MISSING")
    changed=transform(source.read_text(encoding="utf-8"))
    source.write_text(changed,encoding="utf-8")
    for n in OVERLAYS:shutil.copyfile(args.overlays/n,root/n)
    print("SERVIDOR_TX567_PUBLISHED_APP_PATH_FIXED_WITHOUT_WEAKENING_SHA")

if __name__=="__main__":main()
