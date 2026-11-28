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
    def test_long_visible_text_is_not_truncated(self):
        from renpy_runtime import MODEL_CHUNK,model_chunks
        original=("Hello world. "*220)+"[player_name]\n{b}Continue{/b}"
        class EchoSpanish:
            def __init__(self):self.calls=[]
            def translate(self,lang,source):
                self.calls.append(source)
                return source.replace("Hello world.","Hola mundo.").replace("Continue","Continuar")
        n=EchoSpanish()
        result=translate_surface(original,n,quality)
        self.assertEqual(result.count("Hola mundo."),220)
        self.assertIn("[player_name]\n{b}Continuar{/b}",result)
        self.assertTrue(all(len(x)<=MODEL_CHUNK for x in n.calls))
        self.assertEqual("".join(model_chunks(original)),original)
        self.assertTrue(client.eligible(original))
    def test_code_and_ruby_controls(self):
        n=Neural()
        for s in ("score = 12","player.hp += 3","jump chapter_2","renpy.quit()","$ score = 2"):
            self.assertEqual(translate_surface(s,n,quality),s)
        self.assertFalse(n.calls)
        source="Hello 〖東京｜とうきょう〗 [player] {image=star.png}"
        self.assertEqual(translate_surface(source,n,quality),"Hola 〖東京｜とうきょう〗 [player] {image=star.png}")
    def test_persistent_reopen_and_model_identity(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);a=Neural();s=RenpyService(p,"model-a",a,quality)
            self.assertEqual(s.translate("Continue"),"Continuar");s.close()
            n=Neural();s=RenpyService(p,"model-a",n,quality)
            self.assertEqual(s.translate("Continue"),"Continuar");self.assertFalse(n.calls);self.assertEqual(s.cached,1)
            s.close();s=RenpyService(p,"model-b",n,quality)
            self.assertEqual(s.translate("Continue"),"Continuar");self.assertEqual(len(n.calls),1);s.close()
    def test_model_identity_survives_worker_rebuild_and_migrates_verified_memory(self):
        from renpy_runtime import model_memory_identity,legacy_memory_identity
        old={"IATraductora.exe":"a"*64,"models/opus_en_es/model.bin":"b"*64,"models/opus_ja_es/model.bin":"c"*64}
        new=dict(old);new["IATraductora.exe"]="d"*64
        changed=dict(new);changed["models/opus_ja_es/model.bin"]="e"*64
        self.assertEqual(model_memory_identity(old),model_memory_identity(new))
        self.assertNotEqual(legacy_memory_identity(old),legacy_memory_identity(new))
        self.assertNotEqual(model_memory_identity(old),model_memory_identity(changed))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);n=Neural()
            s=RenpyService(p,legacy_memory_identity(old),n,quality)
            self.assertEqual(s.translate("Continue"),"Continuar");s.close()
            n=Neural();s=RenpyService(p,model_memory_identity(new),n,quality,[legacy_memory_identity(old)])
            self.assertEqual(s.translate("Continue"),"Continuar")
            self.assertEqual(s.cached,1);self.assertEqual(n.calls,[])
            self.assertEqual(s.memory.get("Continue"),"Continuar");s.close()
            n=Neural();s=RenpyService(p,model_memory_identity(changed),n,quality)
            self.assertEqual(s.translate("Continue"),"Continuar")
            self.assertEqual(len(n.calls),1);s.close()
    def test_rejected_not_cached(self):
        with tempfile.TemporaryDirectory() as d:
            s=RenpyService(Path(d),"m",Neural(),lambda *_:"reject")
            self.assertEqual(s.translate("Continue"),"Continue")
            self.assertEqual(s.rejected,1);self.assertIsNone(s.memory.get("Continue"));s.close()
    def test_status_write_failure_does_not_break_translation(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            s=RenpyService(Path(d),"m",Neural(),quality)
            try:
                with patch("renpy_runtime.atomic_json",side_effect=PermissionError("temporary sharing violation")):
                    self.assertEqual(s.translate("Continue"),"Continuar")
                    self.assertEqual(s.status()["translated"],1)
                s.publish_status(force=True)
                self.assertEqual(json.loads((Path(d)/"status.json").read_text("utf-8"))["translated"],1)
            finally:s.close()
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
    def test_live_cache_misses_never_call_network(self):
        import time
        from unittest.mock import patch
        c=client.Client("synthetic")
        with patch.object(c,"request",side_effect=AssertionError("UI attempted I/O")) as request:
            before=time.perf_counter()
            for i in range(1000):
                self.assertEqual(c.translate("Unique dialogue %d."%i),"Unique dialogue %d."%i)
            self.assertLess(time.perf_counter()-before,1.0)
            request.assert_not_called()
        self.assertEqual(c.snapshot()["pending"],1000)
        c.remember("Unique dialogue 0.","Dialogo traducido.")
        self.assertEqual(c.translate("Unique dialogue 0."),"Dialogo traducido.")
        c.remember("No change.","No change.")
        c.translate("No change.")
        self.assertNotIn("No change.",c.queued)
    def test_background_consumer_lifecycle_and_cache_miss_stays_nonblocking(self):
        import time
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/client.SIDECAR).mkdir()
            c=client.Client(d)
            caller=threading.current_thread()
            entered=threading.Event()
            release=threading.Event()
            calls=[]
            def delayed_request(value,deadline):
                calls.append((value,threading.current_thread()))
                entered.set()
                if not release.wait(4):
                    raise RuntimeError("test transport not released")
                return "Dialogo listo."
            try:
                with patch.object(c,"get_session",return_value={"ready":True}),patch.object(c,"request",side_effect=delayed_request):
                    source="Cold dialogue."
                    c.enqueue(source)
                    c.finish_inventory(True)
                    self.assertEqual(c.translate(source),source)
                    self.assertEqual(c.snapshot()["pending"],1)
                    self.assertEqual(calls,[])
                    c.start_prefetch()
                    self.assertTrue(entered.wait(3),"Background consumer never started")
                    before=time.perf_counter()
                    self.assertEqual(c.translate(source),source)
                    self.assertLess(time.perf_counter()-before,.25)
                    self.assertIsNot(calls[0][1],caller)
                    release.set()
                    until=time.monotonic()+3
                    while c.snapshot()["pending"] and time.monotonic()<until:
                        time.sleep(.02)
                    self.assertEqual(c.snapshot()["pending"],0)
                    self.assertEqual(c.translate(source),"Dialogo listo.")
                    self.assertEqual(len(calls),1)
            finally:
                release.set()
                c.close()
                if c.thread is not None:c.thread.join(3)
                if c.progress_thread is not None:c.progress_thread.join(3)
    def test_visible_priority_and_no_duplicate_queue(self):
        c=client.Client("synthetic")
        c.enqueue("Inventory one.")
        c.enqueue("Inventory two.")
        c.finish_inventory(True)
        c.translate("Inventory two.",True)
        c.translate("Inventory two.",True)
        self.assertEqual(list(c.urgent),["Inventory two."])
        self.assertEqual(list(c.pending),["Inventory one."])
        self.assertEqual(c.snapshot()["inventory"],2)
        self.assertEqual(c.snapshot()["discovered"],2)
    def test_prepared_fast_start_checks_model_and_protected_controls(self):
        with tempfile.TemporaryDirectory() as d:
            side=Path(d)/client.SIDECAR;side.mkdir()
            receipt={"schema":client.SCHEMA,"engine_sha256":{"models/opus_en_es/model.bin":"a"*64,"models/opus_ja_es/model.bin":"b"*64}}
            (side/"owner-v1.json").write_text(json.dumps(receipt),encoding="utf-8")
            c=client.Client(d)
            c.remember('{b}Save [player]{/b}','{b}Guardar [player]{/b}')
            c.remember("Continue","Continuar")
            c.remember("Danger","Peligro [malicious()]")
            self.assertEqual(c.save_prepared(),2)
            next_client=client.Client(d);next_client.load_prepared()
            self.assertEqual(next_client.preloaded,2)
            next_client.enqueue("Continue");next_client.finish_inventory(True)
            self.assertEqual(next_client.snapshot()["inventory"],1)
            self.assertEqual(next_client.snapshot()["accepted"],1)
            self.assertEqual(next_client.translate('{b}Save [player]{/b}'),'{b}Guardar [player]{/b}')
            self.assertNotIn("Danger",next_client.cache)
            receipt["engine_sha256"]["models/opus_en_es/model.bin"]="c"*64
            (side/"owner-v1.json").write_text(json.dumps(receipt),encoding="utf-8")
            incompatible=client.Client(d);incompatible.load_prepared()
            self.assertEqual(incompatible.preloaded,0)
    def test_preplay_inventory_compiled_screen_and_python_literals(self):
        from types import SimpleNamespace as NS
        def make(kind,**attrs):
            obj=type(kind,(),{})()
            for key,value in attrs.items():setattr(obj,key,value)
            return obj
        def Text():pass
        def _textbutton():pass
        screen=make("SLScreen",children=[
            make("SLDisplayable",displayable=Text,positional=['"Inventory is empty."'],keyword=[],children=[]),
            make("SLIf",entries=[("flag",make("SLBlock",children=[make("SLDisplayable",displayable=_textbutton,positional=['"Open settings"'],keyword=[("action",'Jump("chapter_secret")')],children=[])]))])])
        nodes=[make("Screen",filename="game/screens.rpy",screen=screen),
               make("Python",filename="game/scene.rpy",code=NS(source='renpy.notify("Quest completed.")\nrenpy.input("Your name?", default="PRIVATE_INPUT")\npath="images/hidden.png"\nrenpy.jump("chapter_secret")')),
               make("Define",filename="game/scene.rpy",code=NS(source='Character("Visible name")'))]
        report={}
        eng=NS(game=NS(script=NS(all_stmts=nodes,namemap={},translator=None)),loader=NS(listdirfiles=lambda common=False:[(None,"screens.rpyc"),("game","scene.rpy"),(None,"image.png")]))
        found=set(client.inventory(eng,report))
        self.assertEqual(found,{"Inventory is empty.","Open settings","Quest completed.","Your name?","Visible name"})
        self.assertEqual(report["script_files"],2)
        self.assertEqual(report["archived_scripts"],1)
        self.assertGreaterEqual(report["screen_nodes"],3)
        self.assertFalse(report["partial"])
    def test_inventory_translation_registry_and_progress(self):
        from types import SimpleNamespace as NS
        Say=type("Say",(),{})
        node=Say();node.what="An archived dialogue.";node.filename="game/scene.rpy"
        block=NS(filename="game/scene.rpy",block=[node])
        eng=NS(game=NS(script=NS(all_stmts=[],translator=NS(default_translates={"x":block},additional_strings={"game/options.rpy":[(1,"A menu string.")]}))))
        with tempfile.TemporaryDirectory() as d:
            side=Path(d)/client.SIDECAR;side.mkdir()
            c=client.Client(d)
            for text in client.inventory(eng):c.enqueue(text)
            c.finish_inventory(True);c.publish_progress()
            data=json.loads((side/"client-progress.json").read_text("utf-8"))
            self.assertEqual(data["inventory"],2)
            self.assertTrue(data["scan_complete"])
            self.assertEqual(data["pending"],2)
    def test_main_thread_refreshes_only_current_native_object(self):
        from types import SimpleNamespace as NS
        from unittest.mock import patch
        class Text:
            def set_text(self,value,*a,**kw):self.text=value
        class Input(Text):pass
        c=client.Client("synthetic")
        cfg=NS(say_menu_text_filter=None,periodic_callbacks=[])
        eng=NS(config=cfg,game=NS(script=NS(all_stmts=[]),context=lambda:NS(init_phase=False)),
            predicting=lambda:False,text=NS(text=NS(Text=Text)),display=NS(behavior=NS(Input=Input)))
        client._installed=False
        with patch.object(c,"start_prefetch"),patch.object(c,"start_progress"),patch.object(c,"request",side_effect=AssertionError("network in native setter")):
            client.install(eng,c)
            obj=Text();obj.set_text("Cold dialogue.")
            self.assertEqual(obj.text,"Cold dialogue.")
            old=Text();old.set_text("Old dialogue.");old.set_text("New dialogue.")
            c.remember("Cold dialogue.","Dialogo listo.")
            c.remember("Old dialogue.","No aplicar.")
            cfg.periodic_callbacks[0]()
            self.assertEqual(obj.text,"Dialogo listo.")
            self.assertEqual(old.text,"New dialogue.")
            inp=Input();inp.set_text("Cold dialogue.");self.assertEqual(inp.text,"Cold dialogue.")
        client._installed=False
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
        e.TEXT_TEXT=1;v.tokenized=True
        tokens=[(1,"Save"),(2,"b"),(3,object())]
        v.set_text(tokens)
        self.assertEqual(v.value[0],(1,"Guardar"));self.assertEqual(v.value[1:],tokens[1:])
        v.tokenized=False
        e.predicting=lambda:True
        v.set_text("Continue");self.assertIn(("Continue",False),fake.seen)
        del e.predicting
        e.exports=NS(predicting=lambda:True)
        v.set_text("Save");self.assertEqual(fake.seen[-1],("Save",False))
        e.exports.predicting=lambda:False
        v.set_text("Continue");self.assertEqual(fake.seen[-1],("Continue",True))
