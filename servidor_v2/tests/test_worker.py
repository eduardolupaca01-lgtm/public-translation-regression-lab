import importlib.util, json, tempfile, threading, unittest
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
