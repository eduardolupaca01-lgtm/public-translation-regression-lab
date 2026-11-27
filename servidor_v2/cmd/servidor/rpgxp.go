package main

import (
    "bytes"
    "encoding/binary"
    "errors"
    "os"
    "path/filepath"
    "regexp"
    "strings"
)

const (
    rpgxpPendingCode = "IA_RPGXP_RGSS1_ADAPTADOR_PENDIENTE"
    rpgxpPackedCode = "IA_RPGXP_RGSSAD_PENDIENTE"
    rpgxpInvalidCode = "IA_RPGXP_RECURSOS_NO_VERIFICADOS"
)

var rpgxpLibrary = regexp.MustCompile("(?i)^RGSS1[0-9]{2}[A-Z]?[.]dll$")

// Detection is strictly read-only. It does not load a DLL, deserialize a
// Ruby object, execute a script, or allow installation of an RGSS3 adapter.
func rpgxpPE32(file string, dll bool) bool {
    f, err := os.Open(file)
    if err != nil { return false }
    defer f.Close()
    var dos [64]byte
    if _, err := f.ReadAt(dos[:], 0); err != nil || dos[0] != 'M' || dos[1] != 'Z' { return false }
    off := int64(binary.LittleEndian.Uint32(dos[60:64]))
    if off < 64 || off > 1024*1024 { return false }
    var h [26]byte
    if _, err := f.ReadAt(h[:], off); err != nil { return false }
    if !bytes.Equal(h[:4], []byte{'P','E',0,0}) ||
        binary.LittleEndian.Uint16(h[4:6]) != 0x14c ||
        binary.LittleEndian.Uint16(h[24:26]) != 0x10b ||
        binary.LittleEndian.Uint16(h[20:22]) < 2 { return false }
    characteristics := binary.LittleEndian.Uint16(h[22:24])
    return characteristics&0x0002 != 0 && (characteristics&0x2000 != 0) == dll
}

// matched means the native Game.ini identifies an XP candidate, not that
// the translator supports it. Reject mixed and incomplete resources.
func detectRPGXP(gameEXE string) (matched bool, err error) {
    absolute, err := filepath.Abs(gameEXE)
    if err != nil || !strings.EqualFold(filepath.Ext(absolute), ".exe") || !ordinary(absolute) { return false, nil }
    root := filepath.Dir(absolute)
    if vxaceNoSymlinkAncestors(root) != nil { return false, nil }
    ini, err := vxaceOrdinaryChild(root, "Game.ini", 64*1024)
    if err != nil { return false, nil }
    raw, err := os.ReadFile(ini)
    if err != nil { return false, nil }
    values, err := vxaceParseGameINI(raw)
    if err != nil { return false, nil }
    library := strings.TrimPrefix(strings.ReplaceAll(values["library"], "\\", "/"), "./")
    scripts := strings.TrimPrefix(strings.ReplaceAll(values["scripts"], "\\", "/"), "./")
    parts := strings.Split(library, "/")
    base := parts[len(parts)-1]
    if !rpgxpLibrary.MatchString(base) && !strings.HasSuffix(strings.ToLower(scripts), ".rxdata") { return false, nil }
    invalid := errors.New(rpgxpInvalidCode)
    if !rpgxpLibrary.MatchString(base) || !strings.EqualFold(scripts, "Data/Scripts.rxdata") ||
        !strings.EqualFold(filepath.Base(absolute), "Game.exe") { return true, invalid }
    dir := root
    if len(parts) == 2 && strings.EqualFold(parts[0], "System") {
        dir, err = vxaceDirectoryChild(root, "System")
        if err != nil { return true, invalid }
    } else if len(parts) != 1 { return true, invalid }
    dll, err := vxaceOrdinaryChild(dir, base, 64*1024*1024)
    if err != nil || !rpgxpPE32(dll, true) || !rpgxpPE32(absolute, false) { return true, invalid }
    for _, name := range []string{"Game.rgss2a", "Game.rgss3a"} {
        if _, err := vxaceFindChild(root, name); !errors.Is(err, os.ErrNotExist) { return true, invalid }
    }
    archive, err := vxaceOrdinaryChild(root, "Game.rgssad", vxaceMaxArchive)
    if err == nil {
        f, e := os.Open(archive)
        if e != nil { return true, invalid }
        var magic [8]byte
        _, e = f.ReadAt(magic[:], 0)
        f.Close()
        if e != nil || magic != [8]byte{'R','G','S','S','A','D',0,1} { return true, invalid }
        return true, errors.New(rpgxpPackedCode)
    }
    if !errors.Is(err, os.ErrNotExist) { return true, invalid }
    data, err := vxaceDirectoryChild(root, "Data")
    if err != nil { return true, invalid }
    for _, name := range []string{"Scripts.rxdata", "System.rxdata", "MapInfos.rxdata"} {
        file, e := vxaceOrdinaryChild(data, name, vxaceMaxMarshal)
        if e != nil || vxaceMarshalFile(file) != nil { return true, invalid }
    }
    return true, nil
}
