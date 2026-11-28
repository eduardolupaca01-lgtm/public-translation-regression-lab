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
        self.scan_report={}
        self.prepare_id=""
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
        # Do not spawn a second worker while another verified local session
        # is active. Never attach to a foreign or stale session.
        try:
            if any(n.startswith("session-") and n.endswith(".json") and n!=os.path.basename(self.session) for n in os.listdir(self.side)):
                self.note("IA_RENPY_OTRA_SESION_PRESENTE");return None
        except (IOError,OSError):pass
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
                    "applied":self.applied,"updated":int(time.time()),
                    "preparation_id":self.prepare_id,"scan":dict(self.scan_report)}
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

def expression_texts(source,visible=False):
    """Inspect only literal text in a known presentation position.
    Never evaluate the expression, import game code, or walk arbitrary objects.
    Python 2 and 3 ASTs both expose literal strings as Str.s.
    """
    try:import ast
    except ImportError:return
    if isinstance(source,ast.AST):tree=source
    else:
        source=as_text(source)
        if not source or len(source)>524288:return
        try:tree=ast.parse(source.strip())
        except (SyntaxError,ValueError,TypeError,UnicodeError):
            try:tree=ast.parse(source,mode="exec")
            except (SyntaxError,ValueError,TypeError,UnicodeError):return
    def name(node):
        if isinstance(node,ast.Name):return node.id
        if isinstance(node,ast.Attribute):
            prefix=name(node.value)
            if prefix:return prefix+"."+node.attr
        return ""
    def literals(node):
        if isinstance(node,ast.Str):
            value=as_text(node.s)
            if eligible(value):yield value
        elif isinstance(node,ast.IfExp):
            for part in (node.body,node.orelse):
                for value in literals(part):yield value
        elif isinstance(node,ast.Call) and name(node.func) in ("_","__","_p"):
            if node.args:
                for value in literals(node.args[0]):yield value
        elif isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add) and isinstance(node.left,ast.Str) and isinstance(node.right,ast.Str):
            a=as_text(node.left.s);b=as_text(node.right.s)
            if a is not None and b is not None and eligible(a+b):yield a+b
    if visible:
        node=tree.body[0].value if isinstance(tree,ast.Module) and len(tree.body)==1 and isinstance(tree.body[0],ast.Expr) else None
        if node is not None:
            for value in literals(node):yield value
    first=("_","__","_p","Character","renpy.character.Character","Text","renpy.text.text.Text","renpy.display.text.Text","renpy.notify","renpy.confirm","renpy.input","ui.text","ui.textbutton","ui.label","renpy.exports.notify","renpy.exports.confirm","renpy.exports.input")
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call):continue
        kind=name(node.func)
        index=1 if kind in ("renpy.say","renpy.exports.say") else 0
        if kind not in first and kind not in ("renpy.say","renpy.exports.say"):continue
        if len(node.args)>index:
            for value in literals(node.args[index]):yield value
        else:
            key="what" if index==1 else "prompt" if kind.endswith("input") else "message" if kind.endswith(("notify","confirm")) else "name" if kind.endswith("Character") else "text"
            for keyword in node.keywords:
                if keyword.arg==key:
                    for value in literals(keyword.value):yield value

def screen_texts(screen,report):
    # Native SL2 tree: inspect text, textbutton and label positional arguments,
    # including branches that have never been evaluated. Do not execute screens.
    stack=[screen];seen=set()
    while stack:
        node=stack.pop()
        if node is None or id(node) in seen:continue
        seen.add(id(node));report["screen_nodes"]+=1
        kind=node.__class__.__name__
        if kind=="SLDisplayable":
            fn=getattr(node,"displayable",None)
            if getattr(fn,"__name__","") in ("Text","_textbutton","_label","textbutton","label"):
                args=getattr(node,"positional",[]) or []
                if args:
                    for value in expression_texts(args[0],True):yield value
            # Explicit translation calls may also occur in other properties.
            for key,expr in getattr(node,"keyword",[]) or []:
                for value in expression_texts(expr,key in ("tooltip","alt","text","label")):yield value
        elif kind in ("SLPython","SLDefault"):
            code=getattr(node,"code",None)
            for value in expression_texts(getattr(code,"source",code)):yield value
        for child in reversed(getattr(node,"children",[]) or []):stack.append(child)
        for entry in reversed(getattr(node,"entries",[]) or []):
            if isinstance(entry,(list,tuple)) and len(entry)>=2:stack.append(entry[1])
        block=getattr(node,"block",None)
        if block is not None and not isinstance(block,(list,tuple)):stack.append(block)

