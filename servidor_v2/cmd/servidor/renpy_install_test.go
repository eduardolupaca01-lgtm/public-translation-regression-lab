package main

import (
 "os"
 "path/filepath"
 "testing"
 "archive/zip"
 "bytes"
 "encoding/json"
 "strings"
 "syscall"
 "time"
)
func renpyFixture(t *testing.T)string{
 t.Helper();root:=t.TempDir()
 for _,n:=range []string{"game","renpy","lib"}{if e:=os.Mkdir(filepath.Join(root,n),0700);e!=nil{t.Fatal(e)}}
 for n,b:=range map[string]string{"Game.exe":"MZfixture","renpy/__init__.py":"# fixture","game/script.rpy":"label start:\n    \"Hello\"\n","game/archive.rpa":"fixture","game/scene.rpyc":"fixture"}{if e:=os.WriteFile(filepath.Join(root,filepath.FromSlash(n)),[]byte(b),0600);e!=nil{t.Fatal(e)}}
 return filepath.Join(root,"Game.exe")
}
func renpyFakePackage(t *testing.T)*packageReader{
 t.Helper();var b bytes.Buffer;z:=zip.NewWriter(&b);m:=map[string]string{}
 names:=[]string{"IATraductora.exe"}
 for _,l:=range []string{"opus_en_es","opus_ja_es"}{for _,n:=range []string{"model.bin","source.spm","target.spm","config.json"}{names=append(names,"models/"+l+"/"+n)}}
 for _,n:=range names{w,e:=z.Create(n);if e!=nil{t.Fatal(e)};data:=[]byte("test:"+n);if _,e=w.Write(data);e!=nil{t.Fatal(e)};m[n]=hash(data)}
 if e:=z.Close();e!=nil{t.Fatal(e)};r,e:=zip.NewReader(bytes.NewReader(b.Bytes()),int64(b.Len()));if e!=nil{t.Fatal(e)}
 p:=&packageReader{files:map[string]*zip.File{}};p.manifest.Files=m
 for _,f:=range r.File{p.files[f.Name]=f};return p
}
func TestRenpyDetectAndInstallRestore(t *testing.T){
 exe:=renpyFixture(t);d,e:=detectRenpy(exe);if e!=nil||d.RPY!=1||d.RPYC!=1||d.RPA!=1{t.Fatal(d,e)}
 original:=filepath.Join(d.Root,"game","script.rpy");before,_:=os.ReadFile(original)
 p:=renpyFakePackage(t);if e=renpyInstall(exe,p);e!=nil{t.Fatal(e)}
 side:=filepath.Join(d.Root,renpySide);m,e:=renpyReadReceipt(side);if e!=nil{t.Fatal(e)};if e=renpyVerifySide(side,m,m.Engine);e!=nil{t.Fatal(e)}
 // Idempotent re-install must not rewrite an already verified hook.
 if e=renpyInstall(exe,p);e!=nil{t.Fatal("verified installation",e)}
 hook:=filepath.Join(d.Root,"game",renpyHook)
 if e=os.WriteFile(filepath.Join(hook,"boot.rpyc"),[]byte("compiled"),0600);e!=nil{t.Fatal(e)}
 if e=os.WriteFile(filepath.Join(side,"memory-v1.sqlite3"),[]byte("memory fixture"),0600);e!=nil{t.Fatal(e)}
 if e=renpyRecover(exe);e!=nil{t.Fatal(e)}
 if _,e=os.Stat(hook);!os.IsNotExist(e){t.Fatal("hook remains")}
 after,_:=os.ReadFile(original);if !bytes.Equal(before,after){t.Fatal("original changed")}
 if !ordinary(filepath.Join(side,"memory-v1.sqlite3")){t.Fatal("memory lost")}
 if e=renpyInstall(exe,p);e!=nil{t.Fatal(e)}
}
func TestRenpyRefusesForeignHookAndSession(t *testing.T){
 exe:=renpyFixture(t);p:=renpyFakePackage(t);if e:=renpyInstall(exe,p);e!=nil{t.Fatal(e)}
 root:=filepath.Dir(exe);hook:=filepath.Join(root,"game",renpyHook);side:=filepath.Join(root,renpySide)
 session:=filepath.Join(side,"session-test.json");if e:=os.WriteFile(session,[]byte("{}"),0600);e!=nil{t.Fatal(e)}
 if e:=renpyRecover(exe);e==nil{t.Fatal("session ignored")};os.Remove(session)
 foreign:=filepath.Join(hook,"foreign.rpy");if e:=os.WriteFile(foreign,[]byte("unowned"),0600);e!=nil{t.Fatal(e)}
 if e:=renpyRecover(exe);e==nil||!ordinary(foreign){t.Fatal("foreign file not protected")}
}
func TestRenpyStatusAndWrongGame(t *testing.T){
 exe:=renpyFixture(t);if e:=renpyInstall(exe,renpyFakePackage(t));e!=nil{t.Fatal(e)}
 b,_:=json.Marshal(map[string]any{"schema":renpySchema,"translated":4,"cached":2,"rejected":1})
 if e:=os.WriteFile(filepath.Join(filepath.Dir(exe),renpySide,"status.json"),b,0600);e!=nil{t.Fatal(e)}
 if s,e:=renpyStatusText(exe);e!=nil||s==""{t.Fatal(s,e)}
 bad:=filepath.Join(t.TempDir(),"Game.exe");os.WriteFile(bad,[]byte("MZ"),0600)
 if _,e:=detectRenpy(bad);e==nil{t.Fatal("unknown game accepted")}
}

