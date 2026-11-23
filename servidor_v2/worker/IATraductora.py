#!/usr/bin/env python3
"""IA Traductora, motor neuronal independiente. Sólo 127.0.0.1, sin nube."""
from __future__ import annotations
import argparse, hashlib, json, os, secrets, sys, threading, time
from pathlib import Path
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCHEMA="ia-traductora-bridge-v1"
MAX_TEXT=1800
MODELS={"ja":"opus_ja_es","en":"opus_en_es"}

class NeuralOPUS:
    def __init__(self, engine:Path):
        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as exc:
            raise RuntimeError("IA_DEPENDENCIAS_MODELO_FALTANTES") from exc
        self.models={}
        for lang,name in MODELS.items():
            root=engine/"models"/name
            for file in ("model.bin","source.spm","target.spm"):
                if not (root/file).is_file():
                    raise RuntimeError("IA_MODELO_INCOMPLETO")
            source=spm.SentencePieceProcessor(model_file=str(root/"source.spm"))
            target=spm.SentencePieceProcessor(model_file=str(root/"target.spm"))
            model=ctranslate2.Translator(str(root),device="cpu",compute_type="int8",inter_threads=1)
            self.models[lang]=(model,source,target)
        self.lock=threading.Lock()

    def translate(self,lang:str,text:str)->str:
        model,src,dst=self.models[lang]
        tokens=src.encode(text,out_type=str)
        if not tokens: raise ValueError("IA_TEXTO_VACIO")
        with self.lock:
            result=model.translate_batch([tokens],beam_size=4,max_decoding_length=300)
        return dst.decode(result[0].hypotheses[0]).strip()

def game_root(exe_root:Path)->tuple[Path,Path]:
    root=exe_root.resolve(strict=True)
    if root.is_symlink() or not root.is_dir():raise ValueError("IA_JUEGO_NO_VALIDO")
    layouts=[p for p in (root/"www",root) if
             (p/"js"/"rpg_core.js").is_file() and (p/"js"/"plugins.js").is_file()
             and (p/"data"/"System.json").is_file()]
    if len(layouts)!=1:raise ValueError("IA_SOLAMENTE_RPG_MV")
    return root,layouts[0]

class Service:
    def __init__(self,game:Path,engine:Path,neural=None):
        self.game,self.content=game_root(game)
        engine=engine.resolve(strict=True)
        if engine.is_symlink() or not engine.is_relative_to(self.game):
            raise ValueError("IA_MOTOR_FUERA_DEL_JUEGO")
        self.engine=engine
        self.neural=neural if neural is not None else NeuralOPUS(engine)
        self.token=secrets.token_hex(32)
        self.translations=0
        self.failures=0
        self.cache=OrderedDict()
        self.lock=threading.Lock()

    def translate(self,lang,text):
        if lang not in MODELS or not isinstance(text,str) or not (0<len(text)<=MAX_TEXT):
            raise ValueError("IA_SOLICITUD_INVALIDA")
        key=hashlib.sha256((lang+"\0"+text).encode()).hexdigest()
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key);return self.cache[key]
        output=self.neural.translate(lang,text)
        if not isinstance(output,str) or not output.strip() or output.strip()==text.strip():
            raise RuntimeError("IA_NO_TRADUJO")
        with self.lock:
            self.cache[key]=output
            while len(self.cache)>3000:self.cache.popitem(last=False)
            self.translations+=1
        return output

def make_handler(service:Service):
    class Handler(BaseHTTPRequestHandler):
        server_version="IATraductora/1"
        sys_version=""
        def log_message(self,*_):pass
        def send(self,status,obj):
            body=json.dumps(obj,ensure_ascii=False).encode("utf8")
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def allowed(self):return secrets.compare_digest(self.headers.get("X-IA-Token",""),service.token)
        def do_GET(self):
            if not self.allowed():return self.send(403,{"error":"IA_TOKEN_INVALIDO"})
            if self.path!="/status":return self.send(404,{"error":"IA_RUTA_INVALIDA"})
            self.send(200,{"schema":SCHEMA,"active":True,
                "translated":service.translations,"failed":service.failures,
                "cache":len(service.cache)})
        def do_POST(self):
            if not self.allowed():return self.send(403,{"error":"IA_TOKEN_INVALIDO"})
            if self.path!="/translate":return self.send(404,{"error":"IA_RUTA_INVALIDA"})
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not (0<length<=8192):raise ValueError("IA_TAMANO")
                data=json.loads(self.rfile.read(length).decode("utf8"))
                if not isinstance(data,dict) or data.get("target")!="es":
                    raise ValueError("IA_IDIOMA")
                answer=service.translate(data.get("source"),data.get("text"))
                self.send(200,{"translated":answer,"source":data["source"],"target":"es"})
            except (ValueError,UnicodeError):
                self.send(400,{"error":"IA_SOLICITUD_INVALIDA"})
            except Exception:
                service.failures+=1
                self.send(503,{"error":"IA_MOTOR_FALLO"})
    return Handler

def publish(service,port):
    folder=service.content/"data"/"IATraductora"
    folder.mkdir(exist_ok=True,mode=0o700)
    if folder.is_symlink() or not folder.resolve().is_relative_to(service.game):
        raise RuntimeError("IA_PUENTE_INSEGURO")
    dest=folder/"bridge.json"
    if dest.is_symlink():raise RuntimeError("IA_PUENTE_INSEGURO")
    item={"schema":SCHEMA,"token":service.token,"port":port,
          "pid":os.getpid(),"start_unix":int(time.time())}
    tmp=folder/(".ia-"+secrets.token_hex(12)+".tmp")
    try:
        with tmp.open("x",encoding="utf8") as f:
            json.dump(item,f)
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,dest)
    finally:
        if tmp.exists():tmp.unlink()
    return dest

def run(service):
    http=ThreadingHTTPServer(("127.0.0.1",0),make_handler(service))
    dest=publish(service,http.server_port)
    try:http.serve_forever(poll_interval=0.5)
    finally:
        http.server_close()
        try:
            state=json.loads(dest.read_text("utf8"))
            if state.get("token")==service.token:dest.unlink()
        except (OSError,ValueError):pass

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--game-root",type=Path,required=True)
    p.add_argument("--parent-pid",type=int,default=0)
    args=p.parse_args()
    path=Path(sys.executable if getattr(sys,"frozen",False) else __file__).resolve().parent
    run(Service(args.game_root,path))

if __name__=="__main__":main()
