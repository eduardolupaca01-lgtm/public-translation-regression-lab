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

if __name__=="__main__":unittest.main()
