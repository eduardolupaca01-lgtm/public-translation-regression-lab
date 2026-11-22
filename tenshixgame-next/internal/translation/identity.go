package translation

// Identity of a translation must be the same in scanner, V95 cache and game
// renderer. A game folder path is NEVER part of the key, so copying the
// complete translated game to another drive does not invalidate its cache.
import (
    "crypto/sha256"
    "encoding/hex"
    "errors"
    "strings"
    "unicode/utf8"
)

type Source struct{
    Family string
    Engine string
    Language string
    Raw string
}
const Schema="tenshixgame-exact-source-v1"

// Key keeps all meaningful whitespace, RPG escape codes and Japanese content.
// No lossy lowercase, trim or command stripping: those operations can collide
// with different choices, variables and formatting of an author's game.
func Key(s Source)(string,error){
    if s.Family==""||s.Engine==""||s.Language==""||s.Raw==""{
        return "",errors.New("campo obligatorio vacío")
    }
    for _,field:=range []string{s.Family,s.Engine,s.Language,s.Raw}{
        if !utf8.ValidString(field)||strings.ContainsRune(field,0){
            return "",errors.New("fuente no es UTF-8 válida o contiene NUL")
        }
    }
    h:=sha256.New()
    for _,segment:=range []string{Schema,s.Family,s.Engine,s.Language,s.Raw}{
        h.Write([]byte(segment))
        h.Write([]byte{0})
    }
    return hex.EncodeToString(h.Sum(nil)),nil
}

// Match is deliberately strict: a painter must provide the SAME raw source
// that the scanner stored. A mismatch is a diagnostic, not license to guess.
func Match(scannerSource,paintedSource Source)(bool,error){
    a,err:=Key(scannerSource);if err!=nil{return false,err}
    b,err:=Key(paintedSource);if err!=nil{return false,err}
    return a==b,nil
}
