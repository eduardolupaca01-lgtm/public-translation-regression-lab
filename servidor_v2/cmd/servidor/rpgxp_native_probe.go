package main

import (
 "context"
 _ "embed"
 "encoding/json"
 "errors"
 "flag"
 "fmt"
 "io"
 "net/http"
 "os"
 "os/exec"
 "path/filepath"
 "runtime"
 "strconv"
 "strings"
 "time"
)

//go:embed xp_native/window.rb
var xpNativeWindow []byte

//go:embed xp_native/main.rb
var xpNativeMain []byte

// The selected genuine, trusted XP executable and runtime are copied locally.
// No scripts/assets/saves from the selected game are copied or executed.
func xpNativePrepare(source,dir string)(map[string]string,error){
 root,target,e:=xpTarget(source)
 if e!=nil{return nil,e}
 if e=vxaceNoSymlinkAncestors(dir);e!=nil{return nil,e}
 abs,e:=filepath.Abs(dir);if e!=nil{return nil,e}
 rel,e:=filepath.Rel(root,abs);if e==nil && (rel=="." || (rel!=".." && !strings.HasPrefix(rel,".."+string(filepath.Separator)))){return nil,xpError("PROBE_DENTRO_DEL_JUEGO")}
 entries,e:=os.ReadDir(dir);if e!=nil||len(entries)!=0{return nil,xpError("PROBE_DIRECTORIO_NO_VACIO")}
 ini,e:=vxaceOrdinaryChild(root,"Game.ini",64*1024);if e!=nil{return nil,e}
 iniRaw,e:=xpRead(ini,64*1024);if e!=nil{return nil,e}
 values,e:=vxaceParseGameINI(iniRaw);if e!=nil{return nil,e}
 lib:=strings.TrimPrefix(strings.ReplaceAll(values["library"],"\\","/"),"./")
 parts:=strings.Split(lib,"/")
 libDir:=root
 if len(parts)==2 && strings.EqualFold(parts[0],"System"){
  libDir,e=vxaceDirectoryChild(root,"System");if e!=nil{return nil,e}
 }else if len(parts)!=1{return nil,xpError("PROBE_RUNTIME_INVALIDO")}
 name:=parts[len(parts)-1]
 if !rpgxpLibrary.MatchString(name){return nil,xpError("PROBE_RUNTIME_INVALIDO")}
 dll,e:=vxaceOrdinaryChild(libDir,name,64*1024*1024);if e!=nil{return nil,e}
 exe,e:=filepath.Abs(source);if e!=nil{return nil,e}
 originals:=map[string]string{}
 for _,path:=range []string{exe,dll,ini,target}{
  sum,e:=digestFile(path);if e!=nil{return nil,e};originals[path]=sum
 }
 for _,item:=range []struct{src,dst string}{{exe,"Game.exe"},{dll,name}}{
  b,e:=xpRead(item.src,64*1024*1024);if e!=nil{return nil,e}
  if hash(b)!=originals[item.src]{return nil,xpError("PROBE_ORIGEN_MODIFICADO")}
  if e=createNew(filepath.Join(dir,item.dst),b);e!=nil{return nil,e}
 }
 config:="[Game]\r\nLibrary="+name+"\r\nScripts=Data\\Scripts.rxdata\r\nTitle=IA RGSS1 Native Probe\r\nRTP1=\r\nRTP2=\r\nRTP3=\r\n"
 if e=createNew(filepath.Join(dir,"Game.ini"),[]byte(config));e!=nil{return nil,e}
 data:=filepath.Join(dir,"Data")
 if e=os.Mkdir(data,0700);e!=nil{return nil,e}
 w,e:=xpCompress(xpNativeWindow);if e!=nil{return nil,e}
 m,e:=xpCompress(xpNativeMain);if e!=nil{return nil,e}
 archive,e:=xpEncodeRows([][]byte{xpEncodeRow(1,[]byte("Window_Message"),w),xpEncodeRow(2,[]byte("Main"),m)})
 if e!=nil{return nil,e}
 if _,e=xpParseScripts(archive);e!=nil{return nil,e}
 if e=createNew(filepath.Join(data,"Scripts.rxdata"),archive);e!=nil{return nil,e}
 for _,name:=range []string{"System.rxdata","MapInfos.rxdata"}{
  if e=createNew(filepath.Join(data,name),[]byte{4,8,'[',0});e!=nil{return nil,e}
 }
 return originals,nil
}

