//go:build windows

package main

import (
 "errors"
 "fmt"
 "os"
 "strings"
 "syscall"
 "testing"
)
func TestServidorPreparacionClasificaFaltaEspacio(t *testing.T){
 code,detail:=servidorClassifyPreparationFailure(
  fmt.Errorf("TX778_EXTRAER_APLICACION_FALLIDO: %w",syscall.Errno(112)))
 if code!="TX778_UNIDAD_SIN_ESPACIO"||!strings.Contains(detail,"espacio"){
  t.Fatalf("disk full must have actionable safe diagnosis: %s",code)
 }
}
func TestServidorPreparacionClasificaPermiso(t *testing.T){
 code,_:=servidorClassifyPreparationFailure(fmt.Errorf("stage: %w",os.ErrPermission))
 if code!="TX778_ESCRITURA_DENEGADA"{t.Fatal(code)}
}
func TestServidorPreparacionClasificaBloqueo(t *testing.T){
 code,_:=servidorClassifyPreparationFailure(syscall.Errno(32))
 if code!="TX778_ARCHIVO_BLOQUEADO"{t.Fatal(code)}
}
func TestServidorPreparacionClasificaFase(t *testing.T){
 tests:=[]struct{err,errorCode string}{
  {"TX778_CARPETA_PORTATIL_NO_DISPONIBLE: fallo", "TX778_CARPETA_PORTATIL_NO_DISPONIBLE"},
  {"TX778_EXTRAER_APLICACION_FALLIDO: fallo", "TX778_EXTRAER_APLICACION_FALLIDO"},
  {"TX778_INSTALAR_MOTOR_FALLIDO: fallo", "TX778_INSTALAR_MOTOR_FALLIDO"},
  {"TX771_PORTABLE_PUBLISH_FAILED: fallo", "TX771_PORTABLE_PUBLISH_FAILED"},
 }
 for _,test:=range tests{
  code,detail:=servidorClassifyPreparationFailure(errors.New(test.err))
  if code!=test.errorCode||detail==""{t.Fatalf("%q got %q %q",test.err,code,detail)}
 }
}
func TestServidorPreparacionNuncaFiltraRutaNiSecreto(t *testing.T){
 secret:="C:\\Users\\privado\\token-PRIVADO"
 for _,err:=range []error{
  errors.New("TX778_INSTALAR_MOTOR_FALLIDO: "+secret),
  errors.New("fallo sin codigo: "+secret),
  fmt.Errorf("fase: %w (%s)",syscall.Errno(112),secret),
 }{
  code,detail:=servidorClassifyPreparationFailure(err)
  if strings.Contains(code,secret)||strings.Contains(detail,secret)||strings.Contains(detail,"token-PRIVADO"){
   t.Fatalf("private diagnostic leaked content in %q",code)
  }
 }
}
