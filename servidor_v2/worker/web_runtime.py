"""Independent, explicit host for a user's extracted standalone web frontend.

Only public game assets are served. The original executable and extracted
assets are not modified; no native Wails APIs are impersonated except the
optional local Quit action. This is not an EXE unpacker or a general Wails ABI.
"""
import html.parser
import json
import mimetypes
import re
import stat
import threading
from pathlib import Path
from urllib.parse import unquote, urlsplit
from http.server import ThreadingHTTPServer

MAX_INDEX=1024*1024
MAX_MODULE=16*1024*1024
MAX_ASSET=2*1024*1024*1024
MAX_CATALOG=20000
EXTENSIONS={".js",".mjs",".css",".json",".wasm",".txt",".png",".jpg",".jpeg",
            ".webp",".gif",".bmp",".svg",".ico",".mp3",".wav",".ogg",".m4a",
            ".aac",".mp4",".webm",".ogv",".ttf",".otf",".woff",".woff2"}
CONTENT_TYPES={".js":"text/javascript; charset=utf-8",".mjs":"text/javascript; charset=utf-8",
               ".css":"text/css; charset=utf-8",".json":"application/json; charset=utf-8",
               ".wasm":"application/wasm",".ttf":"font/ttf",".woff":"font/woff",
               ".woff2":"font/woff2"}
CSP=("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
     "img-src 'self' data: blob:; media-src 'self' data: blob:; "
     "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
     "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")

def ordinary(path,kind):
    info=path.lstat()
    return (not stat.S_ISLNK(info.st_mode) and not (getattr(info,"st_file_attributes",0)&0x400)
            and (stat.S_ISDIR(info.st_mode) if kind=="dir" else stat.S_ISREG(info.st_mode)))

def checked_root(folder):
    root=Path(folder).absolute()
    for part in (root,*root.parents):
        if not ordinary(part,"dir"):raise ValueError("IA_WEB_RUTA_INVALIDA")
    return root.resolve(strict=True)

def read_bounded(path,limit):
    if not ordinary(path,"file") or not 0<path.stat().st_size<=limit:
        raise ValueError("IA_WEB_RECURSOS_INCOMPLETOS")
    with path.open("rb") as f:
        raw=f.read(limit+1)
    if len(raw)>limit:raise ValueError("IA_WEB_RECURSOS_INCOMPLETOS")
    return raw

def asset_path(root,relative):
    if not relative.startswith("assets/") or "\\" in relative or ":" in relative:
        raise ValueError("IA_WEB_RUTA_INVALIDA")
    pieces=relative.split("/")
    if any(not p or p in (".","..") or p.endswith(("."," ")) or
           any(ord(c)<32 or ord(c)==127 for c in p) for p in pieces):
        raise ValueError("IA_WEB_RUTA_INVALIDA")
    file=root
    for i,piece in enumerate(pieces):
        file=file/piece
        if not ordinary(file,"file" if i==len(pieces)-1 else "dir"):
            raise ValueError("IA_WEB_RUTA_INVALIDA")
    if not file.resolve(strict=True).is_relative_to(root) or file.suffix.lower() not in EXTENSIONS:
        raise ValueError("IA_WEB_RUTA_INVALIDA")
    if file.stat().st_size>MAX_ASSET:
        raise ValueError("IA_WEB_RECURSOS_INCOMPLETOS")
    return file

class IndexParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.modules=[]
        self.bad=False
    def handle_starttag(self,tag,attrs):
        if tag=="base":
            self.bad=True
        if tag!="script":return
        a=dict(attrs)
        src=a.get("src")
        if not src:
            self.bad=True
            return
        parsed=urlsplit(src)
        path=parsed.path.removeprefix("/")
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or src.startswith("//"):
            self.bad=True
        elif not re.fullmatch(r"assets/[A-Za-z0-9_./-]+\.m?js",path):
            self.bad=True
        else:self.modules.append(path)

