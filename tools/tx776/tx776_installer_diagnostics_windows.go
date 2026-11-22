//go:build windows

// TX776: shareable, safe installer diagnostics. This file is injected into
// ONLY a disposable SHA-pinned checkout of the genuine Windows V95 installer.
package main

import (
    "errors"
    "fmt"
    "regexp"
    "strings"
    "time"
)

// The installer owns the game's model and cache; diagnostics are ephemeral
// in the GUI, NOT a global Windows log or a user-profile database.
type tx776Stage struct { Code, Text string }
var tx776Events=make(chan tx776Stage,128)
const tx776MaximumReport=48*1024
var tx776CodePattern=regexp.MustCompile(`^[A-Z0-9_]{3,110}$`)
var tx776ErrorPattern=regexp.MustCompile(`TX[0-9]{3}_[A-Z0-9_]+`)

func tx776StageEvent(code,message string){
    if !tx776CodePattern.MatchString(code){return}
    // Never pass paths, file contents, tokens, or stderr to this channel.
    select {case tx776Events<-tx776Stage{code,message}:default:}
}

func tx776DrainEvents(){
    for{
        select{
        case ev:=<-tx776Events: tx776Append(ev.Code,ev.Text)
        default: return
        }
    }
}
func tx776StartReport(){
    for {
        select {case <-tx776Events: default: goto drained}
    }
drained:
    rpgStatus("TENSHIXGAME RPG — DIAGNÓSTICO DE INSTALACIÓN\r\n" +
        "Sesión local: "+time.Now().UTC().Format("2006-01-02T15:04:05Z")+"\r\n"+
        "No se envía información por Internet. El diagnóstico no incluye rutas personales, claves ni textos del juego.")
}

// Only the Win32 UI thread may call tx776Append/tx776DrainEvents.
func tx776Append(code,message string){
    if !tx776CodePattern.MatchString(code){code="TX776_EVENTO"}
    // Only static, locally authored explanations. If an exception contains
    // sensitive locations, its raw text NEVER enters the copied report.
    sanitized:=strings.NewReplacer("\r"," ","\n"," ").Replace(message)
    if len(sanitized)>360{sanitized=sanitized[:360]}
    line:=fmt.Sprintf("\r\n[%s] %s",code,sanitized)
    existing:=rpgState.lastMessage
    if len(existing)+len(line)>tx776MaximumReport{
        lines:=strings.Split(existing,"\r\n")
        for len(lines)>1 && len(strings.Join(lines,"\r\n"))+len(line)>tx776MaximumReport{
            lines=lines[1:]
        }
        existing="[TX776] Se conservaron los eventos más recientes; el historial superó su límite seguro.\r\n"+strings.Join(lines,"\r\n")
    }
    rpgStatus(existing+line)
}

func tx776ExplainError(err error)(string,string){
    if err==nil{return "TX776_OK","Instalación completada."}
    detail:=strings.ToUpper(err.Error())
    codes:=tx776ErrorPattern.FindAllString(detail,10)
    code:="TX776_ERROR_NO_CLASIFICADO"
    if len(codes)>0{
        // First code identifies the public stage that failed; a nested code
        // may be the more specific cause. Display both when available.
        code=codes[0]
        if len(codes)>1 && codes[len(codes)-1]!=code{
            code=code+" / "+codes[len(codes)-1]
        }
    } else if strings.Contains(detail,"ACCESS DENIED")||strings.Contains(detail,"ACCESO DENEGADO")||
        strings.Contains(detail,"PERMISSION DENIED") {
        code="TX776_SIN_PERMISOS"
    }else if strings.Contains(detail,"NOT ENOUGH SPACE")||strings.Contains(detail,"DISK FULL")||
        strings.Contains(detail,"ESPACIO INSUFICIENTE"){
        code="TX776_ESPACIO_INSUFICIENTE"
    }else if strings.Contains(detail,"NO SUCH FILE")||strings.Contains(detail,"FILE NOT FOUND")||
        strings.Contains(detail,"NO SE ENCUENTRA EL ARCHIVO"){
        code="TX776_ARCHIVO_NO_ENCONTRADO"
    }
    switch {
    case strings.Contains(detail,"FOREIGN_OR_PARTIAL_SIDECAR"),strings.Contains(detail,"OWNER_MARKER"),
        strings.Contains(detail,"SOURCE_MISMATCH"),strings.Contains(detail,"JOURNAL_OR_SOURCE_MISMATCH"):
        return code,"Se detectó una instalación previa o carpeta sin propiedad/integridad demostrada. No borres el diario, los respaldos, plugins.js ni la caché. Conserva la copia y comparte este código."
    case strings.Contains(detail,"NEURAL_WEIGHTS"),strings.Contains(detail,"MODELS_INVALID"),
        strings.Contains(detail,"ENGINE_INVALID"),strings.Contains(detail,"WORKER_MARKER_MISMATCH"):
        return code,"Los pesos o el motor V95 no superaron la verificación. No uses otra IA, no renombres modelos ni fuerces la instalación; comparte el código."
    case strings.Contains(detail,"NOT_VERIFIED"),strings.Contains(detail,"ONLY_DETECTION"):
        return code,"El motor o la variante del juego no cuenta con un adaptador de instalación certificado. No se debe forzar un complemento de otro motor."
    case strings.Contains(detail,"TX589_HISTORIC_TX203_PLUGIN_PRESENT"):
        return code,"Hay un complemento antiguo incompatible. Guarda el juego y restaura esa instalación con su herramienta original antes de actualizar."
    case strings.Contains(detail,"JOURNAL"),strings.Contains(detail,"BACKUP"),strings.Contains(detail,"RESTORE"):
        return code,"No se pudo verificar el diario o recuperar el respaldo anterior. Conserva ambos sin modificarlos y comparte este código."
    case strings.Contains(detail,"ACCESS DENIED"),strings.Contains(detail,"PERMISSION DENIED"),
        strings.Contains(detail,"ACCESO DENEGADO"):
        return code,"Windows denegó el acceso. Cierra el juego, verifica permisos de la copia y evita carpetas protegidas."
    case strings.Contains(detail,"NOT ENOUGH SPACE"),strings.Contains(detail,"DISK FULL"),
        strings.Contains(detail,"ESPACIO INSUFICIENTE"):
        return code,"No hay suficiente espacio en la unidad de la COPIA del juego para instalar los modelos y conservar respaldos."
    default:
        return code,"La instalación se detuvo. Conserva los archivos existentes y envía este informe. El error original pudo incluir rutas o tokens que no se copian."
    }
}

func tx776CopyReport(){
    if rpgState.statusBox==0{return}
    // Read-only Win32 EDIT supports normal selection and WM_COPY; no file
    // outside the game is created. Clipboard changes only on user click.
    const emSetSel=0x00B1
    const wmCopy=0x0301
    rpgSendMessage.Call(rpgState.statusBox,emSetSel,0,^uintptr(0))
    rpgSendMessage.Call(rpgState.statusBox,wmCopy,0,0)
    rpgSendMessage.Call(rpgState.statusBox,emSetSel,^uintptr(0),^uintptr(0))
}

// Tiny stable regression utility. Avoid printing Go errors, which may embed
// local paths, authentication tokens or private filenames.
func tx776DiagnosticForTest(errText string)(string,string){
    return tx776ExplainError(errors.New(errText))
}
