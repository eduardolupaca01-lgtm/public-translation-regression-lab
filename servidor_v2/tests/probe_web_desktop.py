"""End-to-end create-only web desktop acceptance using the packaged player."""
import hashlib, os, shutil, sqlite3, subprocess, tempfile, time
from pathlib import Path
from contextlib import closing
from probe_web_real_worker import HTML,SCRIPT

def file_hash(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def build_embedded_fixture(base):
    # A genuine stripped Go PE64 with 600 MiB of distinct synthetic
    # embedded payloads. No original game, Wails license or external decoder.
    build=base/"Build";build.mkdir()
    dist=build/"frontend"/"dist";(dist/"assets").mkdir(parents=True)
    (dist/"index.html").write_bytes(HTML)
    (dist/"assets"/"main.js").write_bytes(SCRIPT)
    for n in range(6):
        with (dist/"assets"/("payload-%02d.mp3"%n)).open("wb") as f:
            block=bytes([n+17])*(1024*1024)
            for _ in range(100):f.write(block)
    for n in range(208):
        (dist/"assets"/("fixture-%03d.txt"%n)).write_text("synthetic %d"%n,encoding="ascii")
    (dist/"assets"/"日本語.mp3").write_bytes(b"unicode path fixture")
    expected={p.relative_to(dist):file_hash(p) for p in dist.rglob("*") if p.is_file()}
    (build/"main.go").write_text(
        'package main\nimport("embed";"fmt";"io/fs")\n'
        '//go:embed all:frontend/dist\nvar assets embed.FS\n'
        'func main(){fs.WalkDir(assets,".",func(p string,d fs.DirEntry,e error)error{'
        'if e==nil&&!d.IsDir(){b,_:=assets.ReadFile(p);fmt.Println(p,len(b))};return e})}\n',
        encoding="utf8")
    source=base/"Original";source.mkdir()
    exe=source/"Game.exe"
    env=dict(os.environ,GOOS="windows",GOARCH="amd64",CGO_ENABLED="0",GO111MODULE="off",GOTOOLCHAIN="local")
    subprocess.run(["go","build","-trimpath","-ldflags=-s -w","-o",str(exe),"main.go"],
                   cwd=build,env=env,check=True,timeout=600)
    assert exe.stat().st_size>=600*1024*1024,"IA_WEB_EMBED_LARGE_FIXTURE_TOO_SMALL"
    shutil.rmtree(build)
    assert list(source.iterdir())==[exe],"IA_WEB_EMBED_FIXTURE_NOT_SINGLE_EXE"
    print("IA_WEB_EMBED_PE_FIXTURE_BYTES="+str(exe.stat().st_size),flush=True)
    return source,exe,expected

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--servidor",type=Path,required=True)
    p.add_argument("--auto-exe",action="store_true");a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix="IA Desktop 日本語 ") as tmp:
        base=Path(tmp)
        if a.auto_exe:
            source,exe,expected=build_embedded_fixture(base)
            selection=["--web-exe",str(exe)]
        else:
            source=base/"Extracted";source.mkdir();(source/"assets").mkdir()
            (source/"index.html").write_bytes(HTML);(source/"assets"/"main.js").write_bytes(SCRIPT)
            (source/"Game.exe").write_bytes(b"not a launcher")
            (source/"private.txt").write_bytes(b"not a resource")
            expected={Path("index.html"):file_hash(source/"index.html"),
                      Path("assets/main.js"):file_hash(source/"assets"/"main.js")}
            selection=["--web-folder",str(source)]
        originals={p.relative_to(source):file_hash(p) for p in source.rglob("*") if p.is_file()}
        subprocess.run([str(a.servidor.resolve()),*selection,"--web-copy","--web-copy-parent",str(base)],
                       check=True,timeout=600 if a.auto_exe else 180)
        copies=list(base.glob("Juego-IA-WEB-*"))
        assert len(copies)==1,"IA_WEB_DESKTOP_COPY_MISSING"
        copy=copies[0];player=copy/"Jugar-IA.exe"
        assert player.is_file() and not (copy/"IA_COPIA_WEB_INCOMPLETA.txt").exists()
        assert not (copy/"Game.exe").exists() and not (copy/"private.txt").exists()
        actual_assets={p.relative_to(copy):file_hash(p) for p in (copy/"assets").rglob("*") if p.is_file()}
        actual_assets[Path("index.html")]=file_hash(copy/"index.html")
        assert actual_assets==expected,"IA_WEB_EMBED_RESOURCE_SHA_MISMATCH"
        if a.auto_exe:
            assert not list(base.glob(".ia-web-extract-*")),"IA_WEB_EMBED_STAGING_LEFT"
            print("IA_WEB_AUTO_EXE_ALL_RESOURCES_SHA_PASS",flush=True)
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
        assert {p.relative_to(source):file_hash(p)
                for p in source.rglob("*") if p.is_file()}==originals
        print("IA_WEB_DESKTOP_COPY_SOURCE_SAVE_AND_OPUS_PASS",flush=True)
        if a.auto_exe:print("IA_WEB_AUTO_EXE_NATIVE_OPUS_ROUNDTRIP_PASS",flush=True)

if __name__=="__main__":main()
