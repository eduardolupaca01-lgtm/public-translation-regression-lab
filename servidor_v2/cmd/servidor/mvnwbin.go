package main

// Read-only recognition of a compiled MV loader. Never deserialize, evaluate,
// alter, replace or bypass the binaries or their guard. Recognize the
// original one- and two-binary layouts independently. Only the existing
// two-binary authorized add-on profile is eligible for live installation;
// other recognized layouts can use the independent JSON localization trial.
import (
 "bytes"
 "encoding/json"
 "errors"
 "io"
 "os"
 "path/filepath"
 "regexp"
 "strings"
)

const (
 mvnwbinKind = "MV (NWBin, registro adicional)"
 mvnwbinManifestMissing = "IA_MV_NWBIN_MANIFIESTO_FALTANTE"
 mvnwbinExtensionUnavailable = "IA_MV_NWBIN_EXTENSION_NO_DISPONIBLE"
 mvnwbinInvalid = "IA_MV_NWBIN_RECURSOS_NO_VERIFICADOS"
 mvnwbinOptIn = "// IA_NWBIN_ADDONS_V1"
)

var mvnwbinCore = []string{"rpg_core.js","rpg_managers.js","rpg_objects.js","rpg_scenes.js","rpg_sprites.js","rpg_windows.js"}
var mvnwbinScripts = regexp.MustCompile("(?is)<script\\b([^>]*)>(.*?)</script\\s*>")
var mvnwbinComments = regexp.MustCompile("(?s)<!--.*?-->")
var mvnwbinSrc = regexp.MustCompile("(?i)(?:^|\\s)src\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)')")
var mvnwbinCalls = regexp.MustCompile("(?i)\\.\\s*evalNWBin\\s*\\(\\s*null\\s*,[^;\\r\\n]*?[\"'](?:js[/\\\\])?(guard|plugins)\\.bin[\"'][^;\\r\\n]*?\\)\\s*;")
var mvnwbinAnyCall = regexp.MustCompile("(?i)\\bevalNWBin\\s*\\(")
var mvnwbinAsync = regexp.MustCompile("(?i)(?:^|\\s)(?:async|defer)(?:\\s|=|$)")
var mvnwbinSetup = regexp.MustCompile("(?m)^\\s*PluginManager\\.setup\\(\\s*\\$plugins\\s*\\)\\s*;\\s*$")

func mvnwbinRead(file string,limit int64)([]byte,error){
 if e:=vxaceNoSymlinkAncestors(filepath.Dir(file));e!=nil{return nil,e}
 if !ordinary(file){return nil,errors.New(mvnwbinInvalid)}
 f,e:=os.Open(file);if e!=nil{return nil,e};defer f.Close()
 raw,e:=io.ReadAll(io.LimitReader(f,limit+1))
 if e!=nil||len(raw)==0||int64(len(raw))>limit{return nil,errors.New(mvnwbinInvalid)}
 return bytes.TrimPrefix(raw,[]byte{0xef,0xbb,0xbf}),nil
}

func mvnwbinMarker(file string)bool{
 _,e:=os.Lstat(file)
 return !os.IsNotExist(e)
}

func mvnwbinRegular(file string,max int64)bool{
 if !ordinary(file)||!vxaceCloneOrdinaryPath(file){return false}
 s,e:=os.Stat(file);return e==nil&&s.Size()>0&&s.Size()<=max
}

