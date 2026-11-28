"""Servidor Ren'Py: independent game-local translation service."""
from __future__ import annotations
import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCHEMA="ia-servidor-renpy-v1"
SIDECAR="IA Traductora RenPy"
MAX_TEXT=32768
MODEL_CHUNK=900
MAX_BODY=400000
JA=re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9d]")
LETTERS=re.compile(r"[A-Za-z\u00c0-\u024f\u3040-\u30ff\u3400-\u9fff\uff66-\uff9d]")
PERCENT=re.compile(r"%(?:\([A-Za-z_][A-Za-z0-9_]*\))?[-+ #0]*\d*(?:\.\d+)?[diouxXeEfFgGcrsa%]")
PATH=re.compile(r"^(?:[A-Za-z]:[\\/]|https?://|(?:[\w.-]+[/\\])+[\w.-]+$)|\.(?:rpyc?|rpa|png|jpe?g|webp|ogg|mp3|wav|ttf|otf|json|py|exe)$",re.I)
QUOTES=set('"“”「」『』«»')
CODE=re.compile(r"^(?:\$\s+|(?:jump|call|label)\s+[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*:?\s*$|[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*(?:=|\+=|-=|==|!=)\s*[^=]|[A-Za-z_][\w.]*\([^\n]*\)\s*$)")

def protected_parts(text):
    """Never interpret or send Ren'Py interpolation, formatting or escapes."""
    if not isinstance(text,str) or not 0<len(text)<=MAX_TEXT or "\x00" in text:
        raise ValueError("IA_RENPY_TEXTO_INVALIDO")
    parts=[];plain=[];i=0
    def flush():
        if plain:
            parts.append((False,"".join(plain)));plain.clear()
    while i<len(text):
        ch=text[i];end=None
        if text.startswith(("{{","[[","%%","〖〖"),i):end=i+2
        elif ch=="〖":
            j=text.find("〗",i+1)
            if j<0:raise ValueError("IA_RENPY_CONTROL_AMBIGUO")
            end=j+1
        elif ch in QUOTES or ch in "\n\r\t":end=i+1
        elif ch=="\\":
            if i+1>=len(text):raise ValueError("IA_RENPY_CONTROL_AMBIGUO")
            end=i+2
        elif ch=="{":
            j=text.find("}",i+1)
            if j<0 or "{" in text[i+1:j]:raise ValueError("IA_RENPY_CONTROL_AMBIGUO")
            end=j+1
        elif ch=="[":
            depth=1;j=i+1;quote=None
            while j<len(text) and depth:
                c=text[j]
                if quote:
                    if c=="\\":j+=2;continue
                    if c==quote:quote=None
                elif c in "\"'":quote=c
                elif c=="[":depth+=1
                elif c=="]":depth-=1
                j+=1
            if depth or quote:raise ValueError("IA_RENPY_CONTROL_AMBIGUO")
            end=j
        elif ch=="%":
            m=PERCENT.match(text,i)
            if m:end=m.end()
        if end is None:plain.append(ch);i+=1
        else:
            flush();parts.append((True,text[i:end]));i=end
    flush()
    return parts

def language(text):
    s=text.strip()
    if not LETTERS.search(s) or PATH.search(s) or CODE.match(s):return None
    if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+",s) or re.fullmatch(r"[A-Z0-9_]+_\w+",s):return None
    if JA.search(s):return "ja"
    if not re.search("[A-Za-z]",s):return None
    return "en"

def model_chunks(value):
    """Split long visible text, never discard the tail or separator."""
    while len(value)>MODEL_CHUNK:
        window=value[:MODEL_CHUNK]
        matches=list(re.finditer(r"[。！？.!?](?:\s+|(?=[^\s]))|\s+",window))
        end=matches[-1].end() if matches and matches[-1].end()>=MODEL_CHUNK//3 else MODEL_CHUNK
        yield value[:end]
        value=value[end:]
    if value:yield value

