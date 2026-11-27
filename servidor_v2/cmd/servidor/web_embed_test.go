package main

import(
 "bytes"
 "crypto/sha256"
 "os"
 "os/exec"
 "path/filepath"
 "strings"
 "testing"
)
func webBuildEmbeddedFixture(t *testing.T) (string,map[string][]byte){
 t.Helper()
 root:=t.TempDir()
 dist:=filepath.Join(root,"frontend","dist")
 if e:=os.MkdirAll(filepath.Join(dist,"assets"),0700);e!=nil{t.Fatal(e)}
 files:=map[string][]byte{
  "index.html":[]byte("<!doctype html><html><head><script type='module' src='/assets/main.js'></script></head><body></body></html>"),
  "assets/main.js":[]byte("document.body.textContent='Good morning.'"),
  "assets/日本語.mp3":bytes.Repeat([]byte{31,42,53,64},1024*1024),
 }
 for name,data:=range files{if e:=os.WriteFile(filepath.Join(dist,filepath.FromSlash(name)),data,0600);e!=nil{t.Fatal(e)}}
 source:=[]byte("package main\nimport(\"embed\";\"fmt\";\"io/fs\")\n//go:embed all:frontend/dist\nvar assets embed.FS\nfunc main(){fs.WalkDir(assets,\".\",func(p string,d fs.DirEntry,e error)error{if e==nil&&!d.IsDir(){b,_:=assets.ReadFile(p);fmt.Println(p,len(b))};return e})}\n")
 if e:=os.WriteFile(filepath.Join(root,"main.go"),source,0600);e!=nil{t.Fatal(e)}
 exe:=filepath.Join(root,"Game.exe")
 cmd:=exec.Command("go","build","-trimpath","-ldflags=-s -w","-o",exe,"main.go")
 cmd.Dir=root
 cmd.Env=append(os.Environ(),"GOOS=windows","GOARCH=amd64","CGO_ENABLED=0","GO111MODULE=off","GOTOOLCHAIN=local")
 if out,e:=cmd.CombinedOutput();e!=nil{t.Fatalf("compile fixture: %v %s",e,out)}
 return exe,files
}
func TestWebExtractRealGoPEWithoutRunningIt(t *testing.T){
 exe,want:=webBuildEmbeddedFixture(t)
 f,e:=os.Open(exe);if e!=nil{t.Fatal(e)}
 st,e:=f.Stat();if e!=nil{f.Close();t.Fatal(e)}
 plan,e:=webFindEmbedded(f,st.Size());if e!=nil{f.Close();t.Fatal(e)}
 root:=t.TempDir()
 seen:=0
 for _,m:=range plan.members{
  if e=webExtractMember(f,root,m);e!=nil{f.Close();t.Fatal(e)}
  if m.dir{continue}
  seen++
  got,e:=os.ReadFile(filepath.Join(root,filepath.FromSlash(m.name)))
  if e!=nil||!bytes.Equal(got,want[m.name]){t.Fatalf("resource mismatch: %s",m.name)}
 }
 if e=f.Close();e!=nil{t.Fatal(e)}
 if seen!=len(want){t.Fatalf("missing resources: %d",seen)}
 if _,e=webValidateFolder(root);e!=nil{t.Fatal(e)}
 // A corrupt byte in a real embedded resource must be refused.
 data,e:=os.ReadFile(exe);if e!=nil{t.Fatal(e)}
 for _,m:=range plan.members{
  if m.name!="assets/main.js"{continue}
  data[m.off]^=1
  if e=webExtractMember(bytes.NewReader(data),t.TempDir(),m);e==nil||e.Error()!="IA_WEB_EXE_RECURSO_SHA_INVALIDO"{t.Fatalf("corrupt resource accepted: %v",e)}
 }
}
func TestWebEmbedPathAndMalformedExecutableRejection(t *testing.T){
 for _,name:=range []string{"../x","assets/../x","C:/x","assets/NUL.txt","assets/COM1.mp3","assets/x.","assets/a\\b","assets/a:b","assets/a\x00b"}{
  if webEmbedSafeName(name){t.Fatal("unsafe name accepted: "+name)}
 }
 if !webEmbedSafeName("assets/日本語.mp3"){t.Fatal("Unicode path rejected")}
 if _,e:=webFindEmbedded(bytes.NewReader(make([]byte,4096)),4096);e==nil{t.Fatal("non-PE accepted")}
 sum:=sha256.Sum256([]byte("fixture"));var want [16]byte
 for i:=range want{want[i]=^sum[i]}
 if !webEmbeddedHashMatches(sum[:],want){t.Fatal("Go 1.23 checksum mismatch")}
 want[0]^=1;if webEmbeddedHashMatches(sum[:],want){t.Fatal("corruption accepted")}
 if _,e:=webFindEmbedded(strings.NewReader("MZ"),2);e==nil{t.Fatal("short PE accepted")}
}