func xpNativeStatus(engine string,parent,want int)error{
 folder:=filepath.Dir(engine)
 raw,e:=xpRead(filepath.Join(folder,"rpgxp-session.txt"),512);if e!=nil{return e}
 session:=strings.Split(strings.TrimSpace(string(raw)),"\n")
 if len(session)!=4||session[0]!="IA-RPGXP-SESSION-1"||!xpSHA(session[1])||session[3]!=strconv.Itoa(parent){return xpError("PROBE_SESION_INVALIDA")}
 b,e:=xpRead(filepath.Join(folder,"bridge.json"),4096);if e!=nil{return e}
 var bridge struct{Schema,Token string;Port,Pid int}
 if json.Unmarshal(b,&bridge)!=nil||bridge.Schema!="ia-traductora-bridge-v1"||bridge.Token!=session[1]||bridge.Port<1||bridge.Port>65535||strconv.Itoa(bridge.Pid)!=session[2]{return xpError("PROBE_PUENTE_INVALIDO")}
 client:=&http.Client{Timeout:5*time.Second,Transport:&http.Transport{Proxy:nil,DisableKeepAlives:true},CheckRedirect:func(*http.Request,[]*http.Request)error{return errors.New("redirect")}}
 req,e:=http.NewRequest("GET","http://127.0.0.1:"+strconv.Itoa(bridge.Port)+"/status",nil);if e!=nil{return e}
 req.Header.Set("X-IA-Token",bridge.Token)
 res,e:=client.Do(req);if e!=nil{return xpError("PROBE_ESTADO_INACCESIBLE")};defer res.Body.Close()
 raw,e=io.ReadAll(io.LimitReader(res.Body,4097))
 var status struct{Schema string;Active bool;Translated *int;Failed *int}
 if e!=nil||len(raw)>4096||res.StatusCode!=200||json.Unmarshal(raw,&status)!=nil||status.Schema!=bridge.Schema||!status.Active||status.Translated==nil||status.Failed==nil||*status.Translated!=want||*status.Failed!=0{
  return xpError("PROBE_CONTADORES_INVALIDOS")
 }
 return nil
}

func xpNativeClosed(engine,journal string)error{
 deadline:=time.Now().Add(90*time.Second)
 for time.Now().Before(deadline){
  closed:=true
  for _,p:=range []string{filepath.Join(filepath.Dir(engine),"rpgxp-session.txt"),filepath.Join(filepath.Dir(engine),"bridge.json"),filepath.Join(journal,"operation.lock")}{
   if _,e:=os.Lstat(p);!os.IsNotExist(e){closed=false}
  }
  if closed{return nil}
  time.Sleep(200*time.Millisecond)
 }
 return xpError("PROBE_CIERRE_WORKER")
}

