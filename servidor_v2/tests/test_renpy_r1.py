"""New synthetic regression cases; no game or real neural inference."""
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/"worker"))
from renpy_runtime import protected_parts,translate_surface,RenpyService,handler
spec=importlib.util.spec_from_file_location("renpy_client",BASE/"cmd/servidor/renpy_assets/client.py")
client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
class Neural:
    def __init__(self):self.calls=[]
    def translate(self,lang,text):
        self.calls.append((lang,text))
        return {"She said":"Ella dijo","Hello":"Hola","Continue":"Continuar","Good morning.":"Buenos días.",
                "Choose":"Elige","Open the door":"Abre la puerta","おはよう。":"Buenos días.",
                "Welcome":"Bienvenido","Save":"Guardar"}.get(text,"Texto traducido")
def quality(lang,source,target):return None
class RenpyR1(unittest.TestCase):
    def test_secure_nonce_works_without_uuid(self):
        import re
        from unittest.mock import patch
        with patch.object(client.os, 'urandom', return_value=b'\x01'*16) as random_bytes:
            self.assertEqual(client.new_nonce(), '01'*16)
            random_bytes.assert_called_once_with(16)
        a=client.Client('synthetic-root');b=client.Client('synthetic-root')
        self.assertRegex(a.nonce, r'^[0-9a-f]{32}$')
        self.assertNotEqual(a.nonce,b.nonce)
        self.assertTrue(a.session.endswith('session-'+a.nonce+'.json'))
    def test_quotes_including_end_of_dialogue(self):
        n=Neural()
        self.assertEqual(translate_surface('She said "Hello"',n,quality),'Ella dijo "Hola"')
        self.assertEqual(translate_surface('"Hello"',n,quality),'"Hola"')
        self.assertEqual(translate_surface('「おはよう。」',n,quality),'「Buenos días.」')
    def test_interpolation_nested_and_tags(self):
        source='{b}Welcome [stats["name"]]!{/b}\nChoose %(item)s'
        target=translate_surface(source,Neural(),quality)
        self.assertEqual([x for k,x in protected_parts(source) if k],[x for k,x in protected_parts(target) if k])
        self.assertIn("Bienvenido",target);self.assertIn("Elige",target)
    def test_escaped_literals(self):
        self.assertEqual(translate_surface("Hello [[ {{ %%",Neural(),quality),"Hola [[ {{ %%")
    def test_bad_markup_and_injected_controls(self):
        with self.assertRaises(ValueError):protected_parts("Hello [bad")
        class Bad:
            def translate(self,lang,text):return "{a=evil}Hola{/a}"
        with self.assertRaises(ValueError):translate_surface("Hello",Bad(),quality)
    def test_technical_values(self):
        for s in ("images/hero.png","http://example.org","FLAG_QUEST","123"):
            self.assertEqual(translate_surface(s,Neural(),quality),s)
            self.assertFalse(client.eligible(s))
    def test_persistent_reopen_and_model_identity(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);a=Neural();s=RenpyService(p,"model-a",a,quality)
            self.assertEqual(s.translate("Continue"),"Continuar");s.close()
            n=Neural();s=RenpyService(p,"model-a",n,quality)
            self.assertEqual(s.translate("Continue"),"Continuar");self.assertFalse(n.calls);self.assertEqual(s.cached,1)
            s.close();s=RenpyService(p,"model-b",n,quality)
            self.assertEqual(s.translate("Continue"),"Continuar");self.assertEqual(len(n.calls),1);s.close()
    def test_rejected_not_cached(self):
        with tempfile.TemporaryDirectory() as d:
            s=RenpyService(Path(d),"m",Neural(),lambda *_:"reject")
            self.assertEqual(s.translate("Continue"),"Continue")
            self.assertEqual(s.rejected,1);self.assertIsNone(s.memory.get("Continue"));s.close()
    def test_loopback_authenticated(self):
        with tempfile.TemporaryDirectory() as d:
            s=RenpyService(Path(d),"m",Neural(),quality)
            http=ThreadingHTTPServer(("127.0.0.1",0),handler(s))
            t=threading.Thread(target=http.serve_forever);t.start()
            try:
                for token,status in (("wrong",403),(s.token,200)):
                    c=HTTPConnection("127.0.0.1",http.server_port,timeout=3)
                    c.request("POST","/translate",json.dumps({"text":"Continue"}),{"Authorization":"Bearer "+token})
                    resp=c.getresponse();body=json.loads(resp.read());c.close()
                    self.assertEqual(resp.status,status)
                    if status==200:self.assertEqual(body["text"],"Continuar")
            finally:http.shutdown();t.join();http.server_close();s.close()
    def test_native_hook_keeps_input_and_existing_filter(self):
        from types import SimpleNamespace as NS
        class Text:
            def set_text(self,value,*a,**kw):self.value=value;return "native"
        class Input(Text):pass
        class Fake:
            def __init__(self):self.seen=[];self.outputs=set();self.queue=[]
            def translate(self,value,foreground=True):
                self.seen.append((value,foreground))
                if value in self.outputs:return value
                out={"Hello":"Hola","Continue":"Continuar","Save":"Guardar"}.get(value,value)
                if out!=value:self.outputs.add(out)
                return out
            def enqueue(self,s):self.queue.append(s)
            def start_prefetch(self):pass
            def close(self):pass
        Say=type("Say",(),{});say=Say();say.what="Hello";say.filename="game/script.rpy"
        Menu=type("Menu",(),{});menu=Menu();menu.items=[("Continue",None,[])];menu.filename="game/script.rpy"
        cfg=NS(say_menu_text_filter=lambda value:value)
        e=NS(config=cfg,game=NS(script=NS(all_stmts=[say,menu]),context=lambda:NS(init_phase=False)),
             predicting=lambda:False,text=NS(text=NS(Text=Text)),display=NS(behavior=NS(Input=Input)))
        client._installed=False
        fake=Fake();client.install(e,fake)
        self.assertEqual(fake.queue,["Hello","Continue"])
        self.assertEqual(cfg.say_menu_text_filter("Hello"),"Hola")
        v=Text();self.assertEqual(v.set_text("Hola"),"native");self.assertEqual(v.value,"Hola")
        v.set_text("Save");self.assertEqual(v.value,"Guardar")
        i=Input();i.set_text("Hello");self.assertEqual(i.value,"Hello")
        e.predicting=lambda:True
        v.set_text("Continue");self.assertIn(("Continue",False),fake.seen)
