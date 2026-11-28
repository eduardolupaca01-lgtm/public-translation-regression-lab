# -*- coding: utf-8 -*-
"""Independent native Ren'Py client; Python 2.7 / 3 compatible."""
from __future__ import unicode_literals
try:
    import atexit
except ImportError:
    atexit=None
import collections
import io
import json
import os
import re
import subprocess
import threading
import time
import binascii
import weakref
try:
    import http.client as http_client
except ImportError:
    import httplib as http_client
try:
    text_type=unicode
except NameError:
    text_type=str
SCHEMA="ia-servidor-renpy-v1"
SIDECAR="IA Traductora RenPy"
CLOCK=getattr(time,"monotonic",time.time)
def new_nonce():
    # Legacy RenPy SDKs omit uuid from their bundled standard library.
    # Keep 128 bits from the OS CSPRNG; do not use time or predictable random.
    return binascii.hexlify(os.urandom(16)).decode("ascii")
TECH=re.compile(r"^(?:https?://|[A-Za-z]:[\\/]|(?:[\w.-]+[/\\])+[\w.-]+$)|\.(?:rpyc?|rpa|png|jpe?g|webp|ogg|mp3|wav|ttf|otf|json|py|exe)$",re.I)
LETTERS=re.compile(u"[A-Za-z\u00c0-\u024f\u3040-\u30ff\u3400-\u9fff\uff66-\uff9d]")
def as_text(value):
    if isinstance(value,text_type):return value
    if isinstance(value,bytes):
        try:return value.decode("utf-8")
        except UnicodeError:return None
    return None
def eligible(value):
    return (isinstance(value,text_type) and 0<len(value)<=32768 and bool(LETTERS.search(value))
            and not TECH.search(value.strip()) and not re.match(r"^[A-Z0-9_]+_\w+$",value.strip()))
