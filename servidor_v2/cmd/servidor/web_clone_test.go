package main
import("os";"path/filepath";"testing")
func TestWebClonePlanOnlyIncludesFrontend(t *testing.T){
 root:=t.TempDir()
 if e:=os.Mkdir(filepath.Join(root,"assets"),0700);e!=nil{t.Fatal(e)}
 for name,data:=range map[string]string{
  "index.html":"<head><script type='module' src='/assets/main.js'></script></head>",
  "assets/main.js":"// synthetic",
  "assets/audio.mp3":"fixture",
  "Game.exe":"not copied",
  "private.txt":"not copied",
 }{if e:=os.WriteFile(filepath.Join(root,filepath.FromSlash(name)),[]byte(data),0600);e!=nil{t.Fatal(e)}}
 entries,_,e:=webClonePlan(root);if e!=nil{t.Fatal(e)}
 if len(entries)!=4{t.Fatalf("unexpected plan: %v",entries)}
 for _,entry:=range entries{if entry.rel=="Game.exe"||entry.rel=="private.txt"{t.Fatal("unrelated source copied")}}
 if e:=os.WriteFile(filepath.Join(root,"assets","bad.exe"),[]byte("fixture"),0600);e!=nil{t.Fatal(e)}
 if _,_,e=webClonePlan(root);e==nil{t.Fatal("unexpected executable admitted")}
}