def translate_surface(text,neural,quality):
    if not isinstance(text,str) or not LETTERS.search(text) or PATH.search(text.strip()) or CODE.match(text.strip()) or re.fullmatch(r"[A-Z0-9_]+_\w+",text.strip()):return text
    parts=protected_parts(text)
    output=[]
    for control,value in parts:
        if control:
            output.append(value);continue
        for chunk in model_chunks(value):
            left=len(chunk)-len(chunk.lstrip());right=len(chunk.rstrip())
            if right<=left:
                output.append(chunk);continue
            source=chunk[left:right];lang=language(source)
            if lang is None:
                output.append(chunk);continue
            candidate=neural.translate(lang,source)
            if candidate==source:
                output.append(chunk);continue
            if quality(lang,source,candidate):raise ValueError("IA_RENPY_CALIDAD_RECHAZADA")
            if any(flag for flag,_ in protected_parts(candidate)) or any(c in candidate for c in "{}[]\\\x00\r\n\t"):
                raise ValueError("IA_RENPY_CONTROL_INVENTADO")
            output.append(chunk[:left]+candidate+chunk[right:])
    result="".join(output)
    if [v for c,v in protected_parts(result) if c]!=[v for c,v in parts if c]:
        raise ValueError("IA_RENPY_CONTROL_ALTERADO")
    return result

def ordinary(p,directory=False):
    try:
        s=p.lstat()
        return (not stat.S_ISLNK(s.st_mode) and not getattr(s,"st_file_attributes",0)&0x400
                and (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)))
    except OSError:return False

def read_json(p,limit=65536):
    if not ordinary(p) or p.stat().st_size>limit:raise ValueError("IA_RENPY_ARCHIVO_NO_VERIFICADO")
    return json.loads(p.read_text(encoding="utf8"))

def atomic_json(path,data):
    temp=path.parent/(".tmp-"+secrets.token_hex(16))
    try:
        with temp.open("x",encoding="utf8") as f:
            json.dump(data,f,ensure_ascii=True);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()

def installation(root,engine):
    root=root.absolute();side=root/SIDECAR
    if not ordinary(root,True) or not ordinary(side,True) or not ordinary(side/"engine",True) or engine.resolve()!=(side/"engine").resolve():
        raise ValueError("IA_RENPY_MOTOR_NO_VERIFICADO")
    receipt=read_json(side/"owner-v1.json")
    if receipt.get("schema")!=SCHEMA:raise ValueError("IA_RENPY_INSTALACION_NO_VERIFICADA")
    profile=receipt.get("profile") or "modern"
    rel=receipt.get("game_rel") or "game"
    if profile not in ("classic","modern") or not isinstance(rel,str) or not rel or rel==".." or any(c in rel for c in "/\\:\x00") or rel.lower() in ("renpy","lib",SIDECAR.lower()):
        raise ValueError("IA_RENPY_PERFIL_INVALIDO")
    game=root/rel
    boot=game/"ia_servidor_renpy"/"boot.rpy"
    if profile=="classic":boot=game/"zz_ia_servidor_renpy.rpy"
    if not ordinary(game,True) or not ordinary(boot.parent,True):raise ValueError("IA_RENPY_RUTA_INSEGURA")
    for path,key in ((side/"client.py","client_sha256"),(boot,"boot_sha256")):
        if not ordinary(path) or path.stat().st_size>262144 or hashlib.sha256(path.read_bytes()).hexdigest()!=receipt.get(key):
            raise ValueError("IA_RENPY_INSTALACION_NO_VERIFICADA")
    models=receipt.get("engine_sha256",{})
    if not isinstance(models,dict) or not models or not all(isinstance(v,str) and re.fullmatch(r"[0-9a-f]{64}",v) for v in models.values()):
        raise ValueError("IA_RENPY_MANIFIESTO_INVALIDO")
    return side,hashlib.sha256(("surface-v2:"+json.dumps(models,sort_keys=True)).encode()).hexdigest(),receipt