class ClassicRenpyR1(unittest.TestCase):
    def classic(self):
        s=importlib.util.spec_from_file_location("classic_client",BASE/"cmd/servidor/renpy_assets/classic_client.py")
        m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
    def test_classic_visible_markup_and_resource_guards(self):
        m=self.classic()
        for source in ("{b}Save{/b}", "{i}Continue{/i}", "Hello {image=images/star.png}", "Hello [name]", "{b}Save{/b} [name]"):
            self.assertTrue(m.visible(source),source)
        for source in ("{b}{/b}", "{image=images/star.png}", "[name]", "images/star.png", "{b}images/star.png{/b}", "http://example.org", "FLAG_QUEST"):
            self.assertFalse(m.visible(source),source)
        self.assertEqual(m.visible_probe("{b}Save{/b} [name]"),"Save ")
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
                return {"Hello":"Hola","Continue":"Continuar","Save":"Guardar","{b}Save{/b}":"{b}Guardar{/b}"}.get(s,s)
            def start_prefetch(self):pass
            def close(self):pass
        Say=type("Say",(),{});say=Say();say.what="Hello"
        Menu=type("Menu",(),{});menu=Menu();menu.items=[("Continue",True,[])]
        e=NS(game=NS(script=NS(all_stmts=[say,menu]),init_phase=False,context=lambda:NS(init_phase=False)),
             display=NS(text=NS(Text=Text),behavior=NS(Input=Input)))
        f=Fake();m.install(e,f)
        self.assertEqual(f.seen,["Hello","Continue"])
        self.assertEqual(Text("Hello").text,"Hola")
        self.assertEqual(Text("{b}Save{/b}").text,"{b}Guardar{/b}")
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
                self.assertEqual(c.translate('{b}Save{/b}'),'{b}Guardar{/b}')
                self.assertEqual(c.translate('She said "Hello"'),'Ella dijo "Hola"')
                self.assertEqual(service.translated,3)
                self.assertEqual(c.sequence,3)
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

