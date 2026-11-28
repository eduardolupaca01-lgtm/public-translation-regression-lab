"""Original classic Ren'Py client. Python 2.3 grammar and minimal stdlib.

No JSON, hashlib, subprocess, uuid, socket, or third-party module required.
Only the added displayable adapter and an authenticated local file session.
"""
import os
import time
import sys
try:
    import threading
except ImportError:
    threading=None
try:
    import atexit
except ImportError:
    atexit=None
try:
    text_type=unicode
    byte_type=str
except NameError:
    text_type=str
    byte_type=bytes
SCHEMA="ia-renpy-classic-v1"
SIDE="IA Traductora RenPy"

def read_small(path,limit):
    f=open(path,"rb")
    try:
        raw=f.read(limit+1)
    finally:
        f.close()
    if len(raw)>limit:
        raise ValueError("IA_RENPY_ARCHIVO_EXCESIVO")
    return raw

def write_new(path,raw):
    # The worker exclusively creates this private session directory.
    # Each monotonically increasing request has its own name.
    if os.path.exists(path):
        raise ValueError("IA_RENPY_SOLICITUD_EXISTENTE")
    temp=path+".tmp"
    if os.path.exists(temp):
        raise ValueError("IA_RENPY_SOLICITUD_EXISTENTE")
    f=open(temp,"wb")
    try:
        f.write(raw)
        f.flush()
    finally:
        f.close()
    os.rename(temp,path)

def hex_string(value,length):
    if len(value)!=length:
        return False
    for c in value:
        if c not in "0123456789abcdef":
            return False
    return True

def as_text(value):
    if isinstance(value,text_type):
        return value
    if isinstance(value,byte_type):
        try:
            return value.decode("utf-8")
        except UnicodeError:
            return None
    return None

def visible_probe(s):
    """Remove controls ONLY from the eligibility probe, never from the text
    sent to the worker. A closing {/b} is not a filesystem path.
    The worker separately validates exact control preservation."""
    result=[]
    i=0
    while i<len(s):
        if s.startswith("{{",i) or s.startswith("[[",i):
            result.append(s[i])
            i+=2
            continue
        if s[i]=="{":
            end=s.find("}",i+1)
            if end>=0:
                i=end+1
                continue
        if s[i]=="[":
            end=s.find("]",i+1)
            if end>=0:
                i=end+1
                continue
        result.append(s[i])
        i+=1
    return u"".join(result)

def visible(value):
    s=as_text(value)
    if s is None or not 0<len(s)<=32768:
        return False
    v=visible_probe(s).strip()
    if not v or v.startswith("http://") or v.startswith("https://"):
        return False
    low=v.lower()
    for ext in (".rpy",".rpyc",".rpa",".png",".jpg",".jpeg",".ogg",".mp3",".wav",".ttf",".otf",".exe",".py"):
        if low.endswith(ext):
            return False
    # No attempt to infer or rewrite filenames or internal identifiers.
    if "/" in v or "\\" in v:
        if " " not in v:
            return False
    if "_" in v and " " not in v and v.upper()==v:
        return False
    for c in v:
        if c.isalpha():
            return True
    return False

def root_for(engine):
    choices=[]
    config=getattr(engine,"config",None)
    for value in (getattr(config,"basedir",None),getattr(config,"gamedir",None),getattr(engine.game,"basepath",None)):
        if value:
            value=os.path.abspath(value)
            choices.append(value)
            choices.append(os.path.dirname(value))
    seen={}
    for p in choices:
        if os.path.isfile(os.path.join(p,SIDE,"classic-key.txt")):
            seen[os.path.normcase(p)]=p
    if len(seen)!=1:
        raise ValueError("IA_RENPY_RAIZ_CLASICA_NO_VERIFICADA")
    return list(seen.values())[0]