class Client(object):
    def __init__(self,root):
        self.root=root;self.side=os.path.join(root,SIDECAR);self.nonce=new_nonce()
        self.session=os.path.join(self.side,"session-"+self.nonce+".json")
        self.lock=threading.RLock();self.launch_lock=threading.Lock()
        self.proc=None;self.connection=None;self.cooldown=0
        self.cache=collections.OrderedDict();self.outputs={}
        self.pending=collections.OrderedDict();self.urgent=collections.OrderedDict()
        self.queued=set();self.seen=set();self.negative=set();self.attempts={}
        self.wake=threading.Event();self.stopped=False;self.thread=None
        self.progress_thread=None
        self.rejected=0;self.fallback=0;self.detected=0
        self.inventory_count=0;self.scan_complete=False;self.applied=0
        self.accepted=0;self.failed=0;self.deferred=0
        self.phase="ESCANEO"
        self.worker_diag=os.path.join(self.side,"worker-startup.json")
        self.diagnostics=set()
    def note(self,code):
        # Fixed codes only. No game text, user paths, or credentials.
        if code in self.diagnostics:return
        self.diagnostics.add(code)
        try:
            with open(os.path.join(self.side,"client-startup.txt"),"ab") as report:
                report.write((code+"\n").encode("ascii"))
        except (IOError,OSError):
            pass
    def get_session(self,deadline):
        if self.connection and self.proc and self.proc.poll() is None:return self.connection
        while CLOCK()<deadline:
            if self.connection and self.proc and self.proc.poll() is None:return self.connection
            if CLOCK()<self.cooldown:return None
            if self.launch_lock.acquire(False):break
            time.sleep(.05)
        else:return None
        try:
            if self.stopped:return None
            if not self.proc or self.proc.poll() is not None:
                self.connection=None;self.nonce=new_nonce()
                self.session=os.path.join(self.side,"session-"+self.nonce+".json")
                exe=os.path.join(self.side,"engine","IATraductora.exe")
                if not os.path.isfile(exe):
                    self.note("IA_RENPY_MOTOR_NO_ENCONTRADO")
                    self.cooldown=CLOCK()+5;return None
                try:
                    # The original game's embedded interpreter can leave
                    # Python 2 runtime settings in its environment. Isolate
                    # the child only; never change the game's environment.
                    env=os.environ.copy()
                    for key in ("PYTHONHOME","PYTHONPATH","PYTHONSTARTUP","_MEIPASS2"):
                        env.pop(key,None)
                    args=[exe,"--renpy-root",self.root,"--renpy-session",self.nonce,
                          "--parent-pid",str(os.getpid()),"--diagnostic-file",self.worker_diag]
                    self.proc=subprocess.Popen(args,cwd=self.side,env=env,
                        creationflags=0x08004000 if os.name=="nt" else 0)
                    self.note("IA_RENPY_MOTOR_INICIADO")
                except Exception as exc:
                    code=getattr(exc,"winerror",None) or getattr(exc,"errno",None)
                    if isinstance(code,int) and 0<=code<=4294967295:
                        self.note("IA_RENPY_MOTOR_INICIO_OS_"+str(code))
                    else:
                        self.note("IA_RENPY_MOTOR_INICIO_FALLO")
                    self.cooldown=CLOCK()+5;return None
            while CLOCK()<deadline and self.proc.poll() is None:
                try:
                    with io.open(self.session,"r",encoding="utf-8") as f:state=json.loads(f.read(4096))
                    if (state.get("schema")==SCHEMA and state.get("nonce")==self.nonce and state.get("parent")==os.getpid()
                        and isinstance(state.get("port"),int) and 1024<=state["port"]<=65535
                        and re.match(r"^[0-9a-f]{64}$",state.get("token",""))):
                        self.connection=state;self.note("IA_RENPY_MOTOR_CONECTADO");return state
                except (IOError,ValueError,TypeError):pass
                time.sleep(.05)
            if self.proc is not None and self.proc.poll() is not None:
                self.note("IA_RENPY_MOTOR_SALIDA_"+str(self.proc.returncode & 0xffffffff))
            else:self.note("IA_RENPY_MOTOR_ESPERANDO")
            self.cooldown=CLOCK()+1;return None
        finally:self.launch_lock.release()
    def request(self,value,deadline):
        state=self.get_session(min(deadline,CLOCK()+5))
        if state is None or deadline<=CLOCK():return None
        connection=http_client.HTTPConnection("127.0.0.1",state["port"],timeout=max(.1,deadline-CLOCK()))
        try:
            raw=json.dumps({"text":value},ensure_ascii=True).encode("ascii")
            connection.request("POST","/translate",raw,{"Authorization":"Bearer "+state["token"],"Content-Type":"application/json"})
            response=connection.getresponse()
            if response.status!=200:return None
            result=json.loads(response.read(400000).decode("utf-8"));target=result.get("text")
            return target if isinstance(target,text_type) else None
        except Exception:return None
        finally:connection.close()
    def remember(self,value,result):
        with self.lock:
            if not result:return
            if value==result:
                if value not in self.negative:
                    self.negative.add(value);self.rejected+=1
                return
            if value in self.cache:return
            self.cache[value]=result
            self.outputs[result]=self.outputs.get(result,0)+1
            self.accepted+=1
            if len(self.cache)>65536:
                _,removed=self.cache.popitem(last=False)
                n=self.outputs.get(removed,0)-1
                if n>0:self.outputs[removed]=n
                else:self.outputs.pop(removed,None)
    def enqueue(self,value,priority=False):
        if not eligible(value):return
        with self.lock:
            if value in self.cache or value in self.negative or value in self.outputs:return
            if value not in self.seen:
                self.seen.add(value);self.detected+=1
            if value in self.queued:
                if priority and value in self.pending:
                    self.pending.pop(value,None);self.urgent[value]=None
                return
            if len(self.queued)>=100000:
                # Report saturation rather than pretend to scan every string.
                self.deferred+=1
                return
            self.queued.add(value)
            (self.urgent if priority else self.pending)[value]=None
        self.wake.set()
    def waiting(self,value):
        with self.lock:return value in self.queued
    def ready(self,value):
        with self.lock:return value in self.cache
    def snapshot(self):
        with self.lock:
            return {"schema":SCHEMA,"phase":self.phase,
                    "scan_complete":self.scan_complete,"inventory":self.inventory_count,
                    "discovered":self.detected,"pending":len(self.queued),
                    "accepted":self.accepted,"unchanged":self.rejected,
                    "transport_failed":self.failed,"deferred":self.deferred,
                    "applied":self.applied,"updated":int(time.time())}
    def publish_progress(self):
        # Per-session temporary file; no dialogue or credentials in the report.
        path=os.path.join(self.side,"client-progress.json")
        temp=path+".tmp-"+self.nonce
        try:
            raw=json.dumps(self.snapshot(),ensure_ascii=True).encode("ascii")
            with open(temp,"wb") as out:out.write(raw)
            if hasattr(os,"replace"):os.replace(temp,path)
            else:
                if os.path.isfile(path):os.unlink(path)
                os.rename(temp,path)
        except (IOError,OSError,ValueError):pass
        finally:
            try:
                if os.path.isfile(temp):os.unlink(temp)
            except (IOError,OSError):pass
    def progress_loop(self):
        while not self.stopped:
            self.publish_progress()
            time.sleep(.75)
    def finish_inventory(self,complete):
        with self.lock:
            self.inventory_count=len(self.seen);self.scan_complete=bool(complete)
            self.phase="CONECTANDO"
    def start_progress(self):
        if self.progress_thread:return
        self.progress_thread=threading.Thread(target=self.progress_loop,name="IA-RenPy-progress")
        self.progress_thread.daemon=True;self.progress_thread.start()
    def start_prefetch(self):
        if self.thread:return
        self.start_progress()
        self.thread=threading.Thread(target=self.prefetch,name="IA-RenPy-inventory")
        self.thread.daemon=True;self.thread.start()
    def prefetch(self):
        # Only this thread performs I/O, process creation and inference calls.
        # Never hold the cache lock while doing any of those operations.
        burst=0
        while not self.stopped:
            try:connection=self.get_session(CLOCK()+25)
            except Exception:
                connection=None;self.note("IA_RENPY_MOTOR_CONEXION_FALLO")
            if not connection:
                with self.lock:self.phase="ESPERANDO_MOTOR"
                time.sleep(2);continue
            with self.lock:
                self.phase="TRADUCIENDO" if self.queued else "LISTO"
                value=None
                # Visible strings take priority, with fairness for the scan.
                if self.urgent and (burst<8 or not self.pending):
                    value,_=self.urgent.popitem(last=False);burst+=1
                elif self.pending:
                    value,_=self.pending.popitem(last=False);burst=0
            if value is None:
                self.wake.wait(.25);self.wake.clear();continue
            result=None
            try:result=self.request(value,CLOCK()+90)
            except Exception:pass
            if result is not None:self.remember(value,result)
            with self.lock:
                if result is None:
                    n=self.attempts.get(value,0)+1
                    if n<3 and not self.stopped:
                        self.attempts[value]=n;self.pending[value]=None
                    else:
                        self.attempts.pop(value,None);self.queued.discard(value)
                        self.negative.add(value);self.failed+=1
                else:
                    self.attempts.pop(value,None);self.queued.discard(value)
            time.sleep(.5 if result is None else .04)
    def translate(self,value,foreground=True):
        # A Text constructor, say filter, or screen prediction must NEVER
        # wait on the worker. Cache lookup + enqueue only; fail open instantly.
        if not eligible(value):return value
        with self.lock:
            if value in self.cache:
                self.applied+=1
                return self.cache[value]
            if value in self.outputs or value in self.negative:return value
            if foreground:self.fallback+=1
        self.enqueue(value,priority=foreground)
        return value
    def close(self):
        self.stopped=True;self.wake.set()
    def counts(self):return (self.detected,self.accepted,self.rejected,self.fallback)

