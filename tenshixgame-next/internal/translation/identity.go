package translation

// Native cache keys MUST match the verified original in-game MV/MZ bridge:
// sha256(UTF8(resolved_source_language + NUL + original_source_text)).
// A separate ScopedKey is used only by new diagnostic inventories.
// Neither formula contains a game path: a copied whole game retains its cache.
import (
    "crypto/sha256"
    "encoding/hex"
    "errors"
    "strings"
    "unicode/utf8"
)

type Source struct {
    Family string
    Engine string
    Language string
    Raw string
}

const Schema="tenshixgame-exact-source-v1"

func validate(s Source) error {
    if s.Family=="" || s.Engine=="" || s.Raw=="" {
        return errors.New("identidad de fuente incompleta")
    }
    if s.Language!="ja" && s.Language!="en" {
        return errors.New("idioma sin resolver: solo ja o en; no usar auto en la clave")
    }
    for _,value:=range []string{s.Family,s.Engine,s.Language,s.Raw}{
        if !utf8.ValidString(value)||strings.ContainsRune(value,0) {
            return errors.New("fuente UTF-8 inválida o con NUL")
        }
    }
    return nil
}

// ResolveAutoLanguage reproduces the source-script decision used by the
// original in-game plugin. The GUI may say "auto"; the cache key NEVER does.
func ResolveAutoLanguage(raw string) string {
    for _,r:=range raw {
        if r>=0x3040 && r<=0x30ff || r>=0x3400 && r<=0x9fff {
            return "ja"
        }
    }
    return "en"
}

// Key interoperates with the existing V95 plugin and its SQLite / JSON cache.
// Keep every original byte, including RPG control codes and whitespace.
func Key(s Source)(string,error){
    if err:=validate(s);err!=nil{return "",err}
    sum:=sha256.Sum256([]byte(s.Language+"\x00"+s.Raw))
    return hex.EncodeToString(sum[:]),nil
}

// ScopedKey can disambiguate engine inventories but MUST NOT be written into
// files the original plugin expects under its native Key.
func ScopedKey(s Source)(string,error){
    if err:=validate(s);err!=nil{return "",err}
    h:=sha256.New()
    for _,segment:=range []string{Schema,s.Family,s.Engine,s.Language,s.Raw} {
        _,_ = h.Write([]byte(segment))
        _,_ = h.Write([]byte{0})
    }
    return hex.EncodeToString(h.Sum(nil)),nil
}

// Match checks both the original bridge key and the current engine context.
// Never reuse a key blindly across unrelated plugin families.
func Match(scannerSource,paintedSource Source)(bool,error){
    a,err:=Key(scannerSource);if err!=nil{return false,err}
    b,err:=Key(paintedSource);if err!=nil{return false,err}
    return a==b &&
        scannerSource.Engine==paintedSource.Engine &&
        scannerSource.Family==paintedSource.Family,nil
}
