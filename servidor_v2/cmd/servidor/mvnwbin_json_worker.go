package main

// The offline worker may fail before Python starts, during a native
// inference, or after its deadline. Keep these cases distinguishable
// without logging private paths, source text, or arbitrary process output.
import (
 "context"
 "encoding/json"
 "errors"
 "fmt"
 "os"
 "os/exec"
 "path/filepath"
 "regexp"
 "strings"
 "syscall"
 "time"
)

var mvJSONDiagnosticCode=regexp.MustCompile("^IA_[A-Z0-9_]{4,90}$")
func mvJSONWorkerStatus(file string)string{
 raw,e:=mvJSONRead(file,1024)
 if e!=nil{return ""}
 var s struct{
  Schema string `json:"schema"`
  Code string `json:"code"`
 }
 if json.Unmarshal(raw,&s)!=nil||s.Schema!="ia-traductora-startup-v1"||!mvJSONDiagnosticCode.MatchString(s.Code){return ""}
 return s.Code
}

func mvJSONWorkerFailure(ctx context.Context,err error,statusFile string)error{
 status:=mvJSONWorkerStatus(statusFile)
 phase:=""
 if strings.HasPrefix(status,"IA_MV_JSON_FASE_"){
  phase="_"+strings.TrimPrefix(status,"IA_MV_JSON_FASE_")
 }
 if errors.Is(ctx.Err(),context.DeadlineExceeded){return mvJSONError("TIEMPO_AGOTADO"+phase)}
 if errors.Is(ctx.Err(),context.Canceled){return mvJSONError("MOTOR_CANCELADO"+phase)}
 var exited *exec.ExitError
 if errors.As(err,&exited)&&exited.ProcessState!=nil{
  // A terminal Python error carries a validated, nonprivate category.
  // Never turn a nonzero native exit into a successful result.
  if status!=""&&phase==""&&status!="IA_MV_JSON_CANDIDATO_LISTO"{return errors.New(status)}
  return mvJSONError(fmt.Sprintf("MOTOR_SALIDA_%08X",uint32(exited.ExitCode()))+phase)
 }
 var errno syscall.Errno
 if errors.As(err,&errno){return mvJSONError(fmt.Sprintf("MOTOR_INICIO_OS_%d",uint64(errno)))}
 return mvJSONError("MOTOR_INICIO_FALLO")
}

func mvJSONRunWorker(engine,dest,journal string)error{
 return mvJSONRunWorkerMode(engine,dest,journal,false)
}
func mvJSONRunDirectWorker(engine,dest,journal string)error{
 return mvJSONRunWorkerMode(engine,dest,journal,true)
}
func mvJSONRunWorkerMode(engine,dest,journal string,direct bool)error{
 // A private temporary directory per invocation avoids dependency on
 // the game's cwd, stale extraction directories or a shared TMP path.
 // No global environment variables, permissions, or security settings
 // are changed. The package's engine files have already been verified.
 temp,e:=os.MkdirTemp("","IA-R44-")
 if e!=nil{return mvJSONError("TEMPORAL_NO_DISPONIBLE")}
 defer os.RemoveAll(temp)
 if vxaceCloneCheckAncestors(temp)!=nil{return mvJSONError("TEMPORAL_NO_VERIFICADO")}
 statusFile:=filepath.Join(journal,"status.json")
 ctx,cancel:=context.WithTimeout(context.Background(),20*time.Minute);defer cancel()
 mode:="--mv-json-pilot"
 if direct{mode="--mv-json-direct"}
 cmd:=exec.CommandContext(ctx,filepath.Join(engine,"IATraductora.exe"),
  mode,"--game-root",dest,"--diagnostic-file",statusFile)
 cmd.Dir=engine
 cmd.Env=append(os.Environ(),"TEMP="+temp,"TMP="+temp,"TMPDIR="+temp)
 if e=cmd.Run();e!=nil{return mvJSONWorkerFailure(ctx,e,statusFile)}
 return nil
}