class SDKProbeSourceTests(unittest.TestCase):
    def test_native_render_receipt_is_required_and_mode_specific(self):
        source=BASE/"tests/probe_renpy_installed_native.py"
        spec=importlib.util.spec_from_file_location("native_probe_receipt",source)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as d:
            result=Path(d)
            # The final success marker and a log line alone cannot replace
            # the separate receipt written after actual rendering.
            (result/"result.txt").write_text("NATIVE_INSTALLED_732_PREFLIGHT_OK",encoding="ascii")
            (result/"log.txt").write_text("NATIVE_PREBUILD_RENDER_AND_PERIODIC_REFRESH_PASS",encoding="ascii")
            with self.assertRaises(RuntimeError):m.verify_render_evidence(result,False)
            receipt=result/"render-result.txt"
            receipt.write_text("NATIVE_PREBUILD_RENDER_AND_PERIODIC_REFRESH_PASS",encoding="ascii")
            self.assertEqual(m.verify_render_evidence(result,False),"NATIVE_PREBUILD_RENDER_AND_PERIODIC_REFRESH_PASS")
            with self.assertRaises(RuntimeError):m.verify_render_evidence(result,True)
            receipt.write_text("NATIVE_REAL_RENDER_AND_PERIODIC_REFRESH_PASS",encoding="ascii")
            self.assertEqual(m.verify_render_evidence(result,True),"NATIVE_REAL_RENDER_AND_PERIODIC_REFRESH_PASS")
            with self.assertRaises(RuntimeError):m.verify_render_evidence(result,False)
            receipt.write_text("truncated",encoding="ascii")
            with self.assertRaises(RuntimeError):m.verify_render_evidence(result,True)
    def test_probe_sources_compile_and_keep_checks_active(self):
        import ast
        import re
        import textwrap
        files=(BASE/"tests/renpy_native_probe.py",BASE.parent/".github/scripts/renpy_classic_sdk_probe.py",BASE/"tests/probe_renpy_installed_native.py")
        for path in files:
            source=path.read_text(encoding="utf-8")
            tree=ast.parse(source,filename=str(path))
            compile(tree,str(path),"exec")
            scripts=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="SCRIPT" for t in n.targets)]
            self.assertEqual(len(scripts),1,str(path))
            lines=scripts[0].splitlines()
            blocks=[]
            for i,line in enumerate(lines):
                if not re.match(r"^\s*(?:init\s+\d+\s+)?python(?:\s+hide)?:\s*$",line):continue
                indent=len(line)-len(line.lstrip())
                end=i+1
                while end<len(lines):
                    v=lines[end]
                    if v.strip() and len(v)-len(v.lstrip())<=indent:break
                    end+=1
                code=textwrap.dedent("\n".join(lines[i+1:end]))
                block=ast.parse(code,filename=str(path))
                self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(block)),str(path))
                blocks.append(block)
            self.assertTrue(blocks,str(path))
            self.assertTrue(any(isinstance(n,ast.Raise) for block in blocks for n in ast.walk(block)),str(path))
        for name in ("classic_client.py","classic_start.py","classic_entry.py"):
            data=(BASE/"cmd/servidor/renpy_assets"/name).read_bytes()
            data.decode("ascii")
            self.assertNotIn(b"coding:",data.splitlines()[0])
            compile(data,name,"exec")

if __name__=="__main__":unittest.main()