class ClassicRenpyR1(unittest.TestCase):
    def classic(self):
        s=importlib.util.spec_from_file_location("classic_client",BASE/"cmd/servidor/renpy_assets/classic_client.py")
        m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
    def test_old_native_constructor_and_setter(self):
        from types import SimpleNamespace as NS
        m=self.classic()
        class Text:
            def __init__(self,text,*args,**kw):self.text=text
            def set_text(self,new_text):self.text=new_text
        class Input(Text):pass
        class Fake:
            def __init__(self):self.seen=[]
            def enqueue(self,s):self.seen.append(s)
            def translate(self,s,foreground=True):
                return {"Hello":"Hola","Continue":"Continuar","Save":"Guardar"}.get(s,s)
            def start_prefetch(self):pass
            def close(self):pass
        Say=type("Say",(),{});say=Say();say.what="Hello"
        Menu=type("Menu",(),{});menu=Menu();menu.items=[("Continue",True,[])]
        e=NS(game=NS(script=NS(all_stmts=[say,menu]),init_phase=False,context=lambda:NS(init_phase=False)),
             display=NS(text=NS(Text=Text),behavior=NS(Input=Input)))
        f=Fake();m.install(e,f)
        self.assertEqual(f.seen,["Hello","Continue"])
        self.assertEqual(Text("Hello").text,"Hola")
        t=Text("Continue");self.assertEqual(t.text,"Continuar")
        t.set_text(new_text="Save");self.assertEqual(t.text,"Guardar")
        self.assertEqual(Input("Hello").text,"Hello")
        self.assertEqual(Text("Hello",tokenized=True).text,"Hello")
    def test_classic_client_and_worker_exchange_real_files(self):
        import os
        from renpy_classic_bridge import ClassicBridge
        from renpy_runtime import ordinary
        m=self.classic()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);side=root/"IA Traductora RenPy";side.mkdir()
            nonce="ab"*16
            (side/"classic-key.txt").write_bytes(nonce.encode("ascii"))
            folder=side/("classic-session-"+nonce)
            service=RenpyService(side,"model",Neural(),quality)
            workers=[]
            def start(exe,game,key):
                self.assertEqual(key,nonce);self.assertEqual(Path(game),root)
                folder.mkdir()
                bridge=ClassicBridge(folder,service,nonce,os.getpid(),ordinary)
                thread=threading.Thread(target=bridge.serve);workers.append((bridge,thread))
                thread.start()
                return 1
            m.launch_worker=start
            c=m.Client(str(root))
            try:
                self.assertEqual(c.translate('She said "Hello"'),'Ella dijo "Hola"')
                self.assertEqual(c.translate('「おはよう。」'),'「Buenos días.」')
                self.assertEqual(c.translate('She said "Hello"'),'Ella dijo "Hola"')
                self.assertEqual(service.translated,2)
                self.assertEqual(c.sequence,2)
            finally:
                c.close()
                for bridge,thread in workers:
                    bridge.shutdown();thread.join(5)
                    self.assertFalse(thread.is_alive())
                    bridge.cleanup()
                service.close()

    def test_classic_authenticated_file_transport(self):
        from renpy_classic_bridge import ClassicBridge
        from renpy_runtime import ordinary
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/"session";folder.mkdir()
            s=RenpyService(root,"model",Neural(),quality)
            bridge=ClassicBridge(folder,s,"0"*32,1,ordinary)
            try:
                req=folder/"request-00000001.txt"
                req.write_bytes(b"bad\n00000001\nHello")
                bridge.step();self.assertFalse((folder/"response-00000001.txt").exists())
                prefix=(s.token+"\n00000001\n").encode("ascii")
                req.write_bytes(prefix+b"Hello")
                bridge.step()
                self.assertEqual((folder/"response-00000001.txt").read_bytes(),prefix+b"Hola")
                self.assertFalse(req.exists())
            finally:s.close();bridge.cleanup()

if __name__=="__main__":unittest.main()