func TestRenpyOfficialCatalogAndExactRelease(t *testing.T){
 counts:=map[byte]int{};seen:=map[string]bool{}
 for _,line:=range strings.Split(renpyReleases,"\n"){
  v:=strings.TrimSpace(line) // Windows Git checkouts can convert embedded text to CRLF.
  if v==""||strings.HasPrefix(v,"#"){continue}
  if seen[v]{t.Fatal("duplicate",v)};seen[v]=true;counts[v[0]]++
  if renpyCatalogMatch(v)!=v{t.Fatal("missing exact release",v)}
 }
 for family,want:=range map[byte]int{'4':26,'5':36,'6':51,'7':46,'8':29}{if counts[family]!=want{t.Fatal(family,counts[family],want)}}
 if renpyCatalogMatch("6.99.14.3135")!="6.99.14"||renpyCatalogMatch("8.6.2.26112601")!="8.6.2"||renpyCatalogMatch("7.4.99")!=""{t.Fatal("build mapping")}
}
func TestRenpyClassicZipAndFlatRestore(t *testing.T){
 root:=t.TempDir();game:=filepath.Join(root,"game");lib:=filepath.Join(root,"lib")
 for _,p:=range []string{game,lib}{if e:=os.Mkdir(p,0700);e!=nil{t.Fatal(e)}}
 exe:=filepath.Join(root,"Novel.exe");if e:=os.WriteFile(exe,[]byte("MZfixture"),0600);e!=nil{t.Fatal(e)}
 original:=filepath.Join(game,"script.rpy");raw:=[]byte("label start:\n    \"Hello\"\n");if e:=os.WriteFile(original,raw,0600);e!=nil{t.Fatal(e)}
 f,e:=os.Create(filepath.Join(lib,"renpy.zip"));if e!=nil{t.Fatal(e)}
 z:=zip.NewWriter(f)
 for n,content:=range map[string]string{"renpy/__init__.py":"version = \"Ren'Py 4.8.7\"\n","renpy/display/text.pyc":"compiled fixture"}{
  w,e:=z.Create(n);if e!=nil{t.Fatal(e)};if _,e=w.Write([]byte(content));e!=nil{t.Fatal(e)}
 }
 if e=z.Close();e!=nil{t.Fatal(e)};f.Close()
 d,e:=detectRenpy(exe);if e!=nil||d.Profile!=renpyClassicProfile||d.Version!="4.8.7"||d.GameRel!="game"{t.Fatal(d,e)}
 before,e:=os.ReadFile(filepath.Join(lib,"renpy.zip"));if e!=nil{t.Fatal(e)}
 if e=renpyInstall(exe,renpyFakePackage(t));e!=nil{t.Fatal(e)}
 hook:=filepath.Join(game,renpyClassicHook);b,e:=os.ReadFile(hook);if e!=nil||!bytes.Contains(b,[]byte("init 999:\n    python hide:")){t.Fatal("classic hook",e)}
 side:=filepath.Join(root,renpySide);m,e:=renpyReadReceipt(side);if e!=nil||m.Profile!=renpyClassicProfile||m.ClassicKey==""{t.Fatal(m,e)}
 cmd,e:=renpyLaunchCommand(exe);if e!=nil{t.Fatal(e)}
 if len(cmd.Args)!=3||cmd.Args[1]!="--python"||filepath.Base(cmd.Args[2])!="classic_entry.py"||cmd.Dir!=root{t.Fatal("classic launch route",cmd.Args)}
 start:=filepath.Join(side,"classic_start.py");if e=os.WriteFile(start,[]byte("changed"),0600);e!=nil{t.Fatal(e)}
 if _,e=renpyLaunchCommand(exe);e==nil{t.Fatal("modified startup accepted")}
 if e=os.WriteFile(start,renpyClassicStart,0600);e!=nil{t.Fatal(e)}
 if e=os.WriteFile(hook+"c",[]byte("synthetic compiled"),0600);e!=nil{t.Fatal(e)}
 if e=renpyRecover(exe);e!=nil{t.Fatal(e)}
 if _,e=renpyLaunchCommand(exe);e==nil{t.Fatal("recovered hook can still launch through IA")}
 if _,e=os.Stat(hook);!os.IsNotExist(e){t.Fatal("flat hook remains")}
 if _,e=os.Stat(hook+"c");!os.IsNotExist(e){t.Fatal("compiled hook remains")}
 after,_:=os.ReadFile(original);engine,_:=os.ReadFile(filepath.Join(lib,"renpy.zip"))
 if !bytes.Equal(raw,after)||!bytes.Equal(before,engine){t.Fatal("original modified")}
}
func TestRenpyClassicAmbiguousGameDirectory(t *testing.T){
 root:=t.TempDir()
 for _,n:=range []string{"game","data"}{p:=filepath.Join(root,n);os.Mkdir(p,0700);os.WriteFile(filepath.Join(p,"script.rpy"),[]byte("fixture"),0600)}
 if _,e:=renpyFindGame(root,filepath.Join(root,"Novel.exe"),renpyClassicProfile);e==nil{t.Fatal("ambiguous layout accepted")}
}