class Memory:
    def __init__(self,folder,identity):
        self.identity=identity
        path=folder/"memory-v1.sqlite3"
        for f in (path,folder/"memory-v1.sqlite3-wal",folder/"memory-v1.sqlite3-shm"):
            if (f.exists() or f.is_symlink()) and not ordinary(f):raise ValueError("IA_RENPY_CACHE_INVALIDA")
        self.db=sqlite3.connect(str(path),timeout=5,check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS memory (model TEXT NOT NULL, original TEXT NOT NULL, output TEXT NOT NULL, PRIMARY KEY(model,original))")
        self.db.commit()
    def get(self,source):
        row=self.db.execute("SELECT output FROM memory WHERE model=? AND original=?",(self.identity,source)).fetchone()
        if row:
            try:
                if [v for c,v in protected_parts(source) if c]==[v for c,v in protected_parts(row[0]) if c] and row[0]!=source:return row[0]
            except ValueError:pass
        return None
    def put(self,source,target):
        self.db.execute("INSERT OR REPLACE INTO memory VALUES(?,?,?)",(self.identity,source,target));self.db.commit()
    def close(self):self.db.close()

class RenpyService:
    def __init__(self,side,identity,neural,quality):
        self.side=side;self.neural=neural;self.quality=quality
        self.memory=Memory(side,identity);self.lock=threading.RLock()
        self.translated=0;self.cached=0;self.rejected=0
        self.token=secrets.token_hex(32)
    def status(self):
        return {"schema":SCHEMA,"translated":self.translated,"cached":self.cached,"rejected":self.rejected}
    def translate(self,text):
        with self.lock:
            try:
                if not isinstance(text,str) or not 0<len(text)<=MAX_TEXT:raise ValueError("IA_RENPY_TEXTO_INVALIDO")
                cached=self.memory.get(text)
                if cached is not None:self.cached+=1;return cached
                target=translate_surface(text,self.neural,self.quality)
                if target!=text:self.memory.put(text,target);self.translated+=1
                return target
            except (RuntimeError,ValueError,TypeError):
                self.rejected+=1;return text
            finally:
                atomic_json(self.side/"status.json",self.status())
    def close(self):self.memory.close()

def handler(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send_json(self,status,body):
            raw=json.dumps(body,ensure_ascii=True).encode("ascii")
            self.send_response(status);self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(raw)));self.end_headers()
            try:self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):pass
        def authorized(self):
            return self.client_address[0]=="127.0.0.1" and secrets.compare_digest(self.headers.get("Authorization",""),"Bearer "+service.token)
        def do_GET(self):
            if not self.authorized():return self.send_json(403,{"error":"IA_RENPY_AUTORIZACION"})
            if self.path!="/status":return self.send_json(404,{"error":"IA_RENPY_RUTA"})
            return self.send_json(200,service.status())
        def do_POST(self):
            if not self.authorized():return self.send_json(403,{"error":"IA_RENPY_AUTORIZACION"})
            if self.path!="/translate":return self.send_json(404,{"error":"IA_RENPY_RUTA"})
            try:
                n=int(self.headers.get("Content-Length","0"))
                if not 0<n<=MAX_BODY:raise ValueError()
                text=json.loads(self.rfile.read(n))["text"]
                if not isinstance(text,str) or not 0<len(text)<=MAX_TEXT:raise ValueError()
            except (ValueError,KeyError,TypeError):return self.send_json(400,{"error":"IA_RENPY_SOLICITUD"})
            return self.send_json(200,{"text":service.translate(text)})
    return Handler

def run_renpy(root,engine,nonce,parent,neural_factory,quality,monitor):
    if not re.fullmatch("[0-9a-f]{32}",nonce) or parent<=0:raise ValueError("IA_RENPY_SESION_INVALIDA")
    side,identity,receipt=installation(root,engine)
    if receipt.get("profile")=="classic":
        key=side/"classic-key.txt"
        if not ordinary(key) or key.stat().st_size!=32:
            raise ValueError("IA_RENPY_CLAVE_INVALIDA")
        raw=key.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=receipt.get("classic_key_sha256") or not secrets.compare_digest(raw,nonce.encode("ascii")):
            raise ValueError("IA_RENPY_CLAVE_INVALIDA")
        from renpy_classic_bridge import run_classic
        return run_classic(side,identity,nonce,parent,neural_factory,engine,quality,monitor,RenpyService,ordinary,atomic_json)
    session=side/("session-"+nonce+".json")
    if session.exists():raise ValueError("IA_RENPY_SESION_EXISTENTE")
    service=RenpyService(side,identity,neural_factory(engine),quality)
    server=None
    try:
        server=ThreadingHTTPServer(("127.0.0.1",0),handler(service))
        server.daemon_threads=False;server.block_on_close=True
        monitor(server,parent)
        atomic_json(session,{"schema":SCHEMA,"nonce":nonce,"port":server.server_port,"token":service.token,"parent":parent})
        server.serve_forever(poll_interval=.25)
    finally:
        if server is not None:server.server_close()
        service.close()
        try:
            if read_json(session).get("nonce")==nonce:session.unlink()
        except (OSError,ValueError):pass
