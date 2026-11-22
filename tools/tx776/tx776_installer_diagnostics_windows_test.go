//go:build windows
package main
import ("errors";"strings";"testing")

func TestTX776RecoverableFailureCodesNeverExposeSensitivePaths(t *testing.T){
    cases:=[]struct{input,expected string}{
        {"TX771_PORTABLE_FOREIGN_OR_PARTIAL_SIDECAR: C:\\Users\\private\\token_ABC","TX771_PORTABLE_FOREIGN_OR_PARTIAL_SIDECAR"},
        {"TX583_ORIGINAL_NEURAL_WEIGHTS_INVALID: D:\\MyGame\\private.bin","TX583_ORIGINAL_NEURAL_WEIGHTS_INVALID"},
        {"TX583_OLD_PLUGIN_RESTORE_FAILED: TX395_JOURNAL_OR_SOURCE_MISMATCH","TX395_JOURNAL_OR_SOURCE_MISMATCH"},
        {"Access denied: C:\\Users\\Somebody\\Private","TX776_SIN_PERMISOS"},
        {"disk full: D:\\Game","TX776_ESPACIO_INSUFICIENTE"},
        {"error con token secreta abc123","TX776_ERROR_NO_CLASIFICADO"},
    }
    for _,check:=range cases{
        code,advice:=tx776DiagnosticForTest(check.input)
        if !strings.Contains(code,check.expected) {
            t.Fatalf("lost useful stage code: got %q expected %q",code,check.expected)
        }
        report:=code+" "+advice
        for _,leak:=range []string{"C:\\Users\\","D:\\MyGame","abc123","token_ABC"} {
            if strings.Contains(report,leak) { t.Fatalf("private path/text leaked in diagnosis for %s",code) }
        }
        if strings.TrimSpace(advice)==""{t.Fatal("explanation missing")}
    }
}
func TestTX776DiagnosticsDoNotRequireWindowsHandle(t *testing.T){
    previous:=rpgState
    defer func(){rpgState=previous}()
    rpgState=rpgDashboardState{}
    tx776StartReport()
    tx776StageEvent("TX776_SELECCION","Juego seleccionado sin guardar su ruta.")
    tx776StageEvent("TX776_MODELO_VERIFICADO","Motor original con huella comprobada.")
    tx776DrainEvents()
    if !strings.Contains(rpgState.lastMessage,"TX776_SELECCION")||
        !strings.Contains(rpgState.lastMessage,"TX776_MODELO_VERIFICADO") {
        t.Fatal("progress events were silently discarded")
    }
    tx776Append("TX776_TERMINADO","Diagnóstico terminado.")
    if !strings.Contains(rpgState.lastMessage,"TX776_SELECCION") ||
        !strings.Contains(rpgState.lastMessage,"TX776_TERMINADO") {
        t.Fatal("a late diagnostic replaced the earlier history")
    }
    tx776CopyReport() // no HWND, must not panic or create global cache
}
func TestTX776NoRawExceptionExposedToShareableStatus(t *testing.T){
    prev:=rpgState
    defer func(){rpgState=prev}()
    rpgState=rpgDashboardState{}
    tx776StartReport()
    code,explanation:=tx776ExplainError(errors.New("TX771_PORTABLE_MODELS_INVALID: C:\\Users\\Hidden\\secret-password"))
    tx776Append(code,explanation)
    if strings.Contains(rpgState.lastMessage,"C:\\Users")||
       strings.Contains(rpgState.lastMessage,"secret-password") {
        t.Fatal("copied diagnostic contains private raw worker error")
    }
    if !strings.Contains(rpgState.lastMessage,"TX771_PORTABLE_MODELS_INVALID"){
        t.Fatal("real worker failure code missing")
    }
}
