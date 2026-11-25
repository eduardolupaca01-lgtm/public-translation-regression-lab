import importlib.util, json, tempfile, threading, unittest
from types import SimpleNamespace
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
path=Path(__file__).resolve().parents[1]/"worker"/"IATraductora.py"
spec=importlib.util.spec_from_file_location("ia",path)
ia=importlib.util.module_from_spec(spec);spec.loader.exec_module(ia)

class FakeNeural:
    def translate(self,lang,text):return "Buenos días" if lang=="ja" else "Buen día"

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for file in ("www/js/rpg_core.js","www/js/plugins.js","www/data/System.json"):
            dst=self.root/file;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text("{}")
        self.engine=self.root/"IA Traductora"/".local"/"Rpg"/"engine"
        self.engine.mkdir(parents=True)
        self.s=ia.Service(self.root,self.engine,neural=FakeNeural())
        self.addCleanup(self.s.close)
        self.server=ia.ThreadingHTTPServer(("127.0.0.1",0),ia.make_handler(self.s))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start();self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
    def http(self,endpoint,body=None,token=None):
        data=json.dumps(body).encode() if body else None
        req=Request("http://127.0.0.1:%d%s"%(self.server.server_port,endpoint),
            data=data,headers={"X-IA-Token":token if token is not None else self.s.token},
            method="POST" if data else "GET")
        with urlopen(req,timeout=3) as resp:return json.loads(resp.read().decode())
    def test_spanish_and_deduplicate(self):
        msg={"source":"ja","target":"es","text":"おはようございます。"}
        self.assertEqual(self.http("/translate",msg)["translated"],"Buenos días")
        self.assertEqual(self.http("/translate",msg)["translated"],"Buenos días")
        self.assertEqual(self.s.translations,1)
    def test_cache_survives_full_worker_restart(self):
        original="おはようございます。"
        first=self.http("/translate",{"source":"ja","target":"es","text":original})
        self.assertEqual(first["translated"],"Buenos días")
        class NoInference:
            count=0
            def translate(self,*_):
                self.count+=1
                raise AssertionError("NEURAL_WORK_SHOULD_NOT_REPEAT")
        backend=NoInference()
        again=ia.Service(self.root,self.engine,neural=backend)
        self.addCleanup(again.close)
        self.assertEqual(again.translate("ja",original),"Buenos días")
        self.assertEqual(backend.count,0)
        self.assertTrue((self.engine.parent/"cache"/"translation-memory-v2.sqlite3").is_file())
    def test_quality_gate_no_numbers_lost_or_japanese_leaked(self):
        invalid=[
            ("ja","8月24日","24 de agosto","IA_QUALITY_NUMBER_MISSING"),
            ("ja","今日は学校に行きます。","今日は学校に行きます。","IA_QUALITY_UNCHANGED"),
            ("ja","早く行こう。","Vamos \ufffd","IA_QUALITY_CORRUPT"),
            ("ja","夏実は来た。","Natsumi 夏実 vino.","IA_QUALITY_JAPANESE_RESIDUAL"),
            ("ja","こんにちは！","hola hola hola hola hola hola", "IA_QUALITY_REPEATED_GENERATION"),
        ]
        for lang,original,output,reason in invalid:
            with self.subTest(reason=reason):
                self.assertEqual(ia.quality_reason(lang,original,output),reason)
        self.assertIsNone(ia.quality_reason("ja","08月24日","24 de agosto (8)"))
        self.assertIsNone(ia.quality_reason("ja","夏実は来た。","Natsumi llegó."))
    def test_r12_numeric_recovery_requires_equal_counter(self):
        cases=[
            ("５年前に会った。","Nos vimos hace cinco años.","Nos vimos hace 5 años."),
            ("今は５時です。","Son las cinco.","Son las 5."),
            ("５年前に会った。","Nos vimos hace cuatro años.","Nos vimos hace cuatro años."),
            ("５年後です。","Pasarán años.","Pasarán años."),
            ("５年と２月です。","Cinco años y dos meses.","Cinco años y dos meses."),
            ("５時です。","Son las cinco y media.","Son las cinco y media."),
            ("５年後です。","Pasarán treinta y cinco años.","Pasarán treinta y cinco años."),
            ("５年後です。","Pasarán cinco años y dos meses.","Pasarán cinco años y dos meses."),
            ("５年後です。","Pasarán ciento cinco años.","Pasarán ciento cinco años.")
        ]
        for original,generated,want in cases:
            self.assertEqual(ia.recover_numeric_surface("ja",original,generated),want)
        self.assertIsNone(ia.native_quality_reason("ja",cases[0][0],cases[0][2]))
        self.assertEqual(ia.quality_reason("ja",cases[2][0],cases[2][2]),"IA_QUALITY_NUMBER_MISSING")
        self.assertEqual(ia.quality_reason("ja",cases[3][0],cases[3][2]),"IA_QUALITY_NUMBER_MISSING")
    def test_r12_retries_only_rejected_japanese_with_sentence_context(self):
        class Tokenizer:
            def encode(self,text,out_type):return [text]
            def decode(self,hyp):return hyp[0]
        class Model:
            def __init__(self):self.calls=[]
            def translate_batch(self,source,**kw):
                self.calls.append(source)
                texts={"おはよう。":"Buenos días.","今は5時です。":"Son las cinco.",
                       "駅はどこ？":"¿Dónde está la estación?"}
                return [SimpleNamespace(hypotheses=[[texts.get(t[0],"No sé.")]]) for t in source]
        backend=ia.NeuralOPUS.__new__(ia.NeuralOPUS)
        backend.lock=threading.RLock()
        model=Model()
        backend.models={"ja":(model,Tokenizer(),Tokenizer())}
        backend.roots={}
        backend.source_end_tokens={"ja":None}
        self.assertEqual(backend.translate_many("ja",["おはよう。","今は５時です。駅はどこ？"]),
                         ["Buenos días.","Son las 5. ¿Dónde está la estación?"])
        self.assertTrue(all(["おはよう。"] not in call for call in model.calls[1:]))
    def test_source_eos_matches_packaged_marian_contract(self):
        class Tokenizer:
            def eos_id(self):return 2
            def id_to_piece(self,i):return "</s>"
            def encode(self,text,out_type):return text.split()
        tok=Tokenizer()
        en={"add_source_eos":False,"eos_token":"</s>"}
        ja={"add_source_eos":True,"eos_token":"</s>"}
        self.assertEqual(ia.manual_source_eos(en,tok),"</s>")
        self.assertIsNone(ia.manual_source_eos(ja,tok))
        self.assertEqual(ia.encode_source(tok,"Thank you",ia.manual_source_eos(en,tok)),
                         ["Thank","you","</s>"])
        self.assertEqual(ia.encode_source(tok,"Thank you </s>","</s>"),
                         ["Thank","you","</s>"])
        self.assertEqual(ia.encode_source(tok,"日本語",ia.manual_source_eos(ja,tok)),
                         ["日本語"])
        self.assertEqual(ia.encode_source(tok,"","</s>"),[])
        with self.assertRaisesRegex(RuntimeError,"IA_MODELO_TOKEN_EOS_INVALIDO"):
            ia.manual_source_eos({"add_source_eos":False,"eos_token":"<bad>"},tok)
        with self.assertRaisesRegex(RuntimeError,"IA_MODELO_CONFIG_EOS_INVALIDA"):
            ia.manual_source_eos({},tok)
        class Model:
            def translate_batch(self,source,**kw):
                assert all(v[-1]=="</s>" and v.count("</s>")==1 for v in source)
                return [SimpleNamespace(hypotheses=[["Gracias por tu ayuda."]]) for _ in source]
        class Target:
            def decode(self,hyp):return hyp[0]
        backend=ia.NeuralOPUS.__new__(ia.NeuralOPUS)
        backend.lock=threading.RLock()
        backend.roots={}
        backend.source_end_tokens={"en":ia.manual_source_eos(en,tok)}
        backend.models={"en":(Model(),tok,Target())}
        self.assertEqual(backend.translate_many("en",["Thank you for your help.","Thank you."]),
                         ["Gracias por tu ayuda.","Gracias por tu ayuda."])
    def test_english_bad_cached_markup_and_repetition(self):
        import hashlib
        src="There is a sound at the gate."
        bad="Hay una voz <<<W wordwordWrap> Hay Hay Hay una voz."
        self.assertEqual(ia.quality_reason("en",src,bad),"IA_QUALITY_EN_MARKUP")
        self.assertEqual(ia.quality_reason("en",src,"Una voz voz voz."),"IA_QUALITY_REPEATED_GENERATION")
        self.assertIsNone(ia.quality_reason("en",src,"Se oye un ruido en la entrada."))
        key=hashlib.sha256(("en\0"+src).encode()).hexdigest()
        self.s.memory.db.execute("INSERT INTO translations VALUES (?,?,?,?,?,?)",
           (key,ia.CACHE_SCHEMA,"en",src,bad,0))
        self.s.memory.db.commit()
        self.assertIsNone(self.s.memory.get(key,"en",src))
        self.assertTrue(self.s.memory.put(key,"en",src,"Se oye un ruido en la entrada."))
        self.assertEqual(self.s.memory.get(key,"en",src),"Se oye un ruido en la entrada.")
    def test_laughter_is_not_a_translation_for_a_question(self):
        self.assertEqual(ia.quality_reason("ja","明日は行くの？","(Risas)"),
                         "IA_QUALITY_LAUGHTER_INVENTED")
        self.assertIsNone(ia.quality_reason("ja","あははは。","(Risas)"))
        self.assertIsNone(ia.quality_reason("ja","明日は行くの？","¿Vas mañana?"))
    def test_old_applause_cache_is_rejected_without_erasing_good_rows(self):
        import hashlib
        original="明日は雨が降ります。"
        key=hashlib.sha256(("ja\0"+original).encode()).hexdigest()
        self.s.memory.db.execute("INSERT INTO translations VALUES (?,?,?,?,?,?)",
             (key,ia.CACHE_SCHEMA,"ja",original,"(Aplausos)",0))
        self.s.memory.db.commit()
        self.assertIsNone(self.s.memory.get(key,"ja",original))
        self.assertEqual(ia.quality_reason("ja",original,"(Aplausos)"),
                         "IA_QUALITY_APPLAUSE_INVENTED")
        self.assertIsNone(ia.quality_reason("ja","拍手が起こった。","(Aplausos)"))
        self.assertEqual(ia.native_quality_reason("ja",original,"(Lloverá mañana)"),
                         "IA_QUALITY_NATIVE_DELIMITERS")
        self.assertTrue(self.s.memory.put(key,"ja",original,"Mañana lloverá."))
        self.assertEqual(self.s.memory.get(key,"ja",original),"Mañana lloverá.")
    def test_recovery_redecodes_only_rejected_segments(self):
        class Tokenizer:
            def encode(self,text,out_type):return [text]
            def decode(self,hyp):return hyp[0]
        class Model:
            def __init__(self):self.calls=[]
            def translate_batch(self,source,**kw):
                self.calls.append((source,kw))
                return [SimpleNamespace(hypotheses=[
                    ["Buenos días."] if t[0]=="おはよう。" else
                    ["Mañana lloverá."] if kw["beam_size"]==6 else ["(Aplausos)"]
                ]) for t in source]
        model=Model()
        backend=ia.NeuralOPUS.__new__(ia.NeuralOPUS)
        backend.lock=threading.RLock()
        backend.models={"ja":(model,Tokenizer(),Tokenizer())}
        backend.roots={}
        backend.source_end_tokens={"ja":None,"en":None}
        self.assertEqual(backend.translate_many("ja",["おはよう。","明日は雨が降ります。"]),
                         ["Buenos días.","Mañana lloverá."])
        self.assertEqual(len(model.calls),2)
        self.assertEqual(model.calls[1][0],[["明日は雨が降ります。"]])
        self.assertEqual(model.calls[0][1]["beam_size"],4)
    def test_english_recovery_short_budget_never_accepts_bad_output(self):
        class Tokenizer:
            def encode(self,text,out_type):return [text]
            def decode(self,hyp):return hyp[0]
        class Model:
            def __init__(self):self.calls=[]
            def translate_batch(self,source,**kw):
                self.calls.append((source,kw))
                return [SimpleNamespace(hypotheses=[[
                    "Buenos días." if t[0]=="Good morning." else
                    "Gracias por tu ayuda." if kw["beam_size"]==1 else
                    "Gracias gracias gracias <<<W>"
                ]]) for t in source]
        model=Model()
        backend=ia.NeuralOPUS.__new__(ia.NeuralOPUS)
        backend.lock=threading.RLock()
        backend.models={"en":(model,Tokenizer(),Tokenizer())}
        backend.roots={}
        backend.source_end_tokens={"ja":None,"en":None}
        result=backend.translate_many("en",["Good morning.","Thank you for your help."])
        self.assertEqual(result,["Buenos días.","Gracias por tu ayuda."])
        self.assertEqual([c[1]["beam_size"] for c in model.calls],[4,6,1])
        self.assertEqual(model.calls[-1][0],[["Thank you for your help."]])
        self.assertLess(model.calls[-1][1]["max_decoding_length"],model.calls[0][1]["max_decoding_length"])
    def test_historical_early_not_young_semantic_gate(self):
        source="お前はいつも早過ぎなんだよ。"
        self.assertEqual(ia.quality_reason("ja",source,
            "Siempre eres demasiado joven."),"IA_QUALITY_TIME_AGE_CONFUSION")
        self.assertIsNone(ia.quality_reason("ja",source,
            "Siempre llegas demasiado temprano."))
    def test_neural_selects_structurally_safe_beam_without_losing_codes(self):
        class SourceTokenizer:
            def encode(self,text,out_type):return ["__source__"]
        class TargetTokenizer:
            def decode(self,hyp):return hyp[0]
        class FakeCandidateModel:
            def translate_batch(self,source,**kwargs):
                self.kwargs=kwargs
                return [SimpleNamespace(hypotheses=[
                    ["Siempre eres demasiado joven."],
                    ["Siempre llegas demasiado temprano."],
                    ["いつも早過ぎなんだよ。"]
                ])]
        backend=ia.NeuralOPUS.__new__(ia.NeuralOPUS)
        backend.lock=threading.RLock()
        model=FakeCandidateModel()
        backend.models={"ja":(model,SourceTokenizer(),TargetTokenizer())}
        backend.roots={}
        backend.source_end_tokens={"ja":None,"en":None}
        result=backend.translate("ja","お前はいつも早過ぎなんだよ。")
        self.assertEqual(result,"Siempre llegas demasiado temprano.")
        self.assertEqual(model.kwargs["num_hypotheses"],3)
        self.assertGreater(model.kwargs["repetition_penalty"],1.0)
    def test_all_opus_candidates_rejected_visible_in_qa_status(self):
        class UnsafeNeural:
            def translate(self,*_):
                raise RuntimeError("IA_QUALITY_ALL_CANDIDATES_REJECTED")
        unsafe=ia.Service(self.root,self.engine,neural=UnsafeNeural())
        self.addCleanup(unsafe.close)
        with self.assertRaises(RuntimeError):
            unsafe.translate("ja","おはようございます。")
        self.assertEqual(unsafe.quality_rejected,1)
    def test_batch_preserves_order_identity_and_deduplicates_inference(self):
        class BatchNeural:
            def __init__(self):self.calls=[]
            def translate_many(self,lang,texts):
                self.calls.append(list(texts))
                return ["Buenos días" if t=="おはよう" else
                        "Buenas tardes" if t=="こんにちは" else None for t in texts]
        neural=BatchNeural()
        service=ia.Service(self.root,self.engine,neural=neural)
        self.addCleanup(service.close)
        texts=["おはよう","こんにちは","おはよう","数字を守る"]
        result=service.translate_batch("ja",texts)
        self.assertEqual([v.get("translated") for v in result],
                         ["Buenos días","Buenas tardes","Buenos días",None])
        self.assertEqual(neural.calls,[["おはよう","こんにちは","数字を守る"]])
        self.assertTrue(result[3]["permanent"])
        self.assertEqual(service.quality_rejected,1)
        self.assertEqual(service.translations,2)
        self.assertEqual(service.translate_batch("ja",texts[:3]),result[:3])
        self.assertEqual(len(neural.calls),1,"batch cache must avoid duplicate inference")
        again=ia.Service(self.root,self.engine,neural=BatchNeural())
        self.addCleanup(again.close)
        self.assertEqual(again.translate_batch("ja",texts[:3]),result[:3])
        self.assertEqual(again.neural.calls,[])
    def test_authenticated_batch_http_and_permanent_qa_code(self):
        result=self.http("/translate_batch",{"source":"ja","target":"es",
            "texts":["おはよう","こんにちは","おはよう"]})
        self.assertEqual(len(result["results"]),3)
        self.assertTrue(self.http("/status")["batch"])
        with self.assertRaises(HTTPError) as error:
            self.http("/translate_batch",{"source":"ja","target":"es","texts":["こんにちは"]*7})
        self.assertEqual(error.exception.code,400)
        with self.assertRaises(HTTPError) as error:
            self.http("/translate",{"source":"ja","target":"es","text":"2月です"})
        self.assertEqual(error.exception.code,422)
    def test_authentication(self):
        with self.assertRaises(HTTPError) as e:self.http("/status",token="0"*64)
        self.assertEqual(e.exception.code,403)
    def test_identity_and_bridge(self):
        bridge=ia.publish(self.s,self.server.server_port)
        self.assertEqual(bridge.parent.name,"IATraductora")
        self.assertEqual(json.loads(bridge.read_text())["schema"],"ia-traductora-bridge-v1")
        self.assertEqual(self.http("/status")["active"],True)
    def test_no_game_rewrite(self):
        data=self.root/"www/data/System.json"
        before=data.read_bytes()
        self.http("/translate",{"source":"ja","target":"es","text":"おはよう"})
        self.assertEqual(data.read_bytes(),before)
    def test_bounded_neural_decoding_budgets(self):
        self.assertEqual(ia.decoding_budget("en",2),32)
        self.assertLessEqual(ia.decoding_budget("en",400),144)
        self.assertLessEqual(ia.decoding_budget("ja",400),300)
        self.assertGreater(ia.decoding_budget("ja",20),0)
    def test_parent_lifetime_diagnostic_and_linux_noop(self):
        self.assertEqual(ia.safe_startup_code(RuntimeError("IA_PARENT_PID_INVALIDO")),
                         "IA_PARENT_PID_INVALIDO")
        if ia.os.name!="nt":
            ia.monitor_game_lifetime(self.server,123456789)
    def test_invalid_languages_fail(self):
        with self.assertRaises(HTTPError) as e:
            self.http("/translate",{"source":"fr","target":"es","text":"Bonjour"})
        self.assertEqual(e.exception.code,400)