def inventory(engine,report=None):
    if report is None:report={}
    report.update({"script_files":0,"archived_scripts":0,"loose_scripts":0,
                   "native_nodes":0,"screen_nodes":0,"partial":False})
    script=getattr(engine.game,"script",None)
    if script is None:
        report["partial"]=True;return
    loader=getattr(engine,"loader",None)
    if loader is not None and hasattr(loader,"listdirfiles"):
        try:
            try:entries=loader.listdirfiles(common=False)
            except TypeError:entries=loader.listdirfiles()
            files=set()
            for directory,filename in entries:
                name=as_text(filename)
                if not name or not name.lower().endswith((".rpy",".rpyc",".rpym",".rpymc",".py")):continue
                if "/ia_servidor_renpy/" in "/"+name.replace("\\","/") or "/tl/" in "/"+name.replace("\\","/"):continue
                key=(directory is None,name)
                if key in files:continue
                files.add(key)
                report["archived_scripts" if directory is None else "loose_scripts"]+=1
            report["script_files"]=len(files)
        except Exception:report["partial"]=True
    def visible_node(node):
        filename=(getattr(node,"filename","") or "").replace("\\","/")
        return "/tl/" not in "/"+filename and "/ia_servidor_renpy/" not in "/"+filename
    def nodes():
        stmts=getattr(script,"all_stmts",[]) or []
        if isinstance(stmts,dict):stmts=stmts.values()
        for node in stmts:yield node
        named=getattr(script,"namemap",{}) or {}
        if hasattr(named,"values"):
            for node in named.values():yield node
        translator=getattr(script,"translator",None)
        blocks=getattr(translator,"default_translates",{}) or {}
        if hasattr(blocks,"values"):
            for block in blocks.values():
                if visible_node(block):
                    for node in getattr(block,"block",[]) or []:yield node
    seen=set()
    for node in nodes():
        if node is None or id(node) in seen or not visible_node(node):continue
        seen.add(id(node));report["native_nodes"]+=1
        kind=node.__class__.__name__
        if kind=="Say":
            value=as_text(getattr(node,"what",None))
            if eligible(value):yield value
        elif kind=="Menu":
            for item in getattr(node,"items",[]) or []:
                if item:
                    value=as_text(item[0])
                    if eligible(value):yield value
        elif kind=="Screen":
            try:
                for value in screen_texts(getattr(node,"screen",None),report):yield value
            except Exception:report["partial"]=True
        elif kind in ("Python","EarlyPython","Define","Default"):
            try:
                for value in expression_texts(getattr(getattr(node,"code",None),"source",None)):yield value
            except Exception:report["partial"]=True
    translator=getattr(script,"translator",None)
    extra=getattr(translator,"additional_strings",{}) or {}
    if hasattr(extra,"items"):
        for filename,items in extra.items():
            if "/tl/" in "/"+filename.replace("\\","/") or "/ia_servidor_renpy/" in "/"+filename.replace("\\","/"):continue
            for item in items:
                if len(item)>=2:
                    value=as_text(item[1])
                    if eligible(value):yield value

def prepare_ticket(engine,client):
    """The original native command is opt-in and never enters a game label."""
    args=getattr(engine.game,"args",None)
    requested=getattr(args,"command",None)=="ia_renpy_prepare"
    ticket=os.path.join(client.side,"prepare-request.json")
    if not requested:
        if os.path.isfile(ticket):raise ValueError("IA_RENPY_PREPARACION_EN_CURSO")
        return
    nonce=os.environ.get("IA_RENPY_PREPARE_ID","")
    if not re.match(r"^[0-9a-f]{32}$",nonce):raise ValueError("IA_RENPY_PREPARACION_INVALIDA")
    with io.open(ticket,"r",encoding="utf-8") as inp:request=json.loads(inp.read(4096))
    if request.get("schema")!=SCHEMA or request.get("id")!=nonce:raise ValueError("IA_RENPY_PREPARACION_INVALIDA")
    api=getattr(engine,"arguments",None)
    if api is None or not hasattr(api,"register_command"):raise ValueError("IA_RENPY_PREPARACION_NO_COMPATIBLE")
    client.prepare_id=nonce
    def prepare():
        api.takes_no_arguments("IA Traductora: preparar textos antes de jugar")
        cancel=os.path.join(client.side,"prepare-cancel-"+nonce+".txt")
        result=os.path.join(client.side,"prepare-result-"+nonce+".json")
        state="IA_RENPY_PREPARACION_INCOMPLETA"
        last=None;changed=CLOCK();started=CLOCK()
        try:
            while not client.stopped:
                p=client.snapshot()
                if os.path.isfile(cancel):
                    state="IA_RENPY_PREPARACION_CANCELADA";break
                if p["scan_complete"] and p["pending"]==0 and client.connection:
                    if not p["transport_failed"] and not p["deferred"]:state="IA_RENPY_PREPARACION_LISTA"
                    break
                if not p["scan_complete"] and p["pending"]==0:break
                progress=(p["accepted"],p["unchanged"],p["transport_failed"],p["pending"])
                if progress!=last:last=progress;changed=CLOCK()
                if (not client.connection and CLOCK()-started>60) or CLOCK()-changed>180:break
                time.sleep(.25)
            data=client.snapshot();data["result"]=state;data["id"]=nonce
            # Ticket-specific result written atomically; zero launcher exit
            # alone is never a completion signal.
            temp=result+".tmp"
            with open(temp,"wb") as out:out.write(json.dumps(data,ensure_ascii=True).encode("ascii"))
            os.rename(temp,result)
        finally:
            client.close()
        return False
    api.register_command("ia_renpy_prepare",prepare)

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
    if live_client:prepare_ticket(engine,client)
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
    report={}
    try:
        for text in inventory(engine,report):client.enqueue(text)
        complete=not report.get("partial",False)
    except Exception:
        complete=False
        if hasattr(client,"note"):client.note("IA_RENPY_INVENTARIO_PARCIAL")
    if live_client:
        client.scan_report=report
        client.finish_inventory(complete)
        client.publish_progress()
    client.start_prefetch()
    if atexit is not None:atexit.register(client.close)
    return client