func TestRenpyExactVersionTuple(t *testing.T){
 if v:=renpyDeclaredVersion([]byte("version_tuple = (7, 3, 2, vc_version)\n"));v!="7.3.2"{t.Fatal(v)}
}
func TestRenpyStartupDiagnosticAndNoPrivatePath(t *testing.T){
 side:=t.TempDir()
 if e:=os.WriteFile(filepath.Join(side,"client-startup.txt"),[]byte("IA_RENPY_BOOT_INICIADO\nRENPY_VERSION=7.3.2.320\nIA_RENPY_BOOT_FALLO_CARGA_CLIENTE_ImportError\nC:\\private\\game\n"),0600);e!=nil{t.Fatal(e)}
 if e:=os.WriteFile(filepath.Join(side,"worker-startup.json"),[]byte("{\"schema\":\"ia-traductora-startup-v1\",\"code\":\"IA_RENPY_MOTOR_LISTO\"}"),0600);e!=nil{t.Fatal(e)}
 s:=renpyStartupText(side)
 if !strings.Contains(s,"7.3.2.320")||!strings.Contains(s,"ImportError")||!strings.Contains(s,"IA_RENPY_MOTOR_LISTO")||strings.Contains(s,"private"){t.Fatal(s)}
 e:=renpyStageError("PUBLICAR_HOOK",&os.PathError{Op:"rename",Path:"private",Err:os.ErrPermission})
 if strings.Contains(e.Error(),"private")||!strings.HasPrefix(e.Error(),"IA_RENPY_PUBLICAR_HOOK_"){t.Fatal(e)}
}

func TestRenpyTransientPublishRetry(t *testing.T){
 root:=t.TempDir();src:=filepath.Join(root,"stage");dst:=filepath.Join(root,"final")
 if e:=os.Mkdir(src,0700);e!=nil{t.Fatal(e)}
 calls:=0
 e:=renpyMoveRetry(src,dst,func(a,b string)error{calls++;if calls<3{return &os.LinkError{Op:"rename",Old:a,New:b,Err:syscall.Errno(5)}};return os.Rename(a,b)},func(time.Duration){})
 if e!=nil||calls!=3||!renpyDir(dst){t.Fatal(e,calls)}
 // Existing destination is never replaced.
 if e=renpyMoveRetry(dst,dst,os.Rename,func(time.Duration){});e==nil{t.Fatal("overwrite accepted")}
}
func TestRenpyProgressAndFix1Receipt(t *testing.T){
 root:=t.TempDir()
 data:=[]byte("{\"schema\":\"ia-servidor-renpy-v1\",\"phase\":\"TRADUCIENDO\",\"scan_complete\":true,\"inventory\":844,\"discovered\":859,\"pending\":15,\"accepted\":844,\"updated\":100}")
 if e:=os.WriteFile(filepath.Join(root,"client-progress.json"),data,0600);e!=nil{t.Fatal(e)}
 p,ok:=renpyReadProgress(root);if !ok||!p.ScanComplete||p.Inventory!=844||p.Discovered!=859||p.Accepted!=844||p.Pending!=15{t.Fatal(p)}
 m:=renpyReceipt{Profile:renpyModernProfile,Client:"6cc0ddb46e62076329f2787886190bb58149c6fbc6b220f385cda2bde4808e59",Boot:"bbd6d7f60a19b2324ac9bb1010b7806dcc3bc3b84b73f8f7e1a848ad61b1988f"}
 if !renpyPriorModern(m){t.Fatal("Fix1 recovery rejected")}
}

func TestRenpyPreservePriorMemory(t *testing.T){
 old:=t.TempDir();stage:=t.TempDir()
 for _,name:=range []string{"memory-v1.sqlite3","memory-v1.sqlite3-wal","unrelated.txt"}{
  if e:=os.WriteFile(filepath.Join(old,name),[]byte(name),0600);e!=nil{t.Fatal(e)}
 }
 if e:=renpyPreserveMemory(old,stage);e!=nil{t.Fatal(e)}
 for _,name:=range []string{"memory-v1.sqlite3","memory-v1.sqlite3-wal"}{
  a,e:=os.ReadFile(filepath.Join(old,name));if e!=nil{t.Fatal(e)}
  b,e:=os.ReadFile(filepath.Join(stage,name));if e!=nil||!bytes.Equal(a,b){t.Fatal(name,e)}
 }
 if _,e:=os.Stat(filepath.Join(stage,"unrelated.txt"));!os.IsNotExist(e){t.Fatal("unrelated file copied")}
}