// These checks identify the narrow observed layout, not authenticity or
// permission. They are intentionally not a JavaScript parser/decompiler.
func mvnwbinProfile(root,content string)(bool,error){
 js:=filepath.Join(content,"js")
 data:=filepath.Join(content,"data")
 guard:=filepath.Join(js,"guard.bin")
 plugins:=filepath.Join(js,"plugins.bin")
 if !mvnwbinMarker(filepath.Join(js,"rpg_core.js"))||
    (!mvnwbinMarker(guard)&&!mvnwbinMarker(plugins)){return false,nil}
 invalid:=errors.New(mvnwbinInvalid)
 if mvnwbinMarker(filepath.Join(js,"rmmz_core.js")){return true,errors.New("IA_RPG_RUTAS_AMBIGUAS")}
 for _,dir:=range []string{root,content,js,data,filepath.Join(js,"plugins")}{
  if e:=vxaceNoSymlinkAncestors(dir);e!=nil{return true,invalid}
  s,e:=os.Lstat(dir);if e!=nil||!s.IsDir()||s.Mode()&os.ModeSymlink!=0{return true,invalid}
 }
 for _,name:=range append(append([]string{},mvnwbinCore...),"main.js"){
  if !mvnwbinRegular(filepath.Join(js,name),8*1024*1024){return true,invalid}
 }
 // The binary registry must exist in either profile. A guard may be
 // absent only if the ORIGINAL startup has no active guard call. If
 // the original still contains a guard file, require an ordinary file
 // and preserve it even when the loader does not reference it.
 // Do not read or execute opaque binaries at detection time.
 if !mvnwbinRegular(plugins,64*1024*1024){return true,invalid}
 if mvnwbinMarker(guard)&&!mvnwbinRegular(guard,64*1024*1024){return true,invalid}
 for _,name:=range []string{"System.json","Actors.json","CommonEvents.json","MapInfos.json"}{
  raw,e:=mvnwbinRead(filepath.Join(data,name),16*1024*1024)
  if e!=nil||!json.Valid(raw){return true,invalid}
  raw=bytes.TrimSpace(raw)
  if name=="System.json"&&raw[0]!='{'||name!="System.json"&&raw[0]!='['{return true,invalid}
 }
 html,e:=mvnwbinRead(filepath.Join(content,"index.html"),256*1024)
 if e!=nil{return true,invalid}
 htmlText:=mvnwbinComments.ReplaceAllString(string(html),"")
 pos:=map[string]int{}
 guardAt,pluginsAt,calls:=0,0,0
 tags:=mvnwbinScripts.FindAllStringSubmatch(htmlText,-1)
 if len(tags)==0||len(tags)>128{return true,invalid}
 for i,tag:=range tags{
  attrs,body:=tag[1],tag[2]
  at:=i+1
  matches:=mvnwbinSrc.FindAllStringSubmatch(attrs,-1)
  if len(matches)>1{return true,invalid}
  if len(matches)==1{
   src:=matches[0][1];if src==""{src=matches[0][2]}
   if pos[src]!=0||mvnwbinAsync.MatchString(attrs){return true,invalid}
   pos[src]=at
  }else{
   if mvnwbinAnyCall.MatchString(body){
    found:=mvnwbinCalls.FindAllStringSubmatch(body,-1)
    if len(found)!=len(mvnwbinAnyCall.FindAllStringIndex(body,-1)){return true,invalid}
    for _,call:=range found{
     calls++
     ordinal:=at*100+calls
     switch strings.ToLower(call[1]){
     case "guard":if guardAt!=0{return true,invalid};guardAt=ordinal
     case "plugins":if pluginsAt!=0{return true,invalid};pluginsAt=ordinal
     }
    }
   }
  }
 }
 // A single compiled registry is a separate deployment layout, not a
 // missing guard in the original two-call layout. Closed HTML comments
 // were removed before scanning; never change the input HTML.
 if pluginsAt==0||pos["js/main.js"]*100<=pluginsAt{return true,invalid}
 firstBinAt:=pluginsAt
 if guardAt!=0{
  if calls!=2||pluginsAt<=guardAt||!mvnwbinRegular(guard,64*1024*1024){return true,invalid}
  firstBinAt=guardAt
 }else if calls!=1{return true,invalid}
 last:=0
 for _,name:=range mvnwbinCore{
  at:=pos["js/"+name]
  if at<=last||at*100>=firstBinAt{return true,invalid}
  last=at
 }

 manifest:=filepath.Join(root,"package.json")
 if _,e:=os.Lstat(manifest);os.IsNotExist(e){return true,errors.New(mvnwbinManifestMissing)}
 raw,e:=mvnwbinRead(manifest,128*1024)
 if e!=nil{return true,invalid}
 var desc struct{
  Main string `json:"main"`
  Name string `json:"name"`
  Node *bool `json:"nodejs"`
 }
 if json.Unmarshal(raw,&desc)!=nil||desc.Node!=nil&&!*desc.Node{return true,invalid}
 // Some deployed games leave the application name empty. That is not
 // evidence of a different engine. Diagnose a missing extension first;
 // keep the nonempty-name requirement for the installable lab profile.
 want:="index.html"
 if !strings.EqualFold(root,content){want="www/index.html"}
 if strings.TrimPrefix(desc.Main,"./")!=want{return true,invalid}

 // A single-binary deployment is recognized for the offline JSON trial
 // only. The mere presence of plugins.js is not an authorized live
 // extension and does not override an active compiled registry.
 if guardAt==0{return true,errors.New(mvnwbinExtensionUnavailable)}
 // No file is created to satisfy this condition. The original index must
 // already load the independent plaintext registry after both binaries.
 at:=pos["js/plugins.js"]
 if at*100<=pluginsAt||at>=pos["js/main.js"]{return true,errors.New(mvnwbinExtensionUnavailable)}
 if strings.TrimSpace(desc.Name)==""{return true,invalid}
 registry,e:=mvnwbinRead(filepath.Join(js,"plugins.js"),4*1024*1024)
 if e!=nil{return true,errors.New(mvnwbinExtensionUnavailable)}
 first:=strings.SplitN(string(registry),"\n",2)[0]
 if strings.TrimSuffix(first,"\r")!=mvnwbinOptIn{return true,errors.New(mvnwbinExtensionUnavailable)}
 if _,_,e=parseRegistry(registry);e!=nil{return true,invalid}
 boot,e:=mvnwbinRead(filepath.Join(js,"main.js"),1024*1024)
 if e!=nil||!mvnwbinSetup.Match(boot){return true,errors.New(mvnwbinExtensionUnavailable)}
 return true,nil
}

func mvnwbinGate(root string)error{
 dirs:=[]string{filepath.Join(root,"www"),root}
 count:=0
 selected:=""
 var failure error
 for _,dir:=range dirs{
  if matched,e:=mvnwbinProfile(root,dir);matched{
   count++;selected=dir;failure=e
  }
 }
 if count==0{return nil}
 if count!=1{return errors.New("IA_RPG_RUTAS_AMBIGUAS")}
 for _,dir:=range dirs{
  if dir!=selected&&engineAt(dir)!=""{return errors.New("IA_RPG_RUTAS_AMBIGUAS")}
 }
 return failure
}
