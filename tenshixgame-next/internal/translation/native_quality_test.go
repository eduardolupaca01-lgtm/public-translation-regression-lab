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
