"""End-to-end create-only web desktop acceptance using the packaged player."""
import hashlib, os, sqlite3, subprocess, tempfile, time
from pathlib import Path
from contextlib import closing
from probe_web_real_worker import HTML,SCRIPT

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--servidor",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix="IA Desktop 日本語 ") as tmp:
        base=Path(tmp)
        source=base/"Extracted";source.mkdir();(source/"assets").mkdir()
        (source/"index.html").write_bytes(HTML);(source/"assets"/"main.js").write_bytes(SCRIPT)
        (source/"Game.exe").write_bytes(b"not a launcher")
        (source/"private.txt").write_bytes(b"not a resource")
        originals={p.relative_to(source):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in source.rglob("*") if p.is_file()}
        subprocess.run([str(a.servidor.resolve()),"--web-folder",str(source),"--web-copy","--web-copy-parent",str(base)],
                       check=True,timeout=180)
        copies=list(base.glob("Juego-IA-WEB-*"))
        assert len(copies)==1,"IA_WEB_DESKTOP_COPY_MISSING"
        copy=copies[0];player=copy/"Jugar-IA.exe"
        assert player.is_file() and not (copy/"IA_COPIA_WEB_INCOMPLETA.txt").exists()
        assert not (copy/"Game.exe").exists() and not (copy/"private.txt").exists()
        rpg=copy/"IA Traductora"/".local"/"Rpg"
        receipt=(copy/"web-copy-v1.json").read_bytes()
        env=dict(os.environ,IA_WEB_DESKTOP_QA="1")
        result=rpg/"web-qa-result.txt"
        for mode,expected in (("--qa","IA_WEB_DESKTOP_NATIVE_QA_PASS"),("--qa-reopen","IA_WEB_DESKTOP_REOPEN_QA_PASS")):
            result.unlink(missing_ok=True)
            proc=subprocess.run([str(player),mode],cwd=base,env=env,timeout=430)
            actual=result.read_text("utf8").strip() if result.exists() else "IA_WEB_DESKTOP_RESULT_MISSING"
            assert proc.returncode==0 and actual==expected,actual
            print(expected,flush=True)
        with closing(sqlite3.connect((rpg/"cache"/"translation-memory-v2.sqlite3").resolve().as_uri()+"?mode=ro",uri=True)) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            assert db.execute("SELECT count(*) FROM translations").fetchone()[0]>=2
        assert (copy/"web-copy-v1.json").read_bytes()==receipt
        assert (copy/"index.html").read_bytes()==HTML and (copy/"assets"/"main.js").read_bytes()==SCRIPT
        assert {p.relative_to(source):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in source.rglob("*") if p.is_file()}==originals
        print("IA_WEB_DESKTOP_COPY_SOURCE_SAVE_AND_OPUS_PASS",flush=True)

if __name__=="__main__":main()
