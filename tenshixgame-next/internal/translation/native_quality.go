package translation

// Check native speaker-name controls in cached JA/EN -> ES results.
// This is a CONSERVATIVE read-only gate; passing does not certify fluency or
// that any text has actually reached the in-game message window.
import (
    "regexp"
    "strings"
    "unicode/utf8"
)

var nativeSpeakerTag=regexp.MustCompile(String.raw`\\N<[^>\r\n]{1,128}>`)
var rawJapanese=regexp.MustCompile(String.raw`[\x{3040}-\x{30ff}\x{3400}-\x{9fff}]`)

const (
    QualityAccepted="NATIVE_PROTECTED_TEXT_CANDIDATE"
    QualityUnknown="SOURCE_OR_TRANSLATION_INVALID"
    QualityOriginal="NOT_TRANSLATED"
    QualityChangedSpeaker="ACTOR_CONTROL_CHANGED"
    QualityEmptyBody="EMPTY_SPOKEN_BODY"
    QualityRemainingJapanese="JAPANESE_REMAINS_IN_VISIBLE_BODY"
)

// AssessNativeCandidate does not delete any controls; strips original name
// tags only from a TEMPORARY copy to inspect the displayed prose. The game
// receives the untouched original translation string when appropriate.
func AssessNativeCandidate(source Source, translated string) (bool,string) {
    if err:=validate(source);err!=nil||!utf8.ValidString(translated)||
        strings.ContainsRune(translated,0)||len(translated)>8000||
        strings.TrimSpace(translated)=="" {
        return false,QualityUnknown
    }
    if translated==source.Raw {
        return false,QualityOriginal
    }
    oldNames:=nativeSpeakerTag.FindAllString(source.Raw,-1)
    newNames:=nativeSpeakerTag.FindAllString(translated,-1)
    if len(oldNames)!=len(newNames) {
        return false,QualityChangedSpeaker
    }
    for i:=range oldNames {
        if oldNames[i]!=newNames[i] {return false,QualityChangedSpeaker}
    }
    oldBody:=nativeSpeakerTag.ReplaceAllString(source.Raw,"")
    newBody:=nativeSpeakerTag.ReplaceAllString(translated,"")
    if strings.TrimSpace(oldBody)==""||strings.TrimSpace(newBody)=="" {
        return false,QualityEmptyBody
    }
    if rawJapanese.MatchString(newBody) {
        return false,QualityRemainingJapanese
    }
    return true,QualityAccepted
}
