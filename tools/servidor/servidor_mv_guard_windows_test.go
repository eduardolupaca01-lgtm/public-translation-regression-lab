//go:build windows

package main

import (
    "os"
    "path/filepath"
    "testing"
)

func servidorFixture(t *testing.T, entries ...string) string {
    t.Helper()
    root := t.TempDir()
    for name, value := range map[string]string{
        "Game.exe":"MZ-test-EXE", "www/data/System.json":"{}",
        "www/js/plugins.js":"var $plugins=[];",
    } {
        target := filepath.Join(root,filepath.FromSlash(name))
        if err := os.MkdirAll(filepath.Dir(target),0755); err != nil { t.Fatal(err) }
        if err := os.WriteFile(target,[]byte(value),0644); err != nil { t.Fatal(err) }
    }
    for _, name := range entries {
        target := filepath.Join(root,"www","js",name)
        if err := os.WriteFile(target,[]byte("// fixture"),0644); err != nil { t.Fatal(err) }
    }
    return filepath.Join(root,"Game.exe")
}
func TestServidorMVAcceptsOnlyVerifiedMV(t *testing.T) {
    exe := servidorFixture(t,"rpg_core.js","rpg_managers.js")
    root,err := servidorMVGameRoot(exe)
    if err != nil || root != filepath.Dir(exe) { t.Fatalf("MV original: %q %v",root,err) }
}
func TestServidorMVRejectsMZ(t *testing.T) {
    exe := servidorFixture(t,"rmmz_core.js","rmmz_managers.js")
    if _,err := servidorMVGameRoot(exe);err == nil {t.Fatal("MZ must be refused")}
}
func TestServidorMVRejectsMixedEngine(t *testing.T) {
    exe := servidorFixture(t,"rpg_core.js","rpg_managers.js","rmmz_core.js")
    if _,err := servidorMVGameRoot(exe);err == nil {t.Fatal("mixed engine must be refused")}
}
func TestServidorMVRejectsLayoutWithoutCore(t *testing.T) {
    exe := servidorFixture(t,"rpg_core.js")
    if _,err := servidorMVGameRoot(exe);err == nil {t.Fatal("incomplete MV core must be refused")}
}
func TestServidorMVRejectsMissingGame(t *testing.T) {
    if _,err := servidorMVGameRoot(filepath.Join(t.TempDir(),"Game.exe"));err == nil {t.Fatal("missing EXE was accepted")}
}