def inventory(engine):
    # Inspect the engine's already-loaded AST, including scripts inside RPA;
    # never deserialize game archives outside their native engine or run code.
    script=getattr(engine.game,"script",None)
    if script is None:return
    stmts=getattr(script,"all_stmts",[]) or []
    if isinstance(stmts,dict):stmts=stmts.values()
    def visible_node(node):
        filename=(getattr(node,"filename","") or "").replace("\\","/")
        return "/tl/" not in "/"+filename and "/ia_servidor_renpy/" not in "/"+filename
    for node in stmts:
        if not visible_node(node):continue
        if node.__class__.__name__=="Say":
            value=as_text(getattr(node,"what",None))
            if eligible(value):yield value
        elif node.__class__.__name__=="Menu":
            for item in getattr(node,"items",[]):
                if item:
                    value=as_text(item[0])
                    if eligible(value):yield value
    translator=getattr(script,"translator",None)
    # Some engines keep dialogue in their translation-block registry after
    # releasing all_stmts. This is a read-only second source; queue deduplicates.
    blocks=getattr(translator,"default_translates",{}) or {}
    if hasattr(blocks,"values"):
        for block in blocks.values():
            if not visible_node(block):continue
            for node in getattr(block,"block",[]) or []:
                if node.__class__.__name__=="Say" and visible_node(node):
                    value=as_text(getattr(node,"what",None))
                    if eligible(value):yield value
    extra=getattr(translator,"additional_strings",{}) or {}
    if hasattr(extra,"items"):
        for filename,items in extra.items():
            if "/tl/" in "/"+filename.replace("\\","/"):continue
            for item in items:
                if len(item)>=2:
                    value=as_text(item[1])
                    if eligible(value):yield value
