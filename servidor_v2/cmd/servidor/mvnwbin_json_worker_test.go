package main
import (
 "context"
 "errors"
 "os"
 "os/exec"
 "path/filepath"
 "strings"
 "syscall"
 "testing"
 "time"
)
func TestR44JSONWorkerExitFixture(t *testing.T){
 if os.Getenv("IA_R44_TEST_EXIT_FIXTURE")=="1"{os.Exit(23)}
}
func TestR44JSONWorkerFailureCodes(t *testing.T){
 folder:=t.TempDir()
 file:=filepath.Join(folder,"status.json")
 cmd:=exec.Command(os.Args[0],"-test.run=^TestR44JSONWorkerExitFixture$")
 cmd.Env=append(os.Environ(),"IA_R44_TEST_EXIT_FIXTURE=1")
 failure:=cmd.Run()
 var exit *exec.ExitError
 if !errors.As(failure,&exit)||exit.ExitCode()!=23{t.Fatalf("fixture exit: %v",failure)}
 cases:=[]struct{name,raw,want string}{
  {"missing","","IA_MV_JSON_MOTOR_SALIDA_00000017"},
  {"phase",`{"schema":"ia-traductora-startup-v1","code":"IA_MV_JSON_FASE_INFERENCIA_EN"}`,"IA_MV_JSON_MOTOR_SALIDA_00000017_INFERENCIA_EN"},
  {"terminal",`{"schema":"ia-traductora-startup-v1","code":"IA_MEMORIA_INSUFICIENTE"}`,"IA_MEMORIA_INSUFICIENTE"},
  {"wrong_schema",`{"schema":"foreign","code":"IA_FAKE_SUCCESS"}`,"IA_MV_JSON_MOTOR_SALIDA_00000017"},
  {"nonzero_after_success",`{"schema":"ia-traductora-startup-v1","code":"IA_MV_JSON_CANDIDATO_LISTO"}`,"IA_MV_JSON_MOTOR_SALIDA_00000017"},
  {"private",`{"schema":"ia-traductora-startup-v1","code":"private path"}`,"IA_MV_JSON_MOTOR_SALIDA_00000017"},
 }
 for _,c:=range cases{
  t.Run(c.name,func(t *testing.T){
   if e:=os.Remove(file);e!=nil&&!os.IsNotExist(e){t.Fatal(e)}
   if c.raw!=""{if e:=os.WriteFile(file,[]byte(c.raw),0600);e!=nil{t.Fatal(e)}}
   got:=mvJSONWorkerFailure(context.Background(),failure,file).Error()
   if got!=c.want{t.Fatalf("got %s want %s",got,c.want)}
  })
 }
 if e:=os.WriteFile(file,[]byte(`{"schema":"ia-traductora-startup-v1","code":"IA_MV_JSON_FASE_TOKENIZADORES"}`),0600);e!=nil{t.Fatal(e)}
 ctx,cancel:=context.WithDeadline(context.Background(),time.Now().Add(-time.Second));defer cancel()
 if got:=mvJSONWorkerFailure(ctx,failure,file).Error();got!="IA_MV_JSON_TIEMPO_AGOTADO_TOKENIZADORES"{t.Fatal(got)}
 denied:=&os.PathError{Op:"start",Path:"private-path-not-for-logs",Err:syscall.Errno(5)}
 if got:=mvJSONWorkerFailure(context.Background(),denied,file).Error();got!="IA_MV_JSON_MOTOR_INICIO_OS_5"||strings.Contains(got,"private"){t.Fatal(got)}
}
