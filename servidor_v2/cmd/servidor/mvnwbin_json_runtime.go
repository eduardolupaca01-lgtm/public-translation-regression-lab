package main

// The optional, ordinary one-folder Python distribution is bundled inside
// the single Servidor package and installed only for the offline JSON mode.
// It is selected before any launch, never as a fallback after an OS denial.
// The usual Windows execution policies and file permissions still apply.
import (
 "archive/zip"
 "io/fs"
 "os"
 "path/filepath"
 "strings"
)

const mvJSONRuntimeEXE="json-runtime/IATraductora.exe"
var mvJSONRequiredRuntime=[]string{
 mvJSONRuntimeEXE,
 "json-runtime/_internal/python311.dll",
 "json-runtime/_internal/base_library.zip",
}

func mvJSONRuntimeName(name string)bool{
 if len(name)>200||!safeFile(name){return false}
 if name!=mvJSONRuntimeEXE&&!strings.HasPrefix(name,"json-runtime/_internal/"){return false}
 for _,part:=range strings.Split(name,"/"){
  if part==""||strings.HasSuffix(part,".")||strings.HasSuffix(part," "){return false}
  for _,c:=range part{
   if !(c>='a'&&c<='z'||c>='A'&&c<='Z'||c>='0'&&c<='9'||strings.ContainsRune("_.-+ @()",c)){return false}
  }
  stem:=strings.ToUpper(strings.SplitN(part,".",2)[0])
  if stem=="CON"||stem=="PRN"||stem=="AUX"||stem=="NUL"||
    len(stem)==4&&(strings.HasPrefix(stem,"COM")||strings.HasPrefix(stem,"LPT"))&&stem[3]>='0'&&stem[3]<='9'{return false}
 }
 return true
}

// Legacy installers and their receipts still see precisely the original
// file set. JSON gets its own view of the same verified archive.
func mvJSONPackageForOffline(pkg *packageReader)(*packageReader,error){
 if pkg==nil||len(pkg.jsonFiles)==0||len(pkg.jsonFiles)!=len(pkg.jsonSHA){return nil,mvJSONError("RUNTIME_PAQUETE_INCOMPLETO")}
 for _,name:=range mvJSONRequiredRuntime{if pkg.jsonFiles[name]==nil{return nil,mvJSONError("RUNTIME_PAQUETE_INCOMPLETO")}}
 result:=*pkg
 result.files=map[string]*zip.File{}
 result.manifest.Files=map[string]string{}
 for name,f:=range pkg.files{result.files[name]=f}
 for name,h:=range pkg.manifest.Files{result.manifest.Files[name]=h}
 for name,f:=range pkg.jsonFiles{
  if !mvJSONRuntimeName(name)||f==nil||!xpSHA(pkg.jsonSHA[name])||result.files[name]!=nil{return nil,mvJSONError("RUNTIME_PAQUETE_INVALIDO")}
  result.files[name]=f;result.manifest.Files[name]=pkg.jsonSHA[name]
 }
 return &result,nil
}

func mvJSONVerifyRuntime(engine string,pkg *packageReader)error{
 bad:=mvJSONError("RUNTIME_NO_VERIFICADO")
 if pkg==nil||len(pkg.jsonSHA)==0{return bad}
 root:=filepath.Join(engine,"json-runtime")
 if vxaceCloneCheckAncestors(root)!=nil{return bad}
 count:=0
 e:=filepath.WalkDir(root,func(path string,d fs.DirEntry,walkErr error)error{
  if walkErr!=nil||d==nil||!vxaceCloneOrdinaryPath(path)||d.Type()&os.ModeSymlink!=0{return bad}
  if d.IsDir(){return nil}
  rel,e:=filepath.Rel(engine,path);if e!=nil{return bad}
  name:=filepath.ToSlash(rel)
  want,ok:=pkg.jsonSHA[name]
  if !ok||!mvJSONRuntimeName(name)||!ordinary(path)||xpHashFile(path,want)!=nil{return bad}
  count++
  return nil
 })
 if e!=nil||count!=len(pkg.jsonSHA){return bad}
 return nil
}