_installed=False
def install(engine,client=None):
    global _installed
    if _installed:return None
    client=client or Client(engine.config.basedir)
    def foreground():
        try:
            if getattr(engine,"predicting",lambda:False)():return False
            if engine.game.context().init_phase:return False
        except Exception:pass
        return True
    waiters=collections.OrderedDict()
    live_client=isinstance(client,Client)
    last_refresh=[0]
    def transform(value,missing=None,live=None):
        source=as_text(value)
        if not eligible(source):return value
        try:
            if live is None:live=foreground()
            result=client.translate(source,live)
            if live_client and live and missing is not None and result==source and client.waiting(source):
                missing.add(source)
            return result
        except Exception:return value
    config=engine.config
    if hasattr(config,"say_menu_text_filter"):
        prior=config.say_menu_text_filter
        def say_filter(value):
            if prior is not None:value=prior(value)
            return transform(value)
        config.say_menu_text_filter=say_filter
    elif hasattr(config,"say_menu_text_filters"):
        config.say_menu_text_filters=list(config.say_menu_text_filters)+[transform]
    native=getattr(getattr(engine,"text",None),"text",None);text_cls=getattr(native,"Text",None)
    if text_cls is None or not hasattr(text_cls,"set_text"):
        raise ValueError("IA_RENPY_CLASE_TEXTO_NO_VERIFICADA")
    _installed=True
    if text_cls is not None and hasattr(text_cls,"set_text"):
        previous=text_cls.set_text
        behavior=getattr(getattr(engine,"display",None),"behavior",None)
        input_cls=getattr(behavior,"Input",None)
        def set_text(obj,text,*args,**kwargs):
            # No network, disk access, or waiting on the game thread.
            value=text
            object_id=id(obj);waiters.pop(object_id,None)
            live=foreground();missing=set()
            if ((input_cls is not None and isinstance(obj,input_cls))
                or any(c.__name__=="Input" for c in type(obj).__mro__)):
                return previous(obj,value,*args,**kwargs)
            if getattr(obj,"tokenized",False):
                # Only an explicit native visible-text token is eligible.
                kind=getattr(engine,"TEXT_TEXT",None)
                if kind is not None and isinstance(value,(list,tuple)):
                    items=[]
                    for token in value:
                        if isinstance(token,tuple) and len(token)==2 and token[0]==kind:
                            token=(token[0],transform(token[1],missing,live))
                        items.append(token)
                    value=tuple(items) if isinstance(value,tuple) else items
            else:
                if as_text(value) is not None:value=transform(value,missing,live)
                elif isinstance(value,list):value=[transform(x,missing,live) if as_text(x) is not None else x for x in value]
            result=previous(obj,value,*args,**kwargs)
            if live_client and missing and live and kwargs.get("update",True) and not getattr(obj,"locked",False):
                try:
                    # Only remember the latest setter for a live native object.
                    # Weak references avoid retaining old screens and dialogue.
                    waiters[object_id]=(weakref.ref(obj),text,args,dict(kwargs),missing,getattr(obj,"text",None))
                    if len(waiters)>512:waiters.popitem(last=False)
                except TypeError:pass
            return result
        text_cls.set_text=set_text
        def refresh_pending():
            # Called by Ren'Py's periodic callback on the MAIN thread only.
            # Refresh the object using its real setter, not a global restart.
            now=CLOCK()
            if now-last_refresh[0]<.20 or not foreground():return
            last_refresh[0]=now
            for _ in range(min(64,len(waiters))):
                try:key,record=waiters.popitem(last=False)
                except KeyError:break
                ref,source,args,kwargs,missing,snapshot=record
                obj=ref()
                if obj is None or getattr(obj,"locked",False) or getattr(obj,"text",None) is not snapshot:continue
                if any(client.ready(s) for s in missing):
                    try:set_text(obj,source,*args,**kwargs)
                    except Exception:pass
                elif any(client.waiting(s) for s in missing):
                    waiters[key]=record
        if live_client and hasattr(config,"periodic_callbacks"):
            config.periodic_callbacks.append(refresh_pending)
        elif live_client and hasattr(config,"periodic_callback"):
            old_periodic=config.periodic_callback
            def periodic():
                if old_periodic:old_periodic()
                refresh_pending()
            config.periodic_callback=periodic
    complete=True
    if live_client:client.start_progress()
    try:
        for text in inventory(engine):client.enqueue(text)
    except Exception:
        complete=False
        if hasattr(client,"note"):client.note("IA_RENPY_INVENTARIO_PARCIAL")
    if live_client:client.finish_inventory(complete)
    client.start_prefetch()
    if atexit is not None:atexit.register(client.close)
    return client