def web_profile(folder):
    try:
        root=checked_root(folder)
        if not ordinary(root/"assets","dir"):
            raise ValueError("IA_WEB_RECURSOS_INCOMPLETOS")
        index=read_bounded(root/"index.html",MAX_INDEX).decode("utf-8-sig")
        parser=IndexParser()
        parser.feed(index)
        parser.close()
        if parser.bad or not 1<=len(parser.modules)<=8 or not re.search(r"<head\b[^>]*>",index,re.I):
            raise ValueError("IA_WEB_MODULO_NO_ADMITIDO")
        modules=[]
        for relative in dict.fromkeys(parser.modules):
            file=asset_path(root,relative)
            if not 0<file.stat().st_size<=MAX_MODULE:
                raise ValueError("IA_WEB_RECURSOS_INCOMPLETOS")
            modules.append(file)
        return root,index,modules
    except OSError as exc:
        raise ValueError("IA_WEB_RECURSOS_INCOMPLETOS") from exc
    except UnicodeError as exc:
        raise ValueError("IA_WEB_INDEX_INVALIDO") from exc

# Narrow, non-evaluating profile: only explicit three-language dialogue
# records adjacent to an audio field. Unknown JS structures stay runtime-only.
# No original code, file paths, names, expressions or assets are sent to OPUS.
JS_STRING=r'"(?:\\[^\r\n]|[^"\\\r\n])*"'
RECORD=re.compile(r"\bzh\s*:\s*("+JS_STRING+r")\s*,\s*jp\s*:\s*("+JS_STRING+
                  r")\s*,\s*en\s*:\s*("+JS_STRING+r")\s*,\s*audio\s*:")
def js_string(raw):
    # JS hex escapes need conversion before a strict JSON string decode.
    raw=re.sub(r"\\(?:x([0-9a-fA-F]{2})|[^\r\n])",
               lambda m:"\\u00"+m.group(1) if m.group(1) else m.group(0),raw)
    try:
        value=json.loads(raw).strip()
        value.encode("utf8")
        return value
    except (ValueError,UnicodeError):
        return ""
def catalog(modules):
    records=0
    unique={}
    limited=False
    for file in modules:
        raw=read_bounded(file,MAX_MODULE).decode("utf8",errors="replace")
        for match in RECORD.finditer(raw):
            records+=1
            en,ja=js_string(match[3]),js_string(match[2])
            lang,text=("en",en) if re.search(r"[A-Za-z]",en) else ("ja",ja)
            if not 2<=len(text)<=1800 or "\x00" in text or re.match(r"(?i)^(?:https?:|file:|data:)",text):
                continue
            if lang=="ja" and not re.search(r"[\u3040-\u30ff\u3400-\u9fff]",text):
                continue
            if len(unique)>=MAX_CATALOG and (lang,text) not in unique:
                limited=True
                continue
            unique[(lang,text)]=None
    return {"schema":"ia-web-catalog-v1","records":records,"limited":limited,
            "items":[{"source":lang,"text":text} for lang,text in unique]}