func xpNativeRun(dir,engine,journal string,want int)error{
 for _,name:=range []string{"xp-native-result.txt","xp-native-result.tmp","xp-native-ack.txt"}{
  p:=filepath.Join(dir,name)
  if _,e:=os.Lstat(p);e==nil{
   if !ordinary(p){return xpError("PROBE_MARCADOR_INVALIDO")}
   if e=os.Remove(p);e!=nil{return e}
  }else if !os.IsNotExist(e){return e}
 }
 if e:=xpNativeClosed(engine,journal);e!=nil{return e}
 ctx,cancel:=context.WithTimeout(context.Background(),150*time.Second);defer cancel()
 cmd:=exec.CommandContext(ctx,filepath.Join(dir,"Game.exe"))
 cmd.Dir=dir
 if e:=cmd.Start();e!=nil{return xpError("PROBE_ARRANQUE")}
 done:=make(chan error,1);go func(){done<-cmd.Wait()}()
 // The helper belongs to this isolated copy, not any running game of the user.
 ticker:=time.NewTicker(100*time.Millisecond);defer ticker.Stop()
 marker:=filepath.Join(dir,"xp-native-result.txt")
 acknowledged:=false
 var checkErr error
 for {
  select{
  case e:=<-done:
   if checkErr!=nil{return checkErr}
   if e!=nil||!acknowledged{return xpError("PROBE_RUNTIME_SIN_CONFIRMACION")}
   return xpNativeClosed(engine,journal)
  case <-ctx.Done():
   <-done
   return xpError("PROBE_TIMEOUT")
  case <-ticker.C:
   if acknowledged{continue}
   if _,e:=os.Lstat(marker);os.IsNotExist(e){continue}
   raw,e:=xpRead(marker,128)
   if e!=nil||strings.TrimSpace(string(raw))!="IA_RPGXP_NATIVE_PAINT_PASS"{
    checkErr=xpError("PROBE_RUNTIME_FALLO")
    if e==nil{
     for _,phase:=range []string{"RUNTIME","SESSION","TRANSLATE","PAINT"}{
      if strings.TrimSpace(string(raw))=="IA_RPGXP_NATIVE_"+phase+"_FAIL"{checkErr=xpError("PROBE_"+phase+"_FAIL")}
     }
    }
   }else{
    checkErr=xpNativeStatus(engine,cmd.Process.Pid,want)
   }
   if checkErr==nil{checkErr=createNew(filepath.Join(dir,"xp-native-ack.txt"),[]byte("ok\n"))}
   if checkErr!=nil{cancel();<-done;return checkErr}
   acknowledged=true
  }
 }
}

func xpNativeProbe(source string,pkg *packageReader)error{
 if runtime.GOOS!="windows"{return xpError("PROBE_SOLO_WINDOWS")}
 dir,e:=os.MkdirTemp("","ia-xp-native-");if e!=nil{return e}
 _,engine,journal,_,_:=xpPaths(dir)
 // On failures leave the diagnostic copy in place if the worker cannot
 // shut down; do not force-remove a live SQLite database or user files.
 clean:=false
 defer func(){if !clean{fmt.Fprintln(os.Stderr,"IA_RPGXP_PROBE_TEMPORAL_CONSERVADO")}}()
 originals,e:=xpNativePrepare(source,dir);if e!=nil{return e}
 exe:=filepath.Join(dir,"Game.exe")
 script:=filepath.Join(dir,"Data","Scripts.rxdata")
 before,e:=digestFile(script);if e!=nil{return e}
 if e=xpInstallLab(exe,pkg);e!=nil{return e}
 for _,want:=range []int{3,0}{
  if e=xpNativeRun(dir,engine,journal,want);e!=nil{return e}
 }
 if e=xpRecoverLab(exe);e!=nil{return e}
 if after,e:=digestFile(script);e!=nil||after!=before{return xpError("PROBE_RESTAURACION")}
 for file,sum:=range originals{
  if after,e:=digestFile(file);e!=nil||after!=sum{return xpError("PROBE_ORIGINAL_MODIFICADO")}
 }
 if !ordinary(filepath.Join(filepath.Dir(engine),"cache","translation-memory-v2.sqlite3")){return xpError("PROBE_CACHE_AUSENTE")}
 if e=xpNativeClosed(engine,journal);e!=nil{return e}
 if e=os.RemoveAll(dir);e!=nil{return e}
 clean=true
 fmt.Println("IA_RPGXP_NATIVE_RGSS1_OPUS_CACHE_RESTORE_PASS")
 return nil
}

func xpNativeCommand(game,payload string)error{
 if flag.NArg()!=0||game==""{return xpError("PROBE_ARGUMENTOS_INVALIDOS")}
 valid:=true
 flag.Visit(func(f *flag.Flag){if f.Name!="xp-native-probe"&&f.Name!="game"&&f.Name!="package"{valid=false}})
 if !valid{return xpError("PROBE_ARGUMENTOS_INVALIDOS")}
 if payload==""{var e error;payload,e=os.Executable();if e!=nil{return e}}
 pkg,e:=readPackage(payload);if e!=nil{return e};defer pkg.Close()
 return xpNativeProbe(game,pkg)
}
