"""Early real Edge/CSP smoke gate with a deterministic test-only neural stub.

Runs the same browser contract as the packaged-worker acceptance, before
loading the real model weights. It cannot certify OPUS or publish an EXE.
"""
import argparse
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from test_worker import ia
from probe_web_real_worker import HTML, SCRIPT

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"worker"))
import web_runtime

class ContractOnlyNeural:
    def translate(self,lang,text):
        known={
            ("en","Please open the window."):"Por favor, abre la ventana.",
            ("ja","橋を渡ってください。"):"Cruza el puente, por favor.",
        }
        if (lang,text) not in known:
            raise RuntimeError("IA_WEB_PREFLIGHT_UNKNOWN_TEXT")
        return known[(lang,text)]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--playwright",type=Path,required=True)
    args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix="IA Web CSP QA ") as tmp:
        root=Path(tmp).resolve()
        (root/"assets").mkdir()
        (root/"index.html").write_bytes(HTML)
        (root/"assets"/"main.js").write_bytes(SCRIPT)
        engine=root/"IA Traductora"/".local"/"Rpg"/"engine"
        engine.mkdir(parents=True)
        service=ia.Service(root,engine,neural=ContractOnlyNeural(),web_mode=True)
        server=None
        thread=None
        try:
            server=ia.ThreadingHTTPServer(("127.0.0.1",0),web_runtime.make_web_handler(service,ia.make_handler))
            server.daemon_threads=False
            server.block_on_close=True
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            url="http://127.0.0.1:"+str(server.server_port)
            subprocess.run(["node",str(Path(__file__).with_name("probe_web_browser.js")),url,
                            str(args.playwright.resolve())],check=True,timeout=90)
            assert (root/"index.html").read_bytes()==HTML
            assert (root/"assets"/"main.js").read_bytes()==SCRIPT
            assert service.translations==2,"IA_WEB_PREFLIGHT_NEURAL_CONTRACT"
            print("IA_WEB_CSP_BROWSER_PREFLIGHT_STUB_ONLY_PASS",flush=True)
        finally:
            if server is not None:
                if thread is not None:
                    server.shutdown()
                    thread.join(10)
                server.server_close()
            service.close()

if __name__=="__main__":main()
