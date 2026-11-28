"""File transport for old Ren'Py interpreters. No code evaluation or network."""
import os
import re
import secrets
import threading

REQUEST=re.compile(r"request-(\d{8})\.txt\Z")
OWNED=re.compile(r"(?:ready\.txt|(?:request|response)-\d{8}\.txt(?:\.tmp)?|\.ia-write-[0-9a-f]{32})\Z")
SCHEMA="ia-renpy-classic-v1"
MAX_REQUEST=140000
MAX_TEXT=32768

def publish(path,raw):
    if path.exists() or path.is_symlink():
        raise ValueError("IA_RENPY_RESPUESTA_EXISTENTE")
    temp=path.parent/(".ia-write-"+secrets.token_hex(16))
    try:
        with temp.open("xb") as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        # Session directory belongs to this worker; os.link provides
        # exclusive publication without replacing an existing request.
        os.link(temp,path)
    finally:
        temp.unlink(missing_ok=True)

class ClassicBridge:
    def __init__(self,session,service,nonce,parent,ordinary):
        self.session=session;self.service=service;self.nonce=nonce;self.parent=parent
        self.ordinary=ordinary;self.token=service.token;self.stop=threading.Event()
    def shutdown(self):
        self.stop.set()
    def serve(self):
        ready="\n".join((SCHEMA,self.nonce,str(self.parent),self.token))
        publish(self.session/"ready.txt",ready.encode("ascii"))
        while not self.stop.is_set():
            self.step()
            self.stop.wait(.05)
    def step(self):
        if not self.ordinary(self.session,True):
            raise ValueError("IA_RENPY_SESION_INVALIDA")
        for path in sorted(self.session.iterdir()):
            match=REQUEST.fullmatch(path.name)
            if match is None or not self.ordinary(path):continue
            if path.stat().st_size>MAX_REQUEST:continue
            seq=match.group(1)
            prefix=(self.token+"\n"+seq+"\n").encode("ascii")
            try:
                raw=path.read_bytes()
                if len(raw)>MAX_REQUEST or not secrets.compare_digest(raw[:len(prefix)],prefix):
                    continue
                source=raw[len(prefix):].decode("utf-8")
                if not 0<len(source)<=MAX_TEXT:continue
                response=self.session/("response-"+seq+".txt")
                if response.exists() or response.is_symlink():continue
                target=self.service.translate(source)
                publish(response,prefix+target.encode("utf-8"))
                # Remove only the authenticated request consumed here.
                path.unlink()
            except (OSError,UnicodeError,ValueError):
                continue
    def cleanup(self):
        # Preserve foreign entries rather than deleting arbitrary paths.
        for p in self.session.iterdir():
            if OWNED.fullmatch(p.name) and self.ordinary(p):
                p.unlink(missing_ok=True)
        self.session.rmdir()

def run_classic(side,identity,nonce,parent,neural_factory,engine,quality,monitor,service_type,ordinary,atomic_json):
    folder=side/("classic-session-"+nonce)
    marker=side/("session-"+nonce+".json")
    if marker.exists() or marker.is_symlink():
        raise ValueError("IA_RENPY_SESION_EXISTENTE")
    # mkdir is the exclusive guard. Never attach to another session.
    folder.mkdir(mode=0o700)
    service=None;bridge=None
    try:
        service=service_type(side,identity,neural_factory(engine),quality)
        bridge=ClassicBridge(folder,service,nonce,parent,ordinary)
        monitor(bridge,parent)
        atomic_json(marker,{"schema":SCHEMA,"nonce":nonce,"parent":parent})
        bridge.serve()
    finally:
        if service is not None:service.close()
        if bridge is not None:bridge.cleanup()
        else:folder.rmdir()
        if marker.exists() and ordinary(marker):marker.unlink()
