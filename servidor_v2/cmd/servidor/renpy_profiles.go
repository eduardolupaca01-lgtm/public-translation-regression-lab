package main

import (
 "archive/zip"
 _ "embed"
 "errors"
 "fmt"
 "io/fs"
 "os"
 "path/filepath"
 "regexp"
 "strconv"
 "strings"
)

//go:embed renpy_assets/releases.txt
var renpyReleases string
const renpyClassicHook="zz_ia_servidor_renpy.rpy"
const renpyClassicProfile="classic"
const renpyModernProfile="modern"

type renpyDetection struct{
 Root,GameRel,Profile,Version,Release string
 RPY,RPYC,RPA int
}
func (d renpyDetection) gameDir()string{return filepath.Join(d.Root,d.GameRel)}
func (d renpyDetection)summary()string{
 v:=d.Version;if v==""{v="no declarada; confirmar en ejecución"}
 release:="";if d.Release!=""{release=" | edición oficial="+d.Release}
 return fmt.Sprintf("IA_RENPY_DETECTADO | perfil=%s | versión=%s%s | .rpy=%d | .rpyc=%d | .rpa=%d",d.Profile,v,release,d.RPY,d.RPYC,d.RPA)
}
var renpyVersionLiteral=regexp.MustCompile("(?m)^[\\t ]*(?:version|version_only)[\\t ]*=[\\t ]*[\"'](?:Ren'Py[\\t ]+)?([4-8](?:pr[0-9]+|(?:\\.[0-9]+){0,4}[a-z]?))[\"']")
func renpyDeclaredVersion(raw []byte)string{
 m:=renpyVersionLiteral.FindSubmatch(raw);if len(m)==2{return string(m[1])};return ""
}
func renpyCatalogMatch(version string)string{
 // Exact release, optionally followed by a numeric build identifier.
 best:=""
 for _,line:=range strings.Split(renpyReleases,"\n"){
  v:=strings.TrimSpace(line);if v==""||strings.HasPrefix(v,"#"){continue}
  if v==version&&len(v)>len(best){best=v}
  if strings.HasPrefix(version,v+"."){
   suffix:=strings.TrimPrefix(version,v+".")
   // A version unknown to the catalog must not be called another release.
   // Only an explicit four/five-component internal build is eligible.
   if strings.Count(version,".")>=3&&suffix!=""&&len(suffix)>=4&&!strings.Contains(suffix,"."){
    if _,e:=strconv.ParseUint(suffix,10,64);e==nil&&len(v)>len(best){best=v}
   }
  }
 }
 return best
}
type renpyRuntimeEvidence struct{init,classic,modern bool;version string}
func (e *renpyRuntimeEvidence) observe(name string,raw []byte){
 name=strings.ToLower(strings.ReplaceAll(name,"\\","/"))
 switch name{
 case "renpy/__init__.py","renpy/__init__.pyc","renpy/__init__.pyo":
  e.init=true
 case "renpy/display/text.py","renpy/display/text.pyc","renpy/display/text.pyo":
  e.classic=true
 case "renpy/text/text.py","renpy/text/text.pyc","renpy/text/text.pyo":
  e.modern=true
 }
 if len(raw)>0&&e.version==""{e.version=renpyDeclaredVersion(raw)}
}
func renpyVersionFile(name string)bool{
 return name=="renpy/__init__.py"||name=="renpy/vc_version.py"||name=="renpy/version.py"
}
func renpyRuntimeAt(root string)(renpyRuntimeEvidence,error){
 var evidence renpyRuntimeEvidence
 for _,n:=range []string{"renpy/__init__.py","renpy/__init__.pyc","renpy/__init__.pyo","renpy/vc_version.py","renpy/version.py","renpy/display/text.py","renpy/display/text.pyc","renpy/display/text.pyo","renpy/text/text.py","renpy/text/text.pyc","renpy/text/text.pyo"}{
  p:=filepath.Join(root,filepath.FromSlash(n));if !renpyFile(p){continue}
  var raw []byte
  if renpyVersionFile(n){st,e:=os.Stat(p);if e==nil&&st.Size()<=256*1024{raw,_=os.ReadFile(p)}}
  evidence.observe(n,raw)
 }
 // Old official distributions use lib/renpy.zip or renpy.zip. Inspect
 // only named module entries; never import, unpack, or unpickle them.
 for _,n:=range []string{"renpy.zip","lib/renpy.zip","library.zip","lib/library.zip"}{
  p:=filepath.Join(root,filepath.FromSlash(n));if !renpyFile(p){continue}
  st,e:=os.Stat(p);if e!=nil||st.Size()>256*1024*1024{continue}
  z,e:=zip.OpenReader(p);if e!=nil{continue}
  if len(z.File)>50000{z.Close();return evidence,errors.New("IA_RENPY_ARCHIVO_MOTOR_EXCESIVO")}
  for _,f:=range z.File{
   name:=strings.ToLower(f.Name)
   if !strings.HasPrefix(name,"renpy/")||!safeFile(name){continue}
   var raw []byte
   if renpyVersionFile(name)&&f.UncompressedSize64<=256*1024{raw,_=readZip(f,256*1024)}
   evidence.observe(name,raw)
  }
  z.Close()
 }
 if !evidence.init{return evidence,errors.New("IA_RENPY_ESTRUCTURA_NO_RECONOCIDA")}
 return evidence,nil
}
func renpyProfile(e renpyRuntimeEvidence,root string)(string,error){
 // Capability routing beats marketing version names.
 if e.modern{return renpyModernProfile,nil}
 if e.classic{return renpyClassicProfile,nil}
 if strings.HasPrefix(e.version,"4")||strings.HasPrefix(e.version,"5"){return renpyClassicProfile,nil}
 // Preserve existing R1 recognition for loose modern packages. Version
 // remains unconfirmed until the actual runtime hook runs.
 if renpyDir(filepath.Join(root,"renpy"))&&renpyDir(filepath.Join(root,"lib")){return renpyModernProfile,nil}
 return "",errors.New("IA_RENPY_PERFIL_NO_VERIFICADO")
}
func renpyCountResources(root,rel string)(rpy,rpyc,rpa int,err error){
 base:=filepath.Join(root,rel)
 if !renpyDir(base){return}
 add:=func(n string){
  if n==renpyClassicHook||n==renpyClassicHook+"c"{return}
  switch strings.ToLower(filepath.Ext(n)){case ".rpy":rpy++;case ".rpyc":rpyc++;case ".rpa":rpa++}
 }
 if rel=="."{
  // Root-style classics: do not inventory the engine or unrelated folders.
  var entries []fs.DirEntry;entries,err=os.ReadDir(base);if err!=nil{return}
  for _,n:=range entries{if !n.IsDir(){if !vxaceCloneOrdinaryPath(filepath.Join(base,n.Name())){err=errors.New("IA_RENPY_RUTA_INSEGURA");return};add(n.Name())}}
  return
 }
 err=filepath.WalkDir(base,func(p string,n fs.DirEntry,e error)error{
  if e!=nil{return e}
  if p!=base&&n.IsDir()&&(n.Name()==renpyHook||strings.EqualFold(n.Name(),"saves")){return filepath.SkipDir}
  if !vxaceCloneOrdinaryPath(p){return errors.New("IA_RENPY_RUTA_INSEGURA")}
  if !n.IsDir(){add(n.Name())};return nil
 })
 return
}
func renpyGameRelValid(rel string)bool{
 if rel=="."{return true}
 return rel!=""&&rel!=".."&&filepath.Base(rel)==rel&&!strings.ContainsAny(rel,"/\\:\x00")&&!strings.EqualFold(rel,"renpy")&&!strings.EqualFold(rel,"lib")&&!strings.EqualFold(rel,renpySide)
}
func renpyFindGame(root,exe,profile string)(renpyDetection,error){
 d:=renpyDetection{Root:root,Profile:profile}
 stem:=strings.TrimSuffix(filepath.Base(exe),filepath.Ext(exe))
 choices:=[]string{"game",stem,"data"}
 if profile==renpyClassicProfile{choices=append(choices,".")}
 seen:=map[string]bool{};matches:=0
 for _,rel:=range choices{
  k:=strings.ToLower(rel);if seen[k]||!renpyGameRelValid(rel){continue};seen[k]=true
  a,b,c,e:=renpyCountResources(root,rel);if e!=nil{return d,e}
  if a+b+c==0{continue}
  matches++;d.GameRel=rel;d.RPY=a;d.RPYC=b;d.RPA=c
 }
 if matches==0{return d,errors.New("IA_RENPY_SIN_RECURSOS")}
 if matches!=1{return d,errors.New("IA_RENPY_CARPETA_AMBIGUA")}
 return d,nil
}
