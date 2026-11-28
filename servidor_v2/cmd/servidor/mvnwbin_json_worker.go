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
 // The installed onedir worker does not extract or respawn itself.
 // Keep ordinary temporary files isolated per invocation. Never change
 // the machine's execution policy or try an alternate executable after
 // an access denial. The runtime tree has already been verified.
 temp,e:=os.MkdirTemp("","IA-R44-")
 if e!=nil{return mvJSONError("TEMPORAL_NO_DISPONIBLE")}
 defer os.RemoveAll(temp)
 if vxaceCloneCheckAncestors(temp)!=nil{return mvJSONError("TEMPORAL_NO_VERIFICADO")}
 statusFile:=filepath.Join(journal,"status.json")
 ctx,cancel:=context.WithTimeout(context.Background(),20*time.Minute);defer cancel()
 mode:="--mv-json-pilot"
 if direct{mode="--mv-json-direct"}
 exe:=filepath.Join(engine,filepath.FromSlash(mvJSONRuntimeEXE))
 if !ordinary(exe)||!vxaceCloneOrdinaryPath(exe)||vxaceCloneCheckAncestors(filepath.Dir(exe))!=nil{return mvJSONError("RUNTIME_NO_VERIFICADO")}
 cmd:=exec.CommandContext(ctx,exe,mode,"--game-root",dest,"--diagnostic-file",statusFile)
 cmd.Dir=filepath.Dir(exe)
 cmd.Env=append(os.Environ(),"TEMP="+temp,"TMP="+temp,"TMPDIR="+temp)
 mvJSONConfigureCommand(cmd)
 if e=cmd.Start();e!=nil{return mvJSONWorkerFailure(ctx,e,statusFile)}
 pid:=cmd.Process.Pid
 if e=cmd.Wait();e!=nil{return mvJSONWorkerFailure(ctx,e,statusFile)}
 if mvJSONWorkerStatus(statusFile)!="IA_MV_JSON_CANDIDATO_LISTO"{return mvJSONError("MOTOR_INFORME_NO_VERIFICADO")}
 raw,e:=mvJSONRead(filepath.Join(journal,"report.json"),8192)
 var proof struct{
  Schema string `json:"schema"`
  PID int `json:"worker_pid"`
  Mode string `json:"runtime_mode"`
 }
 // Real acceptance proves Python performed the work in the original
 // process, not in a onefile child. Do not publish on missing proof.
 if e!=nil||json.Unmarshal(raw,&proof)!=nil||proof.Schema!=mvJSONSchema||proof.PID!=pid||proof.Mode!="onedir"{return mvJSONError("RUNTIME_PROCESO_NO_VERIFICADO")}
 return nil
}
