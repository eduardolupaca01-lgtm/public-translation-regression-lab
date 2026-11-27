package main

import (
	"bufio"
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const (
	vxacePluginBuildID = "VXACE-RGSS3-20261126-A"
	vxaceLibraryName = "RGSS301.dll"
	vxaceArchiveName = "Game.rgss3a"
	vxaceMaxArchive  = int64(900 * 1024 * 1024)
	vxaceMaxMarshal  = int64(128 * 1024 * 1024)
)

type vxaceFingerprint struct {
	Root        string
	GameEXE     string
	GameINI     string
	Library     string
	DataDir     string
	ScriptsFile string
	ArchiveFile string
	Packed      bool
	Title       string
}

func vxaceFindChild(dir, wanted string) (string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return "", err
	}
	var match string
	for _, entry := range entries {
		if !strings.EqualFold(entry.Name(), wanted) {
			continue
		}
		if match != "" {
			return "", errors.New("IA_VXACE_COLISION_CASE_PATH")
		}
		match = filepath.Join(dir, entry.Name())
	}
	if match == "" {
		return "", os.ErrNotExist
	}
	info, err := os.Lstat(match)
	if err != nil {
		return "", err
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return "", errors.New("IA_VXACE_RUTA_SIMBOLICA")
	}
	return match, nil
}

func vxaceOrdinaryChild(dir, wanted string, max int64) (string, error) {
	file, err := vxaceFindChild(dir, wanted)
	if err != nil {
		return "", err
	}
	info, err := os.Lstat(file)
	if err != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
		return "", errors.New("IA_VXACE_ARCHIVO_NO_ORDINARIO")
	}
	if info.Size() <= 0 || info.Size() > max {
		return "", errors.New("IA_VXACE_TAMANO_INVALIDO")
	}
	return file, nil
}

func vxaceDirectoryChild(dir, wanted string) (string, error) {
	child, err := vxaceFindChild(dir, wanted)
	if err != nil {
		return "", err
	}
	info, err := os.Lstat(child)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return "", errors.New("IA_VXACE_DIRECTORIO_NO_ORDINARIO")
	}
	return child, nil
}

func vxaceNoSymlinkAncestors(path string) error {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return errors.New("IA_VXACE_RUTA_INVALIDA")
	}
	for current := absolute; ; current = filepath.Dir(current) {
		info, statErr := os.Lstat(current)
		if statErr != nil || info.Mode()&os.ModeSymlink != 0 {
			return errors.New("IA_VXACE_RUTA_SIMBOLICA")
		}
		if filepath.Dir(current) == current {
			break
		}
	}
	return nil
}

func vxacePE(file string) bool {
	f, err := os.Open(file)
	if err != nil {
		return false
	}
	defer f.Close()
	var dos [64]byte
	if _, err = f.Read(dos[:]); err != nil || dos[0] != 'M' || dos[1] != 'Z' {
		return false
	}
	offset := int64(binary.LittleEndian.Uint32(dos[0x3c:0x40]))
	if offset < 64 || offset > 1024*1024 {
		return false
	}
	var signature [6]byte
	if _, err = f.ReadAt(signature[:], offset); err != nil {
		return false
	}
	if !bytes.Equal(signature[:4], []byte{'P', 'E', 0, 0}) {
		return false
	}
	machine := binary.LittleEndian.Uint16(signature[4:6])
	return machine == 0x014c || machine == 0x8664
}

func vxaceParseGameINI(raw []byte) (map[string]string, error) {
	if len(raw) == 0 || len(raw) > 64*1024 || bytes.IndexByte(raw, 0) >= 0 {
		return nil, errors.New("IA_VXACE_GAME_INI_INVALIDO")
	}
	text := strings.TrimPrefix(string(bytes.TrimPrefix(raw, []byte{0xef, 0xbb, 0xbf})), "\uFEFF")
	values := map[string]string{}
	section := ""
	scanner := bufio.NewScanner(strings.NewReader(text))
	scanner.Buffer(make([]byte, 1024), 64*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, ";") || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section = strings.ToLower(strings.TrimSpace(line[1 : len(line)-1]))
			continue
		}
		if section != "game" {
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			return nil, errors.New("IA_VXACE_GAME_INI_INVALIDO")
		}
		key = strings.ToLower(strings.TrimSpace(key))
		value = strings.TrimSpace(value)
		if key == "" || value == "" {
			return nil, errors.New("IA_VXACE_GAME_INI_INVALIDO")
		}
		if _, exists := values[key]; exists {
			return nil, errors.New("IA_VXACE_GAME_INI_DUPLICADO")
		}
		values[key] = value
	}
	if err := scanner.Err(); err != nil {
		return nil, errors.New("IA_VXACE_GAME_INI_LECTURA")
	}
	if len(values) == 0 {
		return nil, errors.New("IA_VXACE_GAME_INI_SIN_SECCION")
	}
	return values, nil
}

