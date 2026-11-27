"""Release gate: installed R38 worker, loopback web host and real Edge DOM.

Only independently authored, synthetic assets. No commercial game content.
"""
import argparse, hashlib, json, socket, sqlite3, subprocess, tempfile, time, re
from contextlib import closing
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

HTML=b'<html><head><script type="module" src="/assets/main.js"></script></head><body><div id="app"></div></body></html>'
SCRIPT=r'''
const records=[
 {zh:"test",jp:"",en:"Please open the window.",audio:""},
 {zh:"test",jp:"橋を渡ってください。",en:"",audio:""}
];
let at=Number(localStorage.getItem("fixture-save")||0);
const app=document.querySelector("#app");
app.innerHTML='<p id="dialog"></p><button id="next">Next</button><button id="save">Save</button><input id="name" value="Please keep my name."><span class="speaker-name" id="identity">Alice</span>';
const draw=()=>{document.querySelector("#dialog").textContent=records[at].en||records[at].jp};
document.querySelector("#next").onclick=()=>{at=1;draw()};
document.querySelector("#save").onclick=()=>localStorage.setItem("fixture-save",String(at));
draw();
'''.encode("utf8")

def request(url,path,token=None,body=None):
    headers={}
    if token:headers["X-IA-Token"]=token
    if body is not None:headers.update({"Origin":url,"Content-Type":"application/json"})
    return urlopen(Request(url+path,data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=10)

def main():
    p=argparse.ArgumentParser();p.add_argument("--servidor",type=Path,required=True)
    p.add_argument("--playwright",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix="IA Web Real 日本語 ") as tmp:
        root=Path(tmp);assets=root/"assets";assets.mkdir()
        (root/"index.html").write_bytes(HTML);(assets/"main.js").write_bytes(SCRIPT)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
        url="http://127.0.0.1:"+str(port)
        cmd=[str(a.servidor.resolve()),"--web-folder",str(root),"--web-port",str(port),"--web-no-browser"]
        process=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        token=None
        try:
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                if process.poll() is not None:raise AssertionError("IA_WEB_PACKAGED_WORKER_EXIT_"+str(process.returncode))
                try:
                    with request(url,"/__ia/adapter.js") as r:script=r.read().decode("utf8")
                    m=re.search(r'const token="([0-9a-f]{64})";',script)
                    if m:token=m[1];break
                except OSError:time.sleep(.3)
            assert token,"IA_WEB_PACKAGED_BOOT_TIMEOUT"
            with request(url,"/__ia/catalog",token) as r:
                inventory=json.load(r)
                assert inventory["records"]==2 and len(inventory["items"])==2
            with request(url,"/") as r:assert b"/__ia/adapter.js" in r.read()
            subprocess.run(["node",str(Path(__file__).with_name("probe_web_browser.js")),url,str(a.playwright.resolve())],
                           check=True,timeout=320)
            with request(url,"/__ia/status",token) as r:assert json.load(r)["active"]
            with request(url,"/__ia/stop",token,{}) as r:assert json.load(r)["stopping"]
            assert process.wait(timeout=45)==0,"IA_WEB_PACKAGED_SHUTDOWN_FAIL"
            cache=root/"IA Traductora"/".local"/"Rpg"/"cache"/"translation-memory-v2.sqlite3"
            with closing(sqlite3.connect(cache.resolve().as_uri()+"?mode=ro",uri=True)) as db:
                assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
                rows=db.execute("SELECT count(*) FROM translations").fetchone()[0]
                assert rows>=2,"IA_WEB_CACHE_NOT_PERSISTENT"
            assert (root/"index.html").read_bytes()==HTML
            assert (assets/"main.js").read_bytes()==SCRIPT
            print("IA_WEB_PACKAGED_REAL_OPUS_BROWSER_AND_ORIGINALS_PASS",flush=True)
        finally:
            if process.poll() is None:
                if token:
                    try:
                        with request(url,"/__ia/stop",token,{}):pass
                    except OSError:pass
                try:process.wait(timeout=35)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=15)
if __name__=="__main__":main()