def launch_worker(exe,root,nonce):
    # Windows os.spawnv exists on the Python 2.3-era runtime. No shell.
    args=[exe,"--renpy-root",root,"--renpy-session",nonce,"--parent-pid",str(os.getpid())]
    if os.name=="nt":
        fixed=[]
        for arg in args:
            if isinstance(arg,text_type):
                # Old Python on Windows cannot launch paths outside its
                # current ANSI code page. Fail closed rather than corrupt it.
                if sys.version_info[0]<3:
                    arg=arg.encode("mbcs")
            if '"' in arg:
                raise ValueError("IA_RENPY_RUTA_INVALIDA")
            if " " in arg:
                arg='"'+arg+'"'
            fixed.append(arg)
        args=fixed
        if sys.version_info[0]<3 and isinstance(exe,text_type):
            exe=exe.encode("mbcs")
    return os.spawnv(os.P_NOWAIT,exe,args)

class Client(object):
    def __init__(self,root):
        self.root=root
        self.side=os.path.join(root,SIDE)
        self.nonce=read_small(os.path.join(self.side,"classic-key.txt"),32).decode("utf-8")
        if not hex_string(self.nonce,32):
            raise ValueError("IA_RENPY_CLAVE_INVALIDA")
        self.session=os.path.join(self.side,"classic-session-"+self.nonce)
        self.started=False
        self.token=None
        self.sequence=0
        self.stopped=False
        self.cache={}
        self.outputs={}
        self.pending=[]
        self.queued={}
        self.thread=None
        self.lock=None
        if threading is not None:
            self.lock=threading.RLock()
    def acquire(self):
        if self.lock is not None:
            self.lock.acquire()
    def release(self):
        if self.lock is not None:
            self.lock.release()
    def connect(self,deadline):
        if not self.started:
            # A stale or another game's session is never adopted.
            if os.path.exists(self.session):
                return False
            exe=os.path.join(self.side,"engine","IATraductora.exe")
            launch_worker(exe,self.root,self.nonce)
            self.started=True
        while time.time()<deadline and not self.stopped:
            try:
                raw=read_small(os.path.join(self.session,"ready.txt"),512).decode("utf-8")
                fields=raw.split("\n")
                if len(fields)==4 and fields[0]==SCHEMA and fields[1]==self.nonce and fields[2]==str(os.getpid()) and hex_string(fields[3],64):
                    self.token=fields[3]
                    return True
            except (IOError,OSError,ValueError,UnicodeError):
                pass
            time.sleep(.05)
        return False
    def request(self,value):
        deadline=time.time()+12.0
        if self.token is None:
            if not self.connect(deadline):
                return None
        self.sequence+=1
        seq="%08d"%self.sequence
        if len(seq)!=8:
            return None
        req=os.path.join(self.session,"request-"+seq+".txt")
        answer=os.path.join(self.session,"response-"+seq+".txt")
        prefix=(self.token+"\n"+seq+"\n").encode("utf-8")
        write_new(req,prefix+value.encode("utf-8"))
        while time.time()<deadline and not self.stopped:
            try:
                raw=read_small(answer,140000)
                if raw.startswith(prefix):
                    result=raw[len(prefix):].decode("utf-8")
                    os.unlink(answer)
                    return result
            except (IOError,OSError,ValueError,UnicodeError):
                pass
            time.sleep(.04)
        return None
    def enqueue(self,value):
        value=as_text(value)
        if not visible(value):
            return
        self.acquire()
        try:
            if value not in self.cache and value not in self.queued and value not in self.outputs and len(self.pending)<20000:
                self.queued[value]=True
                self.pending.append(value)
        finally:
            self.release()
    def start_prefetch(self):
        # If the bundled interpreter omits threading, foreground still
        # works. Do not install libraries in the user's game.
        if threading is None or self.thread is not None:
            return
        self.thread=threading.Thread(target=self.prefetch)
        self.thread.setDaemon(True)
        self.thread.start()
    def prefetch(self):
        while not self.stopped:
            value=None
            self.acquire()
            try:
                if self.pending:
                    value=self.pending.pop(0)
                    self.queued.pop(value,None)
            finally:
                self.release()
            if value is None:
                time.sleep(.15)
            else:
                self.translate(value,True)
                time.sleep(.04)
    def translate(self,value,foreground=True):
        original=value
        value=as_text(value)
        if not visible(value):
            return original
        self.acquire()
        try:
            if value in self.outputs:
                return original
            if value in self.cache:
                return self.cache[value]
            if not foreground:
                self.enqueue(value)
                return original
            try:
                result=self.request(value)
            except (IOError,OSError,ValueError,UnicodeError):
                return original
            if result and result!=value:
                if len(self.cache)>=8192:
                    self.cache.clear()
                    self.outputs.clear()
                self.cache[value]=result
                self.outputs[result]=True
                return result
            return original
        finally:
            self.release()
    def close(self):
        self.stopped=True

