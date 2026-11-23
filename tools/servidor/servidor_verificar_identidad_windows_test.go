//go:build windows

package main

import "testing"

func TestServidorF10PostconditionRejectsOldIdentity(t *testing.T){
    for _,bad:=range []string{
        "◆ TENSHIXGAME RPG · F10\nTENSHIXGAME RPG · V95",
        "◆ IA Traductora · F10\nTENSHIXGAME RPG · V95",
        "TENSHIXGAME RPG · V95\n◆ IA Traductora · F10",
        "◆ IA Traductora · F10",
    }{
        if servidorValidVisibleIAPlugin([]byte(bad)){
            t.Fatal("legacy or incomplete installed F10 branding must fail")
        }
    }
    if !servidorValidVisibleIAPlugin([]byte(
        "◆ IA Traductora · F10\nIA Traductora · V95")){
        t.Fatal("correct brand must pass")
    }
}
