#!/usr/bin/env python3
"""Un solo Servidor.exe con manifiesto, firmas y modelos locales propios."""
from __future__ import annotations
import argparse,hashlib,json,struct,zipfile
from pathlib import Path

if __package__:
 from .pack_vxace_assets import validated_assets
else:
 from pack_vxace_assets import validated_assets

SCHEMA="ia-traductora-package-v1"
MAGIC=b"SERVIDOR2ZIPSHA1"
assert len(MAGIC)==16
MODELS=("opus_ja_es","opus_en_es")
SUFFIX=("model.bin","source.spm","target.spm","config.json",
        "shared_vocabulary.json","source_vocabulary.json","target_vocabulary.json")
def digest(file:Path):
 h=hashlib.sha256()
 with file.open("rb") as stream:
  for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
 return h.hexdigest()
def build(executable:Path,worker:Path,plugin:Path,models:Path,out:Path,*,vxace_helper=None,vxace_plugin=None):
 if not executable.is_file() or not worker.is_file() or not plugin.is_file():
  raise RuntimeError("IA_ARCHIVOS_DE_COMPILACION_INCOMPLETOS")
 if out.resolve() in {executable.resolve(),worker.resolve(),plugin.resolve()}:
  raise RuntimeError("IA_NO_REEMPLAZAR_ORIGINALES")
 files={"IATraductora.exe":worker,"IATraductora.js":plugin}
 if (vxace_helper is None)!=(vxace_plugin is None):
  raise ValueError("IA_VXACE_PAQUETE_INCOMPLETO")
 if vxace_helper is not None:
  assets=validated_assets(vxace_helper,vxace_plugin)
  if out.resolve() in {asset.resolve() for asset in assets.values()}:
   raise ValueError("IA_NO_REEMPLAZAR_ORIGINALES")
  files.update(assets)
 for lang in MODELS:
  for filename in SUFFIX:
   source=models/lang/filename
   if not source.is_file():raise RuntimeError("IA_MODELO_O_LICENCIA_FALTANTE")
   files[f"models/{lang}/{filename}"]=source
  optional=models/lang/"OPUS_LICENSE.txt"
  if not optional.is_file():raise RuntimeError("IA_LICENCIA_MODELO_FALTANTE")
  files[f"models/{lang}/OPUS_LICENSE.txt"]=optional
 checks={name:digest(p) for name,p in files.items()}
 metadata={"schema":SCHEMA,"files":checks}
 import tempfile,os
 with tempfile.TemporaryDirectory() as d:
  temp=Path(d)/"assets.zip"
  with zipfile.ZipFile(temp,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5,
                       allowZip64=True) as archive:
   for name,p in files.items():archive.write(p,name)
   archive.writestr("manifest.json",json.dumps(metadata,separators=(",",":")))
  length=temp.stat().st_size
  if length>900*1024*1024:raise RuntimeError("IA_PAQUETE_EXCESIVO")
  # Appended ZIP footer: length:uint64 + sha256:32 + marker:16.
  with out.open("xb") as target:
   with executable.open("rb") as src:
    for block in iter(lambda:src.read(1024*1024),b""):target.write(block)
   with temp.open("rb") as src:
    for block in iter(lambda:src.read(1024*1024),b""):target.write(block)
   target.write(struct.pack("<Q",length)+bytes.fromhex(digest(temp))+MAGIC)
 print("IA_TRADUCTORA_SINGLE_EXE_SHA256",digest(out))
if __name__=="__main__":
 a=argparse.ArgumentParser()
 for arg in ("bootstrap","worker","plugin","models","out"):a.add_argument("--"+arg,type=Path,required=True)
 a.add_argument('--vxace-helper',type=Path)
 a.add_argument('--vxace-plugin',type=Path)
 args=a.parse_args()
 build(args.bootstrap,args.worker,args.plugin,args.models,args.out,vxace_helper=args.vxace_helper,vxace_plugin=args.vxace_plugin)