WEB_ADAPTER=r"""
(function(){
"use strict";
const token=__IA_WEB_TOKEN__;
const fixed=Object.freeze({"Home":"Inicio","Next":"Siguiente","Prev":"Anterior",
"Previous":"Anterior","Save":"Guardar","Load":"Cargar","Settings":"Ajustes",
"Start":"Comenzar","New Game":"Nueva partida","Continue":"Continuar",
"Quit":"Salir","Exit":"Salir","Back":"Volver","Cancel":"Cancelar",
"Yes":"Sí","No":"No","Close":"Cerrar","Language":"Idioma","Volume":"Volumen",
"English":"Inglés","Japanese":"Japonés","Chinese":"Chino","Gallery":"Galería"});
const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
const block="script,style,noscript,textarea,input,select,option,[contenteditable]:not([contenteditable='false']),[aria-hidden='true'],[data-ia-web],[data-ia-skip],.speaker-name,.character-name";
const cache=new Map(),pending=new Map(),known=new Map(),outputs=new Set(),rejected=new Set(),applied=new WeakMap();
let warm=[],warmAt=0,records=0,limited=false,busy=false,active=true,ready=0,failed=0,shown=0;
let scanTimer=null,scanBusy=false,dirty=false,pumpTimer=null,badge=null,panel=null,status=null;
const headers={"X-IA-Token":token,"Content-Type":"application/json"};
const key=(lang,text)=>lang+"\u0000"+text;
function boundedSet(set,value){set.add(value);if(set.size>12000)set.delete(set.values().next().value);}
function refresh(){
 if(status)status.textContent="OPUS local · "+ready+" listos · "+shown+" mostrados\n"+
 "Inventario previo: "+warmAt+"/"+warm.length+" ("+records+" registros)"+(limited?" · limitado":"")+
 "\nFallos: "+failed+(active?"":" · sesión detenida");
}
function visible(node){
 const p=node.parentElement;
 if(!p||!node.isConnected||p.closest(block)||!p.getClientRects().length)return false;
 return getComputedStyle(p).visibility!=="hidden";
}
function sourceFor(text,node){
 if(known.has(text))return known.get(text);
 if(/[\u3040-\u30ff]/.test(text))return "ja";
 // Chinese-only strings are not passed to the Japanese model. Select
 // English in the original language menu for full pre-inventory coverage.
 if(/[^\x20-\x7e\u2018\u2019\u201c\u201d\u2026\u2013\u2014]/.test(text))return null;
 if(/^(?:https?:|file:|data:|www\.)|[\\/]|[{}=<>]|\.[a-z0-9]{2,4}$/i.test(text))return null;
 const words=text.match(/[A-Za-z]+/g)||[];
 if(words.length<2||words.length>160)return null;
 if(node.parentElement.closest("button,a,label,h1,h2,h3,[role='button']"))return "en";
 return /\b(?:i|you|we|he|she|they|the|a|an|is|are|was|were|to|of|and|or|for|with|my|your|this|that|please|have|has|go|do|don't|will|can|could|from|here|there)\b/i.test(text)?"en":null;
}
function apply(node,raw,value){
 if(!active||typeof value!=="string"||!value.trim()||!visible(node)||node.data!==raw)return;
 const core=raw.trim();
 if(value===core)return;
 const shownText=raw.slice(0,raw.indexOf(core))+value+raw.slice(raw.indexOf(core)+core.length);
 applied.set(node,{raw,shown:shownText});
 boundedSet(outputs,value);
 node.data=shownText;
 shown++;refresh();
}
function remember(k,value){
 cache.set(k,value);
 if(cache.size>12000)cache.delete(cache.keys().next().value);
 boundedSet(outputs,value);
 ready++;
}
function visit(node){
 if(!active||!visible(node))return;
 const raw=node.data,previous=applied.get(node);
 if(previous&&previous.shown===raw)return;
 const text=raw.trim();
 if(text.length<2||text.length>1800||outputs.has(text))return;
 if(own(fixed,text)){apply(node,raw,fixed[text]);return;}
 const lang=sourceFor(text,node);if(!lang)return;
 const k=key(lang,text);
 if(cache.has(k)){apply(node,raw,cache.get(k));return;}
 if(rejected.has(k))return;
 let item=pending.get(k);
 if(!item){
  if(pending.size>=512)return;
  item={lang,text,waiters:new Map()};pending.set(k,item);
 }
 if(item.waiters.size<64)item.waiters.set(node,raw);
}
function scheduleScan(){
 if(!active)return;
 if(scanBusy){dirty=true;return;}
 if(scanTimer!==null)return;
 scanTimer=setTimeout(function(){
  scanTimer=null;if(!document.body||!active)return;
  scanBusy=true;dirty=false;
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  function slice(){
   let n,count=0;
   while(count++<200&&(n=walker.nextNode()))visit(n);
   if(n){setTimeout(slice,0);return;}
   scanBusy=false;schedulePump(0);
   if(dirty)scheduleScan();
  }
  slice();
 },35);
}
function schedulePump(ms){
 if(!active||busy||pumpTimer!==null)return;
 pumpTimer=setTimeout(function(){pumpTimer=null;pump();},ms);
}
async function pump(){
 if(!active||busy)return;
 let item=null,k=null;
 while(pending.size){
  const first=pending.entries().next().value;
  k=first[0];item=first[1];pending.delete(k);
  if(cache.has(k)){
   item.waiters.forEach((raw,node)=>apply(node,raw,cache.get(k)));item=null;continue;
  }
  if(rejected.has(k)){item=null;continue;}
  break;
 }
 while(!item&&warmAt<warm.length){
  const entry=warm[warmAt++];k=key(entry.source,entry.text);
  if(cache.has(k)||rejected.has(k))continue;
  item={lang:entry.source,text:entry.text,waiters:new Map()};
 }
 if(!item){refresh();return;}
 busy=true;
 const controller=new AbortController();
 const timeout=setTimeout(()=>controller.abort(),45000);
 try{
  const response=await fetch("/__ia/translate",{method:"POST",headers,signal:controller.signal,
   body:JSON.stringify({source:item.lang,target:"es",text:item.text})});
  if(!response.ok)throw Error("translation");
  const result=await response.json();
  if(typeof result.translated!=="string"||!result.translated.trim()||result.translated===item.text)throw Error("invalid");
  remember(k,result.translated);
  item.waiters.forEach((raw,node)=>apply(node,raw,result.translated));
 }catch(_){boundedSet(rejected,k);failed++;}
 finally{
  clearTimeout(timeout);busy=false;refresh();
  // Visible work always wins over the next background request.
  scheduleScan();
  schedulePump(pending.size?20:500);
 }
}
async function stop(){
 if(!active)return;
 active=false;
 try{await fetch("/__ia/stop",{method:"POST",headers});}catch(_){}
 refresh();
 if(status)status.textContent+="\nPuedes cerrar esta pestaña.";
}
function start(){
 document.documentElement.setAttribute("translate","no");
 const box=document.createElement("div");box.dataset.iaWeb="1";
 box.style.cssText="position:fixed;top:8px;right:8px;z-index:2147483647;font:14px/1.4 system-ui,sans-serif;color:white;text-align:left;";
 badge=document.createElement("button");badge.id="ia-web-toggle";badge.textContent="◆ IA Traductora · F10";
 badge.style.cssText="background:#141923;color:white;border:1px solid #a99159;border-radius:5px;padding:7px 11px;cursor:pointer;font:inherit;";
 panel=document.createElement("div");panel.id="ia-web-panel";panel.hidden=true;
 panel.style.cssText="background:#141923;color:white;border:1px solid #a99159;padding:10px;margin-top:4px;white-space:pre-wrap;max-width:320px;";
 status=document.createElement("div");panel.appendChild(status);
 const exit=document.createElement("button");exit.textContent="Detener IA";exit.addEventListener("click",stop);panel.appendChild(exit);
 const toggle=()=>{panel.hidden=!panel.hidden;refresh();};
 badge.addEventListener("click",toggle);box.append(badge,panel);document.body.appendChild(box);
 window.addEventListener("keydown",e=>{
  if(e.key==="F10"&&!e.ctrlKey&&!e.altKey&&!e.shiftKey&&!e.metaKey&&!e.repeat&&
     !(e.target&&e.target.closest&&e.target.closest("input,textarea,[contenteditable]"))){
   e.preventDefault();toggle();
  }
 },true);
 // No other Wails APIs are manufactured. A standalone Quit can only
 // terminate this local session; it never closes or kills another program.
 if(typeof window.runtime==="undefined")window.runtime={Quit:stop};
 new MutationObserver(mutations=>{
  if(mutations.some(m=>!(m.target.parentElement&&m.target.parentElement.closest("[data-ia-web]"))&&
      !(m.type==="characterData"&&applied.get(m.target)&&applied.get(m.target).shown===m.target.data)))scheduleScan();
 }).observe(document.body,{childList:true,characterData:true,subtree:true});
 scheduleScan();refresh();
 fetch("/__ia/catalog",{headers}).then(r=>{
  if(!r.ok)throw Error("catalog");return r.json();
 }).then(data=>{
  if(data.schema!=="ia-web-catalog-v1"||!Array.isArray(data.items))return;
  warm=data.items;records=data.records;limited=data.limited;
  warm.forEach(entry=>known.set(entry.text,entry.source));scheduleScan();schedulePump(0);refresh();
 }).catch(()=>{limited=true;refresh();});
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});else start();
})();
"""

