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
if __name__=="__main__":unittest.main()
