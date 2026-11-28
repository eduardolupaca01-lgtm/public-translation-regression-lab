#!/usr/bin/env python3
"""Un solo Servidor.exe con manifiesto, firmas y modelos locales propios."""
from __future__ import annotations
import argparse,hashlib,json,struct,zipfile,re,stat
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
WEB_HOST=("Jugar-IA.exe","Jugar-IA.exe.config","Microsoft.Web.WebView2.Core.dll",
          "Microsoft.Web.WebView2.WinForms.dll","WebView2Loader.dll","WebView2-LICENSE.txt")

def json_runtime_assets(root:Path):
 required={"IATraductora.exe","_internal/python311.dll","_internal/base_library.zip"}
 if not root.is_dir() or root.is_symlink() or getattr(root.lstat(),"st_file_attributes",0)&0x400:
  raise ValueError("IA_MV_JSON_RUNTIME_PAQUETE_INVALIDO")
 assets={}
 seen=set()
 for source in sorted(root.rglob("*")):
  st=source.lstat()
  if source.is_symlink() or getattr(st,"st_file_attributes",0)&0x400:
   raise ValueError("IA_MV_JSON_RUNTIME_PAQUETE_INVALIDO")
  if source.is_dir():continue
  rel=source.relative_to(root).as_posix()
  name="json-runtime/"+rel
  if (not stat.S_ISREG(st.st_mode) or st.st_size<=0 or len(name)>200 or
      (rel!="IATraductora.exe" and not rel.startswith("_internal/")) or
      any(not re.fullmatch(r"[A-Za-z0-9_.+ @()-]+",part) or part.endswith(("."," ")) or
          re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])",part.split(".",1)[0],re.I)
          for part in name.split("/")) or name.casefold() in seen):
   raise ValueError("IA_MV_JSON_RUNTIME_PAQUETE_INVALIDO")
  seen.add(name.casefold())
  assets[name]=source
  if len(assets)>1024:raise ValueError("IA_MV_JSON_RUNTIME_PAQUETE_EXCESIVO")
 if not all("json-runtime/"+name in assets for name in required):
  raise ValueError("IA_MV_JSON_RUNTIME_PAQUETE_INCOMPLETO")
 return assets

def build(executable:Path,worker:Path,plugin:Path,models:Path,out:Path,*,vxace_helper=None,vxace_plugin=None,web_host_dir=None,rpgxp_launcher=None,rpgxp_plugin=None,json_runtime_dir=None):
 if not executable.is_file() or not worker.is_file() or not plugin.is_file():
  raise RuntimeError("IA_ARCHIVOS_DE_COMPILACION_INCOMPLETOS")
 if out.resolve() in {executable.resolve(),worker.resolve(),plugin.resolve()}:
  raise RuntimeError("IA_NO_REEMPLAZAR_ORIGINALES")
 files={"IATraductora.exe":worker,"IATraductora.js":plugin}
 if json_runtime_dir is not None:
  assets=json_runtime_assets(json_runtime_dir)
  if out.resolve() in {p.resolve() for p in assets.values()}:raise RuntimeError("IA_NO_REEMPLAZAR_ORIGINALES")
  files.update(assets)
 if (vxace_helper is None)!=(vxace_plugin is None):
  raise ValueError("IA_VXACE_PAQUETE_INCOMPLETO")
 if vxace_helper is not None:
  assets=validated_assets(vxace_helper,vxace_plugin)
  if out.resolve() in {asset.resolve() for asset in assets.values()}:
   raise ValueError("IA_NO_REEMPLAZAR_ORIGINALES")
  files.update(assets)
 if (rpgxp_launcher is None)!=(rpgxp_plugin is None):
  raise ValueError("IA_RPGXP_PAQUETE_INCOMPLETO")
 if rpgxp_launcher is not None:
  for source,limit in ((rpgxp_launcher,128*1024*1024),(rpgxp_plugin,1024*1024)):
   if source.is_symlink() or not source.is_file() or not 0<source.stat().st_size<=limit or source.resolve()==out.resolve():
    raise ValueError("IA_RPGXP_ASSET_INVALIDO")
  with rpgxp_launcher.open("rb") as stream:
   dos=stream.read(64)
   if len(dos)!=64 or dos[:2]!=b"MZ":raise ValueError("IA_RPGXP_LAUNCHER_PE")
   off=int.from_bytes(dos[60:64],"little")
   if not 64<=off<=1024*1024:raise ValueError("IA_RPGXP_LAUNCHER_PE")
   stream.seek(off);h=stream.read(26)
  if len(h)!=26 or h[:4]!=b"PE\0\0" or h[4:6]!=b"\x64\x86" or h[24:26]!=b"\x0b\x02":
   raise ValueError("IA_RPGXP_LAUNCHER_X64")
  raw=rpgxp_plugin.read_bytes()
  if raw.splitlines()[0]!=b"# IA_TRADUCTORA_RPGXP_RGSS1_OWNER_V1" or b"RPGXP-RGSS1-R43-LAB-2" not in raw:
   raise ValueError("IA_RPGXP_PLUGIN_NO_VERIFICADO")
  raw.decode("utf8",errors="strict")
  files["rpgxp-launcher.exe"]=rpgxp_launcher
  files["rpgxp/IATraductoraXP.rb"]=rpgxp_plugin
 if web_host_dir is not None:
  for filename in WEB_HOST:
   source=Path(web_host_dir)/filename
   if (not source.is_file() or source.is_symlink() or not 0<source.stat().st_size<=32*1024*1024
       or source.resolve()==out.resolve()):
    raise RuntimeError("IA_WEB_HOST_PAQUETE_INCOMPLETO")
   files["webhost/"+filename]=source
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
 manifest=json.dumps(metadata,separators=(",",":")).encode("utf8")
 if len(manifest)>256*1024 or sum(p.stat().st_size for p in files.values())+len(manifest)>900*1024*1024:
  raise RuntimeError("IA_PAQUETE_EXCESIVO")
 import tempfile,os
 with tempfile.TemporaryDirectory() as d:
  temp=Path(d)/"assets.zip"
  with zipfile.ZipFile(temp,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5,
                       allowZip64=True) as archive:
   for name,p in files.items():archive.write(p,name)
   archive.writestr("manifest.json",manifest)
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
 a.add_argument('--web-host-dir',type=Path)
 a.add_argument('--rpgxp-launcher',type=Path)
 a.add_argument('--rpgxp-plugin',type=Path)
 a.add_argument('--json-runtime-dir',type=Path)
 args=a.parse_args()
 build(args.bootstrap,args.worker,args.plugin,args.models,args.out,vxace_helper=args.vxace_helper,vxace_plugin=args.vxace_plugin,web_host_dir=args.web_host_dir,rpgxp_launcher=args.rpgxp_launcher,rpgxp_plugin=args.rpgxp_plugin,json_runtime_dir=args.json_runtime_dir)
