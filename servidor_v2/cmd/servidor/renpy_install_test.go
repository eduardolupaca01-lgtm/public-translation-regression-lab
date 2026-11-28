package main

import (
 "os"
 "path/filepath"
 "testing"
 "archive/zip"
 "bytes"
 "encoding/json"
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