def inventory(engine,client):
    script=getattr(engine.game,"script",None)
    nodes=getattr(script,"all_stmts",None)
    if not nodes:
        return
    if isinstance(nodes,dict):
        nodes=nodes.values()
    for node in nodes:
        name=node.__class__.__name__
        if name=="Say":
            client.enqueue(getattr(node,"what",None))
        elif name=="Menu":
            for item in getattr(node,"items",[]):
                if item:
                    client.enqueue(item[0])

def native_text_class(engine):
    # 4.8.7 and the pre-6.13 text implementations use display.text.
    # Prefer the actual class, not a guessed numerical version.
    native=getattr(getattr(engine,"text",None),"text",None)
    cls=getattr(native,"Text",None)
    if cls is None:
        cls=getattr(getattr(engine.display,"text",None),"Text",None)
    return cls

_installed=False
def install(engine,client=None):
    global _installed
    if _installed:
        return None
    cls=native_text_class(engine)
    if cls is None or not hasattr(cls,"__init__") or not hasattr(cls,"set_text"):
        raise ValueError("IA_RENPY_CLASE_TEXTO_NO_VERIFICADA")
    if client is None:
        client=Client(root_for(engine))
    input_class=getattr(getattr(engine.display,"behavior",None),"Input",None)
    previous_init=cls.__init__
    previous_set=cls.set_text
    def foreground():
        if getattr(engine.game,"init_phase",False):
            return False
        try:
            if getattr(engine.game.context(),"init_phase",False):
                return False
            if getattr(engine,"predicting",lambda:False)():
                return False
        except Exception:
            pass
        return True
    def transform(obj,value,kw):
        if input_class is not None and isinstance(obj,input_class):
            return value
        if getattr(obj,"tokenized",False) or kw.get("tokenized",False):
            return value
        try:
            if visible(value):
                return client.translate(value,foreground())
            # A list of plain strings is supported; token sequences and
            # displayable objects are not reinterpreted as prose.
            if isinstance(value,(list,tuple)):
                for part in value:
                    if as_text(part) is None:
                        return value
                parts=[]
                for part in value:
                    parts.append(client.translate(part,foreground()))
                if isinstance(value,tuple):
                    return tuple(parts)
                return parts
        except Exception:
            pass
        return value
    def initialize(obj,text,*args,**kw):
        # Old Text.__init__ assigns self.text directly, bypassing set_text.
        # Do not touch input values or already tokenized positional data.
        if len(args)>=5 and args[4] is True:
            return previous_init(obj,text,*args,**kw)
        return previous_init(obj,transform(obj,text,kw),*args,**kw)
    def set_text(obj,*args,**kw):
        if args:
            value=transform(obj,args[0],kw)
            return previous_set(obj,value,*args[1:],**kw)
        for name in ("new_text","text"):
            if name in kw:
                kw[name]=transform(obj,kw[name],kw)
                break
        return previous_set(obj,**kw)
    cls.__init__=initialize
    cls.set_text=set_text
    _installed=True
    inventory(engine,client)
    client.start_prefetch()
    if atexit is not None:
        atexit.register(client.close)
    return client
