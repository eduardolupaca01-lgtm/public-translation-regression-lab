package translation

import "testing"
func TestUnchangedJapaneseNameMayCoexistWithSpanishDialogue(t *testing.T){
    src:=Source{"rpg-maker","mv","ja","\\N<隼人 \\N[2]>おはよう、夏実。"}
    ok,why:=AssessNativeCandidate(src,"\\N<隼人 \\N[2]>Buenos días, Natsumi.")
    if !ok||why!=QualityAccepted{t.Fatalf("protected actor result falsely blocked: %s",why)}
}
func TestNativeNameGuardRejectsJapaneseBodyAndModifiedOrLostNames(t *testing.T){
    src:=Source{"rpg-maker","mv","ja","\\N<隼人 \\N[2]>おはよう、夏実。"}
    checks:=[]struct{result,want string}{
        {"\\N<隼人 \\N[2]>おはよう、夏実。",QualityOriginal},
        {"\\N<隼人 \\N[2]>Hola、まだ",QualityRemainingJapanese},
        {"\\N<夏実 \\N[2]>Buenos días.",QualityChangedSpeaker},
        {"Buenos días.",QualityChangedSpeaker},
        {"\\N<隼人 \\N[2]>",QualityEmptyBody},
    }
    for _,c:=range checks {
        good,why:=AssessNativeCandidate(src,c.result)
        if good||why!=c.want{t.Fatalf("result expected %s got %s",c.want,why)}
    }
}
func TestCleanEnglishAndMixedRpgEscapeCodes(t *testing.T){
    src:=Source{"rpg-maker","mz","en","\\V[12] You are ready."}
    ok,why:=AssessNativeCandidate(src,"\\V[12] Estás listo.")
    if !ok||why!=QualityAccepted {t.Fatal(why)}
    ok,why=AssessNativeCandidate(src,"\\V[12] はい")
    if ok||why!=QualityRemainingJapanese{t.Fatal(why)}
}

func TestRpgControlNumbersAndSequenceAreNeverRewritten(t *testing.T){
    source:=Source{"rpg-maker","mz","ja","\\N<隼人>\\C[6]今日は\\C[0] \\V[12]点"}
    valid:="\\N<隼人>\\C[6]Hoy\\C[0] \\V[12] puntos"
    if ok,why:=AssessNativeCandidate(source,valid);!ok||why!=QualityAccepted{
        t.Fatalf("unchanged RPG codes must be allowed: %s",why)
    }
    changed:=[]string{
        "\\N<隼人>\\C[7]Hoy\\C[0] \\V[12] puntos",
        "\\N<隼人>\\C[6]Hoy\\C[0] \\V[13] puntos",
        "\\N<隼人>\\C[6]Hoy \\V[12] puntos", // missing restore-to-default color
        "\\N<隼人>\\C[0]Hoy\\C[6] \\V[12] puntos", // order changed
        "\\N<隼人>\\C[6]Hoy\\C[0] puntos", // missing dynamic variable
        "\\N<隼人>\\C[6]Hoy\\C[0] \\V[12] \\I[3] puntos", // injected control
    }
    for _,candidate:=range changed{
        if good,why:=AssessNativeCandidate(source,candidate);good||why!=QualityControlChanged{
            t.Fatalf("changed game script control accepted; quality=%q candidate=%q",why,candidate)
        }
    }
}
func TestEscapedActorCommandOutsideNameAlsoPreservesParameters(t *testing.T){
    source:=Source{"rpg-maker","mv","ja","\\N[4]が来ました。"}
    if good,why:=AssessNativeCandidate(source,"\\N[5] Ha llegado.");good||why!=QualityControlChanged{
        t.Fatalf("actor ID was silently changed: %s",why)
    }
    if good,why:=AssessNativeCandidate(source,"\\N[4] Ha llegado.");!good||why!=QualityAccepted{
        t.Fatalf("original actor ID should survive: %s",why)
    }
}

func TestVisibleDigitsSurviveJapaneseToSpanishTranslation(t *testing.T){
    input:=Source{"rpg-maker","mv","ja","\\N<隼人42>レベル３で5回成功。\\C[6]注意\\C[0]"}
    good:="\\N<隼人42>Éxito 5 veces en el nivel 3.\\C[6]Atención\\C[0]"
    if ok,reason:=AssessNativeCandidate(input,good);!ok||reason!=QualityAccepted{
        t.Fatalf("fullwidth digits and reordered quantities should be accepted: %s",reason)
    }
    checks:=[]string{
        "\\N<隼人42>Éxito 5 veces.\\C[6]Atención\\C[0]", // missing level
        "\\N<隼人42>Éxito 5 veces en el nivel 4.\\C[6]Atención\\C[0]",
        "\\N<隼人42>Éxito 5 veces en el nivel 3, bonus 10.\\C[6]Atención\\C[0]",
    }
    for _,candidate:=range checks{
        if ok,reason:=AssessNativeCandidate(input,candidate);ok||reason!=QualityNumberChanged{
            t.Fatalf("changed visible digits must be rejected: %s",reason)
        }
    }
}
func TestDynamicCodeParametersAreNotMistakenForSpokenNumbers(t *testing.T){
    input:=Source{"rpg-maker","mz","ja","\\V[12]は最後の章です。"}
    spanish:="\\V[12] es el capítulo final."
    if good,why:=AssessNativeCandidate(input,spanish);!good||why!=QualityAccepted{
        t.Fatalf("variable parameter not visible number: %s",why)
    }
    if good,why:=AssessNativeCandidate(input,"\\V[13] es el capítulo final.");good||why!=QualityControlChanged{
        t.Fatalf("parameter changed: %s",why)
    }
}
