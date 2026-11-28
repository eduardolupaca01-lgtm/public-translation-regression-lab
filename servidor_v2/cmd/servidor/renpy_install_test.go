package main

import (
 "os"
 "path/filepath"
 "testing"
 "archive/zip"
 "bytes"
 "encoding/json"
 "strings"
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
 if e=renpyInstall(exe,p);e==nil{t.Fatal("must not overwrite hook")}
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
