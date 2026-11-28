# -*- coding: utf-8 -*-
"""Independent native Ren'Py client; Python 2.7 / 3 compatible."""
from __future__ import unicode_literals
import atexit
import collections
import io
import json
import os
import re
import subprocess
import threading
import time
import binascii
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
def eligible(value):
    return (isinstance(value,text_type) and 0<len(value)<=1800 and bool(LETTERS.search(value))
            and not TECH.search(value.strip()) and not re.match(r"^[A-Z0-9_]+_\w+$",value.strip()))
class Client(object):
    def __init__(self,root):
        self.root=root;self.side=os.path.join(root,SIDECAR);self.nonce=new_nonce()
        self.session=os.path.join(self.side,"session-"+self.nonce+".json")
        self.lock=threading.RLock();self.launch_lock=threading.Lock()
        self.proc=None;self.connection=None;self.cooldown=0
        self.cache=collections.OrderedDict();self.outputs=set()
        self.pending=collections.deque();self.queued=set()
        self.wake=threading.Event();self.stopped=False;self.thread=None
        self.rejected=0;self.fallback=0;self.detected=0
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
                try:
                    self.proc=subprocess.Popen([exe,"--renpy-root",self.root,"--renpy-session",self.nonce,
                        "--parent-pid",str(os.getpid())],cwd=self.side,creationflags=0x08000000 if os.name=="nt" else 0)
                except (OSError,ValueError):
                    self.cooldown=CLOCK()+5;return None
            while CLOCK()<deadline and self.proc.poll() is None:
                try:
                    with io.open(self.session,"r",encoding="utf-8") as f:state=json.loads(f.read(4096))
                    if (state.get("schema")==SCHEMA and state.get("nonce")==self.nonce and state.get("parent")==os.getpid()
                        and isinstance(state.get("port"),int) and 1024<=state["port"]<=65535
                        and re.match(r"^[0-9a-f]{64}$",state.get("token",""))):
                        self.connection=state;return state
                except (IOError,ValueError,TypeError):pass
                time.sleep(.05)
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
            result=json.loads(response.read(65536).decode("utf-8"));target=result.get("text")
            return target if isinstance(target,text_type) else None
        except Exception:return None
        finally:connection.close()
    def remember(self,value,result):
        if not result or value==result:return
        with self.lock:
            if value in self.cache:self.cache.pop(value)
            self.cache[value]=result;self.outputs.add(result)
            if len(self.cache)>8192:
                _,removed=self.cache.popitem(last=False)
                if removed not in self.cache.values():self.outputs.discard(removed)
    def enqueue(self,value):
        if not eligible(value):return
        with self.lock:
            if value in self.cache or value in self.outputs or value in self.queued:return
            self.queued.add(value);self.pending.append(value);self.detected+=1
        self.wake.set()
    def start_prefetch(self):
        if self.thread:return
        self.thread=threading.Thread(target=self.prefetch,name="IA-RenPy-inventory")
        self.thread.daemon=True;self.thread.start()
    def prefetch(self):
        while not self.stopped:
            value=None
            with self.lock:
                if self.pending:value=self.pending.popleft()
            if value is None:self.wake.wait(.25);self.wake.clear();continue
            retry=False
            try:
                with self.lock:ready=value in self.cache
                if not ready:
                    result=self.request(value,CLOCK()+20)
                    self.remember(value,result);retry=result is None
            except Exception:retry=True
            finally:
                with self.lock:
                    if retry and not self.stopped:self.pending.append(value)
                    else:self.queued.discard(value)
            time.sleep(.5 if retry else .02)
    def translate(self,value,foreground=True):
        if not eligible(value):return value
        with self.lock:
            if value in self.outputs:return value
            if value in self.cache:return self.cache[value]
        if not foreground:self.enqueue(value);return value
        result=self.request(value,CLOCK()+12)
        if not result:
            self.fallback+=1;self.enqueue(value);return value
        if result==value:self.rejected+=1;return value
        self.remember(value,result);return result
    def close(self):
        self.stopped=True;self.wake.set()
    def counts(self):return (self.detected,len(self.cache),self.rejected,self.fallback)
def inventory(engine):
    script=getattr(engine.game,"script",None)
    if script is None:return
    stmts=getattr(script,"all_stmts",[]) or []
    if isinstance(stmts,dict):stmts=stmts.values()
    for node in stmts:
        filename=(getattr(node,"filename","") or "").replace("\\","/")
        if "/tl/" in "/"+filename or "/ia_servidor_renpy/" in "/"+filename:continue
        if node.__class__.__name__=="Say":
            value=getattr(node,"what",None)
            if eligible(value):yield value
        elif node.__class__.__name__=="Menu":
            for item in getattr(node,"items",[]):
                if item and eligible(item[0]):yield item[0]
    extra=getattr(getattr(script,"translator",None),"additional_strings",{}) or {}
    if hasattr(extra,"items"):
        for filename,items in extra.items():
            if "/tl/" in "/"+filename.replace("\\","/"):continue
            for item in items:
                if len(item)>=2 and eligible(item[1]):yield item[1]
_installed=False
def install(engine,client=None):
    global _installed
    if _installed:return None
    _installed=True;client=client or Client(engine.config.basedir)
    def foreground():
        try:
            if getattr(engine,"predicting",lambda:False)():return False
            if engine.game.context().init_phase:return False
        except Exception:pass
        return True
    def transform(value):
        try:return client.translate(value,foreground())
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
    if text_cls is not None and hasattr(text_cls,"set_text"):
        previous=text_cls.set_text
        behavior=getattr(getattr(engine,"display",None),"behavior",None)
        input_cls=getattr(behavior,"Input",None)
        def set_text(obj,text,*args,**kwargs):
            value=text
            if (getattr(obj,"tokenized",False) or (input_cls is not None and isinstance(obj,input_cls))
                or any(c.__name__=="Input" for c in type(obj).__mro__)):
                return previous(obj,value,*args,**kwargs)
            if isinstance(value,text_type):value=transform(value)
            elif isinstance(value,list):value=[transform(x) if isinstance(x,text_type) else x for x in value]
            return previous(obj,value,*args,**kwargs)
        text_cls.set_text=set_text
    for text in inventory(engine):client.enqueue(text)
    client.start_prefetch();atexit.register(client.close)
    return client
