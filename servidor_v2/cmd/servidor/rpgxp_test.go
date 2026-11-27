package main

import (
    "bytes"
    "encoding/binary"
    "os"
    "path/filepath"
    "testing"
)

func rpgxpPEFixture(dll bool) []byte {
    b := make([]byte, 256)
    copy(b, "MZ")
    binary.LittleEndian.PutUint32(b[60:64], 64)
    copy(b[64:], []byte{'P','E',0,0})
    binary.LittleEndian.PutUint16(b[68:70], 0x14c)
    binary.LittleEndian.PutUint16(b[84:86], 2)
    flags := uint16(2)
    if dll { flags |= 0x2000 }
    binary.LittleEndian.PutUint16(b[86:88], flags)
    binary.LittleEndian.PutUint16(b[88:90], 0x10b)
    return b
}

func rpgxpFixture(t *testing.T) string {
    t.Helper()
    root := filepath.Join(t.TempDir(), "XP prueba")
    data := filepath.Join(root, "Data")
    if e := os.MkdirAll(data, 0700); e != nil { t.Fatal(e) }
    files := map[string][]byte{
        "Game.exe": rpgxpPEFixture(false),
        "RGSS104E.dll": rpgxpPEFixture(true),
        "Game.ini": []byte("[Game]\r\nLibrary=RGSS104E.dll\r\nScripts=Data\\Scripts.rxdata\r\nTitle=Prueba XP\r\nRTP1=Standard\r\n"),
        "Data/Scripts.rxdata": {4,8,0x5b,0},
        "Data/System.rxdata": {4,8,0x5b,0},
        "Data/MapInfos.rxdata": {4,8,0x5b,0},
    }
    for name, b := range files {
        if e := os.WriteFile(filepath.Join(root, filepath.FromSlash(name)), b, 0600); e != nil { t.Fatal(e) }
    }
    return filepath.Join(root,"Game.exe")
}

func TestRPGXPDetectionDoesNotEnableInstaller(t *testing.T) {
    exe := rpgxpFixture(t)
    root := filepath.Dir(exe)
    scripts := filepath.Join(root,"Data","Scripts.rxdata")
    before, e := os.ReadFile(scripts)
    if e != nil { t.Fatal(e) }
    if matched,e := detectRPGXP(exe); !matched || e != nil { t.Fatalf("XP not recognized: %v %v",matched,e) }
    if _,e := detectInstallTarget(exe); e == nil || e.Error()!=rpgxpPendingCode { t.Fatalf("XP must be detected but blocked: %v",e) }
    if e := Install(exe,nil); e == nil || e.Error()!=rpgxpPendingCode { t.Fatalf("unimplemented XP installation not blocked: %v",e) }
    after,e := os.ReadFile(scripts)
    if e != nil || !bytes.Equal(before,after) { t.Fatal("original script changed") }
    if _,e := os.Stat(filepath.Join(root,"IA Traductora")); !os.IsNotExist(e) { t.Fatal("detector created sidecar") }
}

func TestRPGXPRejectsInvalidOrForeignResources(t *testing.T) {
    for _,tc := range []struct{name,file string; body []byte; expected string}{
        {"invalid runtime","RGSS104E.dll",[]byte("not PE"),rpgxpInvalidCode},
        {"invalid Marshal","Data/Scripts.rxdata",[]byte("not Marshal"),rpgxpInvalidCode},
        {"foreign archive","Game.rgss3a",[]byte("foreign"),rpgxpInvalidCode},
        {"packed XP","Game.rgssad",[]byte{'R','G','S','S','A','D',0,1},rpgxpPackedCode},
        {"escape path","Game.ini",[]byte("[Game]\nLibrary=../RGSS104E.dll\nScripts=Data/Scripts.rxdata\n"),rpgxpInvalidCode},
    } {
        t.Run(tc.name,func(t *testing.T){
            exe:=rpgxpFixture(t)
            if e:=os.WriteFile(filepath.Join(filepath.Dir(exe),filepath.FromSlash(tc.file)),tc.body,0600); e!=nil {t.Fatal(e)}
            matched,e:=detectRPGXP(exe)
            if !matched || e==nil || e.Error()!=tc.expected {t.Fatalf("unexpected detection: %v %v",matched,e)}
            if _,e:=detectInstallTarget(exe);e==nil {t.Fatal("invalid/unsupported XP accepted")}
        })
    }
}
func TestRPGXPDoesNotClaimVXAce(t *testing.T) {
    exe:=vxaceFixture(t,false)
    if matched,e:=detectRPGXP(exe);matched||e!=nil{t.Fatalf("foreign engine claimed: %v %v",matched,e)}
    if kind,e:=detectInstallTarget(exe);e!=nil||kind!="VX Ace"{t.Fatalf("existing engine lost: %s %v",kind,e)}
}