func vxaceMarshalFile(file string) error {
	f, err := os.Open(file)
	if err != nil {
		return err
	}
	defer f.Close()
	var header [2]byte
	if _, err = f.Read(header[:]); err != nil || header != [2]byte{4, 8} {
		return errors.New("IA_VXACE_MARSHAL_INVALIDO")
	}
	return nil
}

// detectVXAce returns matched=false only when the selected executable is not
// recognizably VX Ace. Once RGSS301.dll/Game.ini markers match, malformed
// resources fail closed instead of falling through to another engine.
func detectVXAce(gameEXE string) (vxaceFingerprint, bool, error) {
	var result vxaceFingerprint
	absolute, err := filepath.Abs(gameEXE)
	if err != nil || !strings.EqualFold(filepath.Ext(absolute), ".exe") || !ordinary(absolute) {
		return result, false, nil
	}
	root := filepath.Dir(absolute)
	if err = vxaceNoSymlinkAncestors(root); err != nil {
		return result, false, err
	}
	gameINI, iniErr := vxaceOrdinaryChild(root, "Game.ini", 64*1024)
	if iniErr != nil {
		return result, false, nil
	}
	iniBytes, err := os.ReadFile(gameINI)
	if err != nil {
		return result, true, errors.New("IA_VXACE_GAME_INI_LECTURA")
	}
	values, err := vxaceParseGameINI(iniBytes)
	if err != nil {
		return result, true, err
	}
	libraryName := values["library"]
	if !strings.EqualFold(filepath.Base(strings.ReplaceAll(libraryName, "\\", "/")), vxaceLibraryName) {
		return result, false, nil
	}
	result = vxaceFingerprint{Root: root, GameEXE: absolute, GameINI: gameINI, Title: values["title"]}
	library, err := vxaceOrdinaryChild(root, vxaceLibraryName, 64*1024*1024)
	if err != nil || !vxacePE(library) || !vxacePE(absolute) {
		return result, true, errors.New("IA_VXACE_RUNTIME_NO_VERIFICADO")
	}
	result.Library = library
	scriptsSetting := strings.ReplaceAll(values["scripts"], "\\", "/")
	scriptsSetting = strings.TrimPrefix(scriptsSetting, "./")
	if scriptsSetting == "" {
		scriptsSetting = "Data/Scripts.rvdata2"
	}
	parts := strings.Split(scriptsSetting, "/")
	if len(parts) != 2 || !strings.EqualFold(parts[0], "Data") || !strings.EqualFold(parts[1], "Scripts.rvdata2") {
		return result, true, errors.New("IA_VXACE_SCRIPTS_PATH_NO_ADMITIDO")
	}
	archive, archiveErr := vxaceOrdinaryChild(root, vxaceArchiveName, vxaceMaxArchive)
	if archiveErr == nil {
		f, openErr := os.Open(archive)
		if openErr != nil {
			return result, true, errors.New("IA_VXACE_ARCHIVO_NO_LEIBLE")
		}
		var header [8]byte
		_, readErr := f.Read(header[:])
		_ = f.Close()
		if readErr != nil || !bytes.Equal(header[:], []byte{'R', 'G', 'S', 'S', 'A', 'D', 0, 3}) {
			return result, true, errors.New("IA_VXACE_RGSS3A_INVALIDO")
		}
		result.ArchiveFile = archive
		result.Packed = true
		// The archive helper performs the authoritative entry-table and
		// Scripts.rvdata2 validation before any write is permitted.
		return result, true, nil
	}
	if !errors.Is(archiveErr, os.ErrNotExist) {
		return result, true, archiveErr
	}
	data, err := vxaceDirectoryChild(root, "Data")
	if err != nil {
		return result, true, errors.New("IA_VXACE_DATA_NO_DISPONIBLE")
	}
	scripts, err := vxaceOrdinaryChild(data, "Scripts.rvdata2", vxaceMaxMarshal)
	if err != nil {
		return result, true, errors.New("IA_VXACE_SCRIPTS_NO_DISPONIBLE")
	}
	if err = vxaceMarshalFile(scripts); err != nil {
		return result, true, err
	}
	for _, required := range []string{"System.rvdata2", "MapInfos.rvdata2"} {
		file, e := vxaceOrdinaryChild(data, required, vxaceMaxMarshal)
		if e != nil {
			return result, true, errors.New("IA_VXACE_DATA_INCOMPLETA")
		}
		if e = vxaceMarshalFile(file); e != nil {
			return result, true, e
		}
	}
	for _, incompatible := range []string{"Game.rgssad", "Game.rgss2a"} {
		if _, e := vxaceFindChild(root, incompatible); e == nil {
			return result, true, errors.New("IA_VXACE_ARCHIVO_DE_OTRO_MOTOR")
		}
	}
	result.DataDir = data
	result.ScriptsFile = scripts
	return result, true, nil
}

func vxaceDiagnostic(fp vxaceFingerprint) string {
	mode := "loose"
	if fp.Packed {
		mode = "rgss3a"
	}
	return fmt.Sprintf("VXACE mode=%s", mode)
}
