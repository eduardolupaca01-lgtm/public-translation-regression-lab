package translation

// Check native speaker-name controls in cached JA/EN -> ES results.
// This is a CONSERVATIVE read-only gate; passing does not certify fluency or
// that any text has actually reached the in-game message window.
import (
    "regexp"
    "sort"
    "strings"
    "unicode/utf8"
)

var nativeSpeakerTag=regexp.MustCompile(`\\N<[^>\r\n]{1,128}>`)
var rawJapanese=regexp.MustCompile(`[\x{3040}-\x{30ff}\x{3400}-\x{9fff}]`)
// Use the same RPG escape-code family as the ORIGINAL V95 native bridge.
// Actor tags are checked separately and then removed ONLY from scratch copies.
var rpgEscapeCode=regexp.MustCompile(`\\(?:[A-Za-z]+\[[^\]\r\n]+\]|[A-Za-z{}.!^$<>\\|])`)
var visibleDigits=regexp.MustCompile(`[0-9０-９]+`)

const (
    QualityAccepted="NATIVE_PROTECTED_TEXT_CANDIDATE"
    QualityUnknown="SOURCE_OR_TRANSLATION_INVALID"
    QualityOriginal="NOT_TRANSLATED"
    QualityChangedSpeaker="ACTOR_CONTROL_CHANGED"
    QualityControlChanged="RPG_CONTROL_CODE_CHANGED"
    QualityNumberChanged="RPG_VISIBLE_DIGITS_CHANGED"
    QualityEmptyBody="EMPTY_SPOKEN_BODY"
    QualityRemainingJapanese="JAPANESE_REMAINS_IN_VISIBLE_BODY"
)

// digitsOutsideControls mirrors the ORIGINAL TX710CleanCore.valid numeric gate.
// The controls' parameters and Japanese actor metadata are not spoken text,
// so they must NOT be counted as quantities in the visible dialogue.
func digitsOutsideControls(text string) []string {
    body:=rpgEscapeCode.ReplaceAllString(nativeSpeakerTag.ReplaceAllString(text,""),"")
    tokens:=visibleDigits.FindAllString(body,-1)
    for i,token:=range tokens {
        runes:=[]rune(token)
        for j,digit:=range runes {
            if digit>='０' && digit<='９'{
                runes[j]='0'+(digit-'０')
            }
        }
        tokens[i]=string(runes)
    }
    sort.Strings(tokens)
    return tokens
}

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
    // A translation may not change the game's event-control semantics:
    // variables, color, icons, wait, actor references and sequence matter.
    // Matching only speaker names would wrongly accept changed \V[1] or
    // dropped \C[0]. This mirrors TX710CleanCore.valid from original V95.
    originalCodes:=rpgEscapeCode.FindAllString(oldBody,-1)
    translatedCodes:=rpgEscapeCode.FindAllString(newBody,-1)
    if len(originalCodes)!=len(translatedCodes) {
        return false,QualityControlChanged
    }
    for i:=range originalCodes {
        if originalCodes[i]!=translatedCodes[i] {
            return false,QualityControlChanged
        }
    }
    // A completed model result with missing or modified visible digits
    // is NOT safe to paint or persist. Allow reordered quantities, but not
    // deleted or newly invented ones; normalize full-width Japanese digits.
    originals:=digitsOutsideControls(source.Raw)
    translatedNums:=digitsOutsideControls(translated)
    if len(originals)!=len(translatedNums){
        return false,QualityNumberChanged
    }
    for i:=range originals {
        if originals[i]!=translatedNums[i] {
            return false,QualityNumberChanged
        }
    }
    if rawJapanese.MatchString(newBody) {
        return false,QualityRemainingJapanese
    }
    return true,QualityAccepted
}