def make_web_handler(service,base_factory):
    root,index,modules=web_profile(service.content)
    inventory=catalog(modules)
    # Inject only in the served response; never write the user's HTML.
    head=re.search(r"<head\b[^>]*>",index,re.I)
    insertion='<meta name="google" content="notranslate"><script src="/__ia/adapter.js"></script>'
    page=(index[:head.end()]+insertion+index[head.end():]).encode("utf8")
    script=WEB_ADAPTER.replace("__IA_WEB_TOKEN__",json.dumps(service.token)).encode("utf8")
    Base=base_factory(service)
    class Handler(Base):
        timeout=10
        def scoped(self,post=False):
            host="127.0.0.1:"+str(self.server.server_port)
            origin=self.headers.get("Origin")
            return (self.headers.get("Host")==host and self.headers.get("Sec-Fetch-Site")!="cross-site"
                    and (origin=="http://"+host if post else origin in (None,"http://"+host)))
        def end_headers(self):
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Cross-Origin-Resource-Policy","same-origin")
            self.send_header("Content-Security-Policy",CSP)
            self.send_header("X-Frame-Options","DENY")
            super().end_headers()
        def bytes_response(self,body,mime,head=False):
            self.send_response(200)
            self.send_header("Content-Type",mime)
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            if not head:self.wfile.write(body)
        def static_file(self,file,head=False):
            with file.open("rb") as f:
                size=file.stat().st_size
                start,end,code=0,size-1,200
                requested=self.headers.get("Range")
                if requested:
                    m=re.fullmatch(r"bytes=(\d{0,20})-(\d{0,20})",requested)
                    if m and (m[1] or m[2]):
                        if m[1]:
                            start=int(m[1]);end=min(end,int(m[2])) if m[2] else end
                        else:start=max(0,size-int(m[2]))
                    if not m or not(m[1] or m[2]) or start>end or start>=size:
                        self.send_response(416);self.send_header("Content-Range","bytes */"+str(size))
                        self.send_header("Content-Length","0");self.end_headers();return
                    code=206
                length=max(0,end-start+1)
                mime=CONTENT_TYPES.get(file.suffix.lower()) or mimetypes.guess_type(str(file))[0] or "application/octet-stream"
                self.send_response(code);self.send_header("Content-Type",mime)
                self.send_header("Accept-Ranges","bytes");self.send_header("Content-Length",str(length))
                self.send_header("Cache-Control","no-store")
                if code==206:self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
                self.end_headers()
                if head:return
                f.seek(start)
                while length:
                    block=f.read(min(256*1024,length))
                    if not block:break
                    self.wfile.write(block);length-=len(block)
        def do_GET(self,head=False):
            if not self.scoped():return self.send(403,{"error":"IA_WEB_ORIGEN_INVALIDO"})
            try:
                parsed=urlsplit(self.path)
                route=unquote(parsed.path,errors="strict")
                if parsed.scheme or parsed.netloc or self.path.startswith("//"):
                    raise ValueError()
                if route in ("/","/index.html"):
                    return self.bytes_response(page,"text/html; charset=utf-8",head)
                if route=="/__ia/adapter.js":
                    return self.bytes_response(script,"text/javascript; charset=utf-8",head)
                if not head and route in ("/__ia/catalog","/__ia/status"):
                    if not self.allowed():return self.send(403,{"error":"IA_TOKEN_INVALIDO"})
                    if route.endswith("/catalog"):return self.send(200,inventory)
                    self.path="/status";return super().do_GET()
                if route.startswith("/assets/"):
                    return self.static_file(asset_path(root,route[1:]),head)
            except (OSError,ValueError,UnicodeError):
                pass
            return self.send(404,{"error":"IA_WEB_RUTA_NO_ADMITIDA"})
        def do_HEAD(self):return self.do_GET(head=True)
        def do_POST(self):
            if not self.scoped(post=True) or not self.allowed():
                return self.send(403,{"error":"IA_WEB_ORIGEN_O_TOKEN_INVALIDO"})
            if self.path=="/__ia/stop":
                self.send(200,{"stopping":True})
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if self.path not in ("/__ia/translate","/__ia/translate_batch"):
                return self.send(404,{"error":"IA_WEB_RUTA_NO_ADMITIDA"})
            self.path=self.path.removeprefix("/__ia")
            return super().do_POST()
    return Handler

def run_web(service,port,no_browser,parent_pid,diagnostic_file,base_factory,monitor_lifetime,write_code):
    server=None
    try:
        try:server=ThreadingHTTPServer(("127.0.0.1",port),make_web_handler(service,base_factory))
        except OSError as exc:raise ValueError("IA_WEB_PUERTO_OCUPADO") from exc
        server.daemon_threads=False
        server.block_on_close=True
        monitor_lifetime(server,parent_pid)
        write_code(diagnostic_file,"IA_WEB_LISTO")
        if not no_browser:
            import webbrowser
            webbrowser.open("http://127.0.0.1:"+str(port)+"/#/")
        server.serve_forever(poll_interval=0.25)
    finally:
        try:
            if server is not None:server.server_close()
        finally:service.close()
    write_code(diagnostic_file,"IA_WEB_CERRADO")