class MZLayoutTests(unittest.TestCase):
    def test_mz_root_and_wrapped(self):
        for wrapped in (False,True):
            with self.subTest(wrapped=wrapped), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                content=root/"www" if wrapped else root
                for file in ("js/rmmz_core.js","js/rmmz_managers.js","js/rmmz_objects.js","js/rmmz_scenes.js","js/rmmz_windows.js","js/plugins.js","data/System.json"):
                    dest=content/file;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text("{}")
                self.assertEqual(ia.game_root(root),(root.resolve(),content.resolve()))
                engine=root/"IA Traductora"/".local"/"Rpg"/"engine"
                engine.mkdir(parents=True)
                service=ia.Service(root,engine,neural=FakeNeural())
                try:
                    self.assertEqual(service.translate("en","Good morning."),"Buen día")
                finally:
                    service.close()
                (content/"js"/"rpg_core.js").write_text("{}")
                with self.assertRaises(ValueError):ia.game_root(root)

class CompressedMZWorkerTests(unittest.TestCase):
    def fixture(self,root,wrapped=False):
        content=root/"www" if wrapped else root
        for name in ("rmmz_core.js","rmmz_managers.js","rmmz_objects.js","rmmz_scenes.js","rmmz_windows.js",
                     "plugins/POR_DatabaseEncoder.js","plugins/lz-string.min.js"):
            file=content/"js"/name
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text("// synthetic native marker",encoding="utf8")
        data=content/"data"
        data.mkdir()
        for name in ("System","Actors","CommonEvents","MapInfos"):
            (data/(name+".jsono")).write_bytes(b"N4XyA===")
        entries=[{"name":"POR_DatabaseEncoder","status":True,"parameters":{}},
                 {"name":"lz-string.min","status":True,"parameters":{}},
                 {"name":"IATraductora","status":True,"parameters":{}}]
        (content/"js"/"plugins.js").write_text("// generated\nvar $plugins = "+json.dumps(entries)+";",encoding="utf-8-sig")
        return content,entries
    def test_worker_mz_compressed_root_and_www_authenticated_http(self):
        for wrapped in (False,True):
            with self.subTest(wrapped=wrapped),tempfile.TemporaryDirectory(prefix="IA R18 日本語 ") as tmp:
                root=Path(tmp)
                content,entries=self.fixture(root,wrapped)
                snapshots={f:f.read_bytes() for f in (content/"data").glob("*.jsono")}
                registry=content/"js"/"plugins.js";before=registry.read_bytes()
                self.assertEqual(ia.game_root(root),(root.resolve(),content.resolve()))
                engine=root/"IA Traductora"/".local"/"Rpg"/"engine"
                engine.mkdir(parents=True)
                service=ia.Service(root,engine,neural=FakeNeural())
                server=ia.ThreadingHTTPServer(("127.0.0.1",0),ia.make_handler(service))
                bridge=ia.publish(service,server.server_port)
                thread=threading.Thread(target=server.serve_forever,daemon=True)
                thread.start()
                try:
                    descriptor=json.loads(bridge.read_text(encoding="utf8"))
                    # Windows tempfile can return an 8.3 alias (RUNNER~1)
                    # while game_root resolves the long name (runneradmin).
                    # Verify actual file identity, not the spelling of a path.
                    expected_bridge=content/"data"/"IATraductora"/"bridge.json"
                    self.assertTrue(expected_bridge.is_file())
                    self.assertFalse(expected_bridge.is_symlink())
                    self.assertTrue(bridge.samefile(expected_bridge),
                                    "The authenticated bridge must be in the actual game data directory")
                    self.assertEqual(bridge.resolve(strict=True),expected_bridge.resolve(strict=True))
                    base="http://127.0.0.1:"+str(descriptor["port"])
                    headers={"X-IA-Token":descriptor["token"],"Content-Type":"application/json"}
                    with urlopen(Request(base+"/status",headers=headers),timeout=3) as response:
                        self.assertTrue(json.load(response)["active"])
                    for lang,raw,expected in (("en","Good morning.","Buen día"),("ja","おはようございます。","Buenos días")):
                        payload=json.dumps({"source":lang,"target":"es","text":raw}).encode()
                        with urlopen(Request(base+"/translate",data=payload,headers=headers),timeout=3) as response:
                            self.assertEqual(json.load(response)["translated"],expected)
                    self.assertEqual(service.translations,2)
                    self.assertEqual(service.memory.db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                finally:
                    server.shutdown();server.server_close();thread.join(3);service.close()
                self.assertFalse((content/"data"/"System.json").exists())
                self.assertEqual(registry.read_bytes(),before)
                for f,raw in snapshots.items():self.assertEqual(f.read_bytes(),raw)
    def test_worker_rejects_inactive_missing_invalid_and_ambiguous(self):
        for case in ("inactive","missing","invalid","mv","dual"):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);content,entries=self.fixture(root)
                if case=="inactive":
                    entries[0]["status"]=False
                    (content/"js"/"plugins.js").write_text("var $plugins = "+json.dumps(entries)+";",encoding="utf8")
                if case=="missing":(content/"data"/"Actors.jsono").unlink()
                if case=="invalid":(content/"data"/"System.jsono").write_text("invalid data")
                if case=="mv":
                    (content/"js"/"rmmz_core.js").unlink()
                    (content/"js"/"rpg_core.js").write_text("{}")
                if case=="dual":self.fixture(root,True)
                with self.assertRaises(ValueError) as error:ia.game_root(root)
                want="IA_RPG_RUTAS_AMBIGUAS" if case=="dual" else ("IA_SOLAMENTE_RPG_MV_MZ" if case=="mv" else "IA_RPG_MZ_COMPRIMIDO_NO_VALIDO")
                self.assertEqual(ia.safe_startup_code(error.exception),want)
    def test_startup_diagnostic_is_specific_but_private(self):
        self.assertEqual(ia.safe_startup_code(ValueError("IA_SOLAMENTE_RPG_MV_MZ")),"IA_SOLAMENTE_RPG_MV_MZ")
        self.assertEqual(ia.safe_startup_code(ValueError("IA_RPG_MZ_COMPRIMIDO_NO_VALIDO")),"IA_RPG_MZ_COMPRIMIDO_NO_VALIDO")
        self.assertEqual(ia.safe_startup_code(ValueError("unknown private path")),"IA_MOTOR_ERROR_NO_CLASIFICADO")

if __name__=="__main__":unittest.main()
