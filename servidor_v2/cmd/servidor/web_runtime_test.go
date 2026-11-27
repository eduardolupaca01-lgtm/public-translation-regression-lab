package main
import("os";"path/filepath";"testing";"bytes")
func TestWebFolderPreparationPreservesExtractedAssets(t *testing.T){
 root:=filepath.Join(t.TempDir(),"Web 日本語")
 if e:=os.MkdirAll(filepath.Join(root,"assets"),0700);e!=nil{t.Fatal(e)}
 index:=[]byte("<!doctype html><html><head><script type=\"module\" src=\"/assets/main.js\"></script></head><body><div id=\"app\"></div></body></html>")
 script:=[]byte("document.querySelector('#app').textContent='Good morning.'")
 for path,data:=range map[string][]byte{"index.html":index,"assets/main.js":script}{
  if e:=os.WriteFile(filepath.Join(root,filepath.FromSlash(path)),data,0600);e!=nil{t.Fatal(e)}
 }
 pkg,e:=readPackage(fakePackage(t));if e!=nil{t.Fatal(e)};defer pkg.Close()
 for i:=0;i<2;i++{
  got,engine,e:=webPrepare(root,pkg)
  if e!=nil||got!=root||!ordinary(filepath.Join(engine,"IATraductora.exe")){t.Fatalf("web prepare: %v",e)}
 }
 for path,data:=range map[string][]byte{"index.html":index,"assets/main.js":script}{
  after,e:=os.ReadFile(filepath.Join(root,filepath.FromSlash(path)));if e!=nil||!bytes.Equal(after,data){t.Fatal("source changed")}
 }
 if e:=os.Remove(filepath.Join(root,"assets","main.js"));e!=nil{t.Fatal(e)}
 if _,e=webValidateFolder(root);e==nil{t.Fatal("missing module accepted")}
}
func TestWebFolderRejectsEscapingModule(t *testing.T){
 root:=t.TempDir()
 if e:=os.Mkdir(filepath.Join(root,"assets"),0700);e!=nil{t.Fatal(e)}
 if e:=os.WriteFile(filepath.Join(root,"outside.js"),[]byte("fixture"),0600);e!=nil{t.Fatal(e)}
 if e:=os.WriteFile(filepath.Join(root,"index.html"),[]byte("<script type='module' src='/assets/../outside.js'></script>"),0600);e!=nil{t.Fatal(e)}
 if _,e:=webValidateFolder(root);e==nil{t.Fatal("traversal accepted")}
}
