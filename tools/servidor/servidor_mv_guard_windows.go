//go:build windows

package main

// Servidor keeps the original authenticated V95 installer and narrows the
// FIRST pilot to RPG Maker MV. It must never turn a generic detection into
// permission to modify another game engine.
import (
    "errors"
    "os"
    "path/filepath"
)

func servidorMVGameRoot(executable string) (string, error) {
    root, err := tx771GameRoot(executable)
    if err != nil { return "", err }
    var base string
    for _, candidate := range []string{root, filepath.Join(root, "www")} {
        if tx771Regular(filepath.Join(candidate, "data", "System.json")) &&
           tx771Regular(filepath.Join(candidate, "js", "plugins.js")) {
            if base != "" { return "", errors.New("TX777_MULTIPLE_GAME_LAYOUTS_REFUSED") }
            base = candidate
        }
    }
    if base == "" { return "", errors.New("TX777_MV_GAME_STRUCTURE_REQUIRED") }
    for _, directory := range []string{base, filepath.Join(base, "js"), filepath.Join(base, "data")} {
        info, e := os.Lstat(directory)
        if e != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
            return "", errors.New("TX777_MV_LINKED_GAME_FOLDER_REFUSED")
        }
    }
    for _, name := range []string{"rmmz_core.js", "rmmz_managers.js"} {
        _, e := os.Lstat(filepath.Join(base, "js", name))
        if e == nil || !os.IsNotExist(e) {
            return "", errors.New("TX777_MV_MZ_MIXED_OR_OTHER_ENGINE_REFUSED")
        }
    }
    for _, name := range []string{"rpg_core.js", "rpg_managers.js"} {
        if !tx771Regular(filepath.Join(base, "js", name)) {
            return "", errors.New("TX777_MV_ENGINE_SIGNATURE_MISSING")
        }
    }
    return root, nil
}
