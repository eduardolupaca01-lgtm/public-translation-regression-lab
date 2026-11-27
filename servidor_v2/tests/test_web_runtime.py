import sys, tempfile, threading, unittest, json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from test_worker import ia, FakeNeural
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"worker"))
import web_runtime as web

class WebRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="IA Web 日本語 ")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        assets=self.root/"assets";assets.mkdir()
        self.index=b'<html><head><script type="module" src="/assets/main.js"></script></head><body><div id="app"></div></body></html>'
        self.js=b'const data=[{zh:"test",jp:"\\u304a\\u306f\\u3088\\u3046",en:"Good morning.",audio:""},{zh:"test",jp:"",en:"Good morning.",audio:""}];'
        (self.root/"index.html").write_bytes(self.index)
        (assets/"main.js").write_bytes(self.js)
        (assets/"clip.mp3").write_bytes(b"1234567890")
        (self.root/"private.txt").write_text("private fixture")
        engine=self.root/"IA Traductora"/".local"/"Rpg"/"engine"
        engine.mkdir(parents=True)
        self.service=ia.Service(self.root,engine,neural=FakeNeural(),web_mode=True)
        self.server=ia.ThreadingHTTPServer(("127.0.0.1",0),web.make_web_handler(self.service,ia.make_handler))
        self.url="http://127.0.0.1:"+str(self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup_server)
    def cleanup_server(self):
        self.server.shutdown();self.thread.join(5);self.server.server_close();self.service.close()
    def req(self,path,body=None,token=True,origin=None,extra=None):
        headers={}
        if token:headers["X-IA-Token"]=self.service.token
        if origin is not None:headers["Origin"]=origin
        if extra:headers.update(extra)
        if body is not None:
            body=json.dumps(body).encode("utf8")
            headers["Content-Type"]="application/json"
        return urlopen(Request(self.url+path,data=body,headers=headers),timeout=5)
    def test_virtual_html_catalog_and_real_service_contract(self):
        with self.req("/") as r:
            page=r.read();self.assertIn(b"/__ia/adapter.js",page)
            csp=r.headers["Content-Security-Policy"]
            self.assertIn("frame-ancestors 'none'",csp)
            self.assertEqual(next(x.strip() for x in csp.split(";") if x.strip().startswith("script-src ")),
                             "script-src 'self'")
            self.assertNotIn("'unsafe-eval'",csp)
        with self.req("/__ia/catalog") as r:
            c=json.load(r)
        self.assertEqual(c["records"],2)
        self.assertEqual(c["items"],[{"source":"en","text":"Good morning."}])
        with self.req("/__ia/translate",{"source":"en","target":"es","text":"Good morning."},origin=self.url) as r:
            self.assertEqual(json.load(r)["translated"],"Buen día")
        self.assertEqual((self.root/"index.html").read_bytes(),self.index)
        self.assertEqual((self.root/"assets"/"main.js").read_bytes(),self.js)
    def test_no_private_paths_and_cross_origin_requests(self):
        for path in ("/private.txt","/IA%20Traductora/.local/Rpg/engine/IATraductora.exe",
                     "/assets/../private.txt","/assets/%2e%2e/private.txt","/assets/a%5c..%5cprivate.txt"):
            with self.assertRaises(HTTPError) as e:self.req(path)
            self.assertEqual(e.exception.code,404);e.exception.close()
        for path,headers in (("/__ia/catalog",{"token":False}),
                             ("/",{"origin":"https://example.invalid"}),
                             ("/",{"extra":{"Host":"example.invalid"}})):
            with self.assertRaises(HTTPError) as e:self.req(path,**headers)
            self.assertEqual(e.exception.code,403);e.exception.close()
        with self.assertRaises(HTTPError) as e:self.req("/__ia/translate",{"source":"en","target":"es","text":"Good morning."})
        self.assertEqual(e.exception.code,403);e.exception.close()
        self.assertEqual(self.service.translations,0)
    def test_ranges_and_missing_module(self):
        with self.req("/assets/clip.mp3",extra={"Range":"bytes=2-4"}) as r:
            self.assertEqual(r.status,206);self.assertEqual(r.read(),b"345")
        with self.req("/assets/clip.mp3",extra={"Range":"bytes=-3"}) as r:
            self.assertEqual(r.read(),b"890")
        (self.root/"assets"/"main.js").unlink()
        with self.assertRaises(ValueError):web.web_profile(self.root)
    def test_catalog_never_evaluates_js_or_scans_untyped_fields(self):
        file=self.root/"assets"/"catalog.js"
        file.write_text(r'const rows=[{zh:"x",jp:"\u6a4b",en:"",audio:"x"},{zh:"x",jp:"x",en:"Open\x20the window.",audio:"x"}]; const skip={en:"Unrelated technical field"};',encoding="utf8")
        data=web.catalog([file])
        self.assertEqual(data["records"],2)
        self.assertEqual(data["items"],[{"source":"en","text":"Open the window."}])
if __name__=="__main__":unittest.main()
