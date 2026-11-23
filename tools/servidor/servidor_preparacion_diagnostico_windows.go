//go:build windows

package main

// Servidor's original diagnostics intentionally do not disclose private file
// paths, model payloads or user profile names. These whitelisted codes show
// WHERE preparation failed without exposing the underlying error message.
import (
 "errors"
 "os"
 "strings"
 "syscall"
)
func servidorClassifyPreparationFailure(err error)(string,string){
 if err==nil{return "TX778_COMPLETADO","Instalación comprobada."}
 // Check low-level Windows I/O errors FIRST. A phase wrapper may include
 // another stable code but the actionable device condition is more important.
 if errors.Is(err,syscall.Errno(112))||errors.Is(err,syscall.Errno(39)){
  return "TX778_UNIDAD_SIN_ESPACIO",
  "No hay suficiente espacio libre en la unidad del juego para extraer la IA. Comprueba el espacio disponible en esa unidad sin borrar cachés ni partidas."
 }
 if errors.Is(err,os.ErrPermission)||errors.Is(err,syscall.Errno(5)){
  return "TX778_ESCRITURA_DENEGADA",
  "Windows denegó acceso a un archivo o carpeta durante la preparación. Verifica que la copia del juego esté cerrada y en una carpeta donde tengas permiso de escritura."
 }
 if errors.Is(err,syscall.Errno(32))||errors.Is(err,syscall.Errno(33)){
  return "TX778_ARCHIVO_BLOQUEADO",
  "Windows informa que un archivo está en uso o bloqueado. Cierra el juego y otros instaladores; conserva los archivos existentes."
 }
 if errors.Is(err,syscall.Errno(206)){
  return "TX778_RUTA_DEMASIADO_LARGA",
  "Windows rechazó una ruta demasiado larga. Prueba una copia del juego en una ruta sencilla y corta, sin modificar el original."
 }
 code:=tx777StageCode.FindString(strings.ToUpper(err.Error()))
 switch code {
 case "TX778_CARPETA_PORTATIL_NO_DISPONIBLE":
  return code,"No se pudo crear la carpeta temporal de la IA en la unidad del juego. Comprueba los permisos de la copia y su espacio libre."
 case "TX778_CARPETA_PORTATIL_INACCESIBLE":
  return code,"No se pudo comprobar la ubicación donde estaría la IA portátil. Puede haber un conflicto de acceso o una ruta anterior."
 case "TX778_CARPETA_EXISTENTE_NO_VERIFICADA","TX778_CARPETA_EXISTENTE_SIN_PROPIETARIO","TX778_CARPETA_EXISTENTE_MODELO_INVALIDO":
  return code,"Se encontró una instalación portátil previa que no se pudo verificar de forma segura. No borres la carpeta ni los datos existentes."
 case "TX778_EXTRAER_APLICACION_FALLIDO":
  return code,"La extracción o comprobación de los archivos internos se detuvo. Comprueba el espacio libre y el acceso a archivos en la unidad del juego."
 case "TX778_INSTALAR_MOTOR_FALLIDO":
  return code,"El componente que instala y verifica el motor V95 no pudo terminar. El juego no se ha declarado traducido; comprueba que Windows permita ejecutar el instalador incluido."
 case "TX778_HUELLA_MOTOR_FALLIDA":
  return code,"No se pudo obtener la huella de integridad del ejecutable neuronal después de prepararlo."
 case "TX778_GUARDAR_MARCADOR_FALLIDO","TX778_CODIFICAR_MARCADOR_FALLIDO":
  return code,"Falló el registro de propiedad de la instalación portátil. No modifiques manualmente el marcador ni los archivos anteriores."
 case "TX778_VERIFICAR_PAQUETE_PUBLICADO_FALLIDO","TX778_VERIFICAR_PROPIETARIO_PUBLICADO_FALLIDO":
  return code,"La verificación final de la carpeta portátil falló. Se han conservado los archivos existentes para evitar pérdida de datos."
 case "TX772_OWNER_MARKER_REQUIRED":
  return code,"La carpeta portátil anterior no dispone de un marcador de propiedad válido. Servidor conserva su contenido para proteger traducciones y partidas; no la borres ni la sobrescribas."
 case "TX779_ONLY_MV_SELECTED","TX779_GAME_PORTABLE_RUNTIME_MISMATCH","TX779_LOCAL_ENGINE_NOT_FOUND":
  return code,"La selección de MV o la carpeta portátil no coinciden con el juego. Comprueba la copia cerrada y conserva el registro de instalación."
 case "TX779_ORIGINAL_V95_OWNER_WORKER_MISMATCH","TX779_ORIGINAL_V95_ENGINE_INVALID","TX779_ORIGINAL_NEURAL_WEIGHTS_INVALID":
  return code,"El componente de IA V95 no superó una verificación de integridad. Servidor no modificará archivos desconocidos ni instalará un complemento sin verificar el motor."
 case "TX779_NATIVE_MV_PLUGIN_INSTALL_FAILED","TX779_PREVIOUS_LANGUAGE_RESTORE_REFUSED","TX779_NATIVE_PLUGIN_INSTALLATION_NOT_VERIFIED":
  return code,"No se pudo verificar la instalación del complemento MV o su copia de seguridad. Conserva el respaldo y los archivos actuales del juego."
 case "TX771_PORTABLE_PUBLISH_FAILED":
  return code,"Windows rechazó publicar la carpeta preparada. Puede deberse al bloqueo del directorio o a los permisos en la unidad del juego."
 case "TX771_FOREIGN_PORTABLE_FOLDER","TX771_OWNER_MARKER_NOT_REGULAR","TX771_OWNER_MARKER_WRONG_SCHEMA":
  return code,"La carpeta portátil existente no es una instalación comprobada de Servidor. No la borres ni la sobrescribas."
 }
 if strings.HasPrefix(code,"TX541_")||strings.HasPrefix(code,"TX567_")||
    strings.HasPrefix(code,"TX771_")||strings.HasPrefix(code,"TX772_"){
  return code,"Un control interno del paquete o del motor V95 rechazó la preparación. El identificador indica el paso que debe revisarse, sin divulgar archivos privados."
 }
 if errors.Is(err,os.ErrNotExist){
  return "TX778_ARCHIVO_REQUERIDO_NO_ENCONTRADO",
  "Falta un archivo requerido durante la preparación. No borres ni reemplaces manualmente modelos o archivos del juego."
 }
 return "TX778_FALLO_SIN_CLASIFICAR",
    "La preparación no terminó y el instalador aún no pudo identificar la causa. Conserva los archivos del juego y copia este código para continuar la investigación."
}
