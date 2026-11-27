package main

import (
	"bufio"
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

const (
	vxacePluginBuildID = "VXACE-RGSS3-20261126-F"
	vxaceLibraryName = "RGSS301.dll"
	vxaceArchiveName = "Game.rgss3a"
	// The original 900 MiB cap rejected otherwise valid packed games.
	// Keep input AND output below the conservative signed 32-bit seek bound
	// of the legacy runtime. This is not the installer ZIP size limit.
	vxaceMaxArchive  = int64(2*1024*1024*1024 - 1)
	vxaceMaxMarshal  = int64(512 * 1024 * 1024)
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

func vxaceAMD64PE(file string) bool {
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
	var signature [26]byte
	if _, err = f.ReadAt(signature[:], offset); err != nil {
		return false
	}
	return bytes.Equal(signature[:4], []byte{'P', 'E', 0, 0}) &&
		binary.LittleEndian.Uint16(signature[4:6]) == 0x8664 &&
		binary.LittleEndian.Uint16(signature[24:26]) == 0x20b
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
		if key == "" || ((key == "library" || key == "scripts") && value == "") {
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
	libraryName := strings.TrimPrefix(strings.ReplaceAll(values["library"], "\\", "/"), "./")
	libParts := strings.Split(libraryName, "/")
	libBase := libParts[len(libParts)-1]
	if !strings.EqualFold(libBase, "RGSS300.dll") && !strings.EqualFold(libBase, vxaceLibraryName) {
		return result, false, nil
	}
	result = vxaceFingerprint{Root: root, GameEXE: absolute, GameINI: gameINI, Title: values["title"]}
	if !strings.EqualFold(filepath.Base(absolute), "Game.exe") {
		return result, true, errors.New("IA_VXACE_GAME_EXE_NO_ESTANDAR")
	}
	libDir := root
	if len(libParts) == 2 && strings.EqualFold(libParts[0], "System") {
		libDir, err = vxaceDirectoryChild(root, "System")
		if err != nil { return result, true, errors.New("IA_VXACE_RUNTIME_NO_VERIFICADO") }
	} else if len(libParts) != 1 {
		return result, true, errors.New("IA_VXACE_LIBRARY_PATH_NO_ADMITIDO")
	}
	library, err := vxaceOrdinaryChild(libDir, libBase, 64*1024*1024)
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
	for _, incompatible := range []string{"Game.rgssad", "Game.rgss2a"} {
		if _, e := vxaceFindChild(root, incompatible); !errors.Is(e, os.ErrNotExist) {
			return result, true, errors.New("IA_VXACE_ARCHIVO_DE_OTRO_MOTOR")
		}
	}
	if engineAt(root) != "" || engineAt(filepath.Join(root, "www")) != "" {
		return result, true, errors.New("IA_RPG_RUTAS_AMBIGUAS")
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


type vxaceReceipt struct {
	Schema string `json:"schema"`
	BeforeSHA string `json:"before_sha256"`
	AfterSHA string `json:"after_sha256"`
	PluginSHA string `json:"plugin_sha256"`
	WorkerSHA string `json:"worker_sha256"`
	HelperSHA string `json:"helper_sha256"`
	Mode string `json:"mode"`
	TargetRel string `json:"target_rel"`
	Build string `json:"build"`
	Status string `json:"status"`
}

type vxaceHelperReport struct {
	Schema string `json:"schema"`
	Mode string `json:"mode"`
	OriginalSHA string `json:"original_sha256"`
	OutputSHA string `json:"output_sha256"`
	PluginSHA string `json:"plugin_sha256"`
	ScriptIndex int `json:"script_index"`
	ArchiveEntries int `json:"archive_entries"`
	NonScriptEntriesPreserved bool `json:"non_script_entries_preserved"`
}

func vxacePaths(fp vxaceFingerprint) (target, backupName, targetRel, mode, outputName string, maxSize int64) {
	if fp.Packed {
		return fp.ArchiveFile, "original-Game.rgss3a", "Game.rgss3a", "rgss3a", "Game.rgss3a.new", vxaceMaxArchive
	}
	return fp.ScriptsFile, "original-Scripts.rvdata2", "Data/Scripts.rvdata2", "loose", "Scripts.rvdata2.new", vxaceMaxMarshal
}

// Worst additional on-disk footprint: backup (if not present), extracted
// entries plus repacked archive, or repacked archive plus replacement temp.
// Reserve extra room for the patched Marshal script and filesystem overhead.
// The sidecar package has already been staged when this check runs.
func vxaceArchiveSpaceNeeded(size int64, needBackup bool) uint64 {
	copies := uint64(2)
	if needBackup { copies++ }
	return uint64(size)*copies + 2*uint64(vxaceMaxMarshal) + 128*1024*1024
}

func vxaceEnsureArchiveSpace(fp vxaceFingerprint, needBackup bool) error {
	if !fp.Packed { return nil }
	info, err := os.Stat(fp.ArchiveFile)
	if err != nil || info.Size() <= 0 || info.Size() > vxaceMaxArchive {
		return errors.New("IA_VXACE_TAMANO_INVALIDO")
	}
	return vxaceCheckDiskSpace(fp.Root, vxaceArchiveSpaceNeeded(info.Size(), needBackup))
}

func vxaceCopyFileNew(source, destination string) error {
	if !ordinary(source) {
		return errors.New("IA_VXACE_BACKUP_SOURCE_INVALID")
	}
	if _, err := os.Lstat(destination); err == nil {
		return errors.New("IA_VXACE_BACKUP_EXISTS")
	} else if !os.IsNotExist(err) {
		return errors.New("IA_VXACE_BACKUP_INSPECT_FAILED")
	}
	input, err := os.Open(source)
	if err != nil {
		return errors.New("IA_VXACE_BACKUP_SOURCE_UNREADABLE")
	}
	defer input.Close()
	output, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return errors.New("IA_VXACE_BACKUP_CREATE_FAILED")
	}
	ok := false
	defer func() {
		if !ok {
			_ = os.Remove(destination)
		}
	}()
	if _, err = io.CopyBuffer(output, input, make([]byte, 256*1024)); err != nil {
		_ = output.Close()
		return errors.New("IA_VXACE_BACKUP_COPY_FAILED")
	}
	if err = output.Sync(); err != nil {
		_ = output.Close()
		return errors.New("IA_VXACE_BACKUP_SYNC_FAILED")
	}
	if err = output.Close(); err != nil {
		return errors.New("IA_VXACE_BACKUP_CLOSE_FAILED")
	}
	sourceSHA, err := digestFile(source)
	if err != nil {
		return errors.New("IA_VXACE_BACKUP_SOURCE_HASH_FAILED")
	}
	backupSHA, err := digestFile(destination)
	if err != nil || backupSHA != sourceSHA {
		return errors.New("IA_VXACE_BACKUP_HASH_MISMATCH")
	}
	ok = true
	return nil
}

// Each replacement has already been journaled with both exact SHA-256
// values. Never delete the old resource, truncate it in place, or rename
// it out of the way as a fallback. Recheck after staging and before retries.
var vxaceMoveReplacement = vxaceReplaceOnce
var vxaceReplacementSleep = time.Sleep

func vxaceSameReplaceFile(a,b os.FileInfo) bool {
	return a != nil && b != nil && a.Mode().IsRegular() && b.Mode().IsRegular() &&
		os.SameFile(a,b) && a.Size()==b.Size() && a.ModTime().Equal(b.ModTime())
}

func vxaceVerifiedReplaceFile(filename, expected string) (os.FileInfo,error) {
	st,err:=os.Lstat(filename)
	if err!=nil || !st.Mode().IsRegular() || st.Mode()&os.ModeSymlink!=0 {
		return nil,errors.New("IA_VXACE_REPLACE_TARGET_UNSAFE")
	}
	actual,err:=digestFile(filename)
	if err!=nil {return nil,errors.New("IA_VXACE_REPLACE_HASH_NO_VERIFICADO")}
	after,err:=os.Lstat(filename)
	if err!=nil || actual!=expected || !vxaceSameReplaceFile(st,after) {
		return nil,errors.New("IA_VXACE_RECURSO_CAMBIO_DURANTE_REEMPLAZO")
	}
	return after,nil
}

func vxaceReplacementError(err error) error {
	// Public diagnostics expose only a numeric OS status, not user paths.
	if strings.HasPrefix(err.Error(),"IA_VXACE_") {return err}
	var errno syscall.Errno
	if errors.As(err,&errno) {
		switch errno {
		case 5:return errors.New("IA_VXACE_REPLACE_ACCESS_DENIED_WIN32_5")
		case 32:return errors.New("IA_VXACE_REPLACE_SHARING_WIN32_32")
		case 33:return errors.New("IA_VXACE_REPLACE_LOCKED_WIN32_33")
		default:return fmt.Errorf("IA_VXACE_REPLACE_ATOMIC_OS_%d",uint64(errno))
		}
	}
	return errors.New("IA_VXACE_REPLACE_ATOMIC_FAILED")
}

func vxaceAtomicReplaceFrom(source, destination, sourceSHA, destinationSHA string) error {
	if !ordinary(source) {
		return errors.New("IA_VXACE_REPLACE_SOURCE_INVALID")
	}
	if err:=vxaceNoSymlinkAncestors(filepath.Dir(destination));err!=nil{return err}
	if !ordinary(destination) {return errors.New("IA_VXACE_REPLACE_TARGET_UNSAFE")}
	tmp, err := os.CreateTemp(filepath.Dir(destination), ".ia-vxace-replace-")
	if err != nil {
		return errors.New("IA_VXACE_REPLACE_TEMP_FAILED")
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName)
	input, err := os.Open(source)
	if err != nil {
		_ = tmp.Close()
		return errors.New("IA_VXACE_REPLACE_SOURCE_UNREADABLE")
	}
	_, copyErr := io.CopyBuffer(tmp, input, make([]byte, 256*1024))
	inputErr := input.Close()
	if copyErr != nil || inputErr != nil {
		_ = tmp.Close()
		return errors.New("IA_VXACE_REPLACE_COPY_FAILED")
	}
	if err = tmp.Sync(); err != nil {
		_ = tmp.Close()
		return errors.New("IA_VXACE_REPLACE_SYNC_FAILED")
	}
	if err = tmp.Close(); err != nil {
		return errors.New("IA_VXACE_REPLACE_CLOSE_FAILED")
	}
	prepared,err:=vxaceVerifiedReplaceFile(tmpName,sourceSHA)
	if err!=nil{return errors.New("IA_VXACE_REPLACE_TEMP_SHA_INVALIDO")}
	// Retry transient file-sharing failures only; never ask Windows to
	// bypass ACLs, terminate the game, or defer a replacement to reboot.
	// Rehash the current target on each attempt, since a concurrent writer
	// must not be overwritten. Do not repeat the large archive construction.
	for attempt:=0;attempt<6;attempt++{
		original,e:=vxaceVerifiedReplaceFile(destination,destinationSHA)
		if e!=nil{return e}
		check,e:=os.Lstat(tmpName)
		if e!=nil||!vxaceSameReplaceFile(prepared,check){
			return errors.New("IA_VXACE_REPLACE_TEMP_SHA_INVALIDO")
		}
		err=vxaceMoveReplacement(tmpName,destination,original)
		if err==nil{return nil}
		if !iaIsTransientRename(err)||attempt==5{return vxaceReplacementError(err)}
		vxaceReplacementSleep(time.Duration(100*(1<<attempt))*time.Millisecond)
	}
	return errors.New("IA_VXACE_REPLACE_ATOMIC_FAILED")
}

func vxaceReadReceipt(filename string) (vxaceReceipt, bool, error) {
	var receipt vxaceReceipt
	if !ordinary(filename) {
		if _, err := os.Lstat(filename); os.IsNotExist(err) {
			return receipt, false, nil
		}
		return receipt, false, errors.New("IA_VXACE_RECIBO_INVALIDO")
	}
	raw, err := os.ReadFile(filename)
	if err != nil || len(raw) > 16*1024 || json.Unmarshal(raw, &receipt) != nil ||
		receipt.Schema != "ia-traductora-vxace-install-v1" ||
		len(receipt.BeforeSHA) != 64 || len(receipt.AfterSHA) != 64 ||
		len(receipt.PluginSHA) != 64 || len(receipt.HelperSHA) != 64 ||
		len(receipt.WorkerSHA) != 64 {
		return receipt, false, errors.New("IA_VXACE_RECIBO_INVALIDO")
	}
	return receipt, true, nil
}

func vxaceSidecarPaths(root string) (sidecar, engine, helper, plugin, worker, receiptFile, installDir string) {
	sidecar = filepath.Join(root, brandFolder)
	engine = filepath.Join(sidecar, ".local", "Rpg", "engine")
	helper = filepath.Join(engine, "vxace-helper.exe")
	plugin = filepath.Join(engine, "vxace", "IATraductoraVXACE.rb")
	worker = filepath.Join(engine, "IATraductora.exe")
	installDir = filepath.Join(sidecar, "install", "vxace")
	receiptFile = filepath.Join(sidecar, "install", "vxace-receipt.json")
	return
}

func installVXAce(fp vxaceFingerprint, pkg *packageReader) error {
	if pkg == nil || pkg.files["vxace-helper.exe"] == nil || pkg.files["vxace/IATraductoraVXACE.rb"] == nil {
		return errors.New("IA_VXACE_PAQUETE_INCOMPLETO")
	}
	sidecar, err := iaPrepareAndPublishSidecar(fp.Root, pkg)
	if err != nil {
		return err
	}
	if err = iaCheckEngine(sidecar, pkg); err != nil {
		return err
	}
	_, _, helper, plugin, worker, receiptFile, installDir := vxaceSidecarPaths(fp.Root)
	if !ordinary(helper) || !vxaceAMD64PE(helper) || !ordinary(plugin) || !ordinary(worker) {
		return errors.New("IA_VXACE_COMPONENTES_NO_INSTALADOS")
	}
	helperSHA, err := digestFile(helper)
	if err != nil || helperSHA != pkg.manifest.Files["vxace-helper.exe"] {
		return errors.New("IA_VXACE_HELPER_SHA_INVALIDO")
	}
	pluginSHA, err := digestFile(plugin)
	if err != nil || pluginSHA != pkg.manifest.Files["vxace/IATraductoraVXACE.rb"] {
		return errors.New("IA_VXACE_PLUGIN_SHA_INVALIDO")
	}
	workerSHA, err := digestFile(worker)
	if err != nil || workerSHA != pkg.manifest.Files["IATraductora.exe"] {
		return errors.New("IA_VXACE_WORKER_SHA_INVALIDO")
	}
	target, backupName, targetRel, mode, outputName, maxSize := vxacePaths(fp)
	if !ordinary(target) {
		return errors.New("IA_VXACE_RECURSO_ORIGINAL_INVALIDO")
	}
	currentSHA, err := digestFile(target)
	if err != nil {
		return errors.New("IA_VXACE_RECURSO_HASH_FALLO")
	}
	if err = iaMakeSafeDirs(sidecar, filepath.Join("install", "vxace", "staging")); err != nil {
		return err
	}
	if err = iaMakeSafeDirs(sidecar, filepath.Join("install", "vxace")); err != nil {
		return err
	}
	backup := filepath.Join(installDir, backupName)
	receipt, hasReceipt, err := vxaceReadReceipt(receiptFile)
	if err != nil {
		return err
	}
	originalSHA := currentSHA
	if hasReceipt {
		if receipt.Mode != mode || receipt.TargetRel != targetRel {
			return errors.New("IA_VXACE_RECIBO_OTRO_RECURSO")
		}
		if receipt.Build != vxacePluginBuildID || receipt.PluginSHA != pluginSHA ||
			receipt.HelperSHA != helperSHA || receipt.WorkerSHA != workerSHA {
			return errors.New("IA_VXACE_VERSION_DISTINTA_REVISAR")
		}
		originalSHA = receipt.BeforeSHA
		switch receipt.Status {
		case "INSTALLED":
			if currentSHA != receipt.AfterSHA { return errors.New("IA_VXACE_RECURSO_MODIFICADO") }
		case "PREPARED":
			if currentSHA != receipt.BeforeSHA && currentSHA != receipt.AfterSHA {
				return errors.New("IA_VXACE_RECURSO_MODIFICADO")
			}
		case "RESTORED":
			if currentSHA != receipt.BeforeSHA { return errors.New("IA_VXACE_RECURSO_MODIFICADO") }
		default:
			return errors.New("IA_VXACE_RECIBO_ESTADO_INVALIDO")
		}
		if !ordinary(backup) {
			return errors.New("IA_VXACE_BACKUP_FALTANTE")
		}
		backupSHA, e := digestFile(backup)
		if e != nil || backupSHA != originalSHA {
			return errors.New("IA_VXACE_BACKUP_HASH_MISMATCH")
		}
		if currentSHA == receipt.AfterSHA && (receipt.Status == "INSTALLED" || receipt.Status == "PREPARED") {
			if receipt.Status == "INSTALLED" { return nil }
			receipt.Status = "INSTALLED"
			raw, _ := json.MarshalIndent(receipt, "", "  ")
			return writeAtomic(receiptFile, raw)
		}
	} else {
		if present, e := iaPathIsPresent(backup); e != nil {
			return e
		} else if present {
			backupSHA, hashErr := digestFile(backup)
			if hashErr != nil || backupSHA != currentSHA {
				return errors.New("IA_VXACE_BACKUP_EXISTENTE_NO_COINCIDE")
			}
		} else {
			if err = vxaceEnsureArchiveSpace(fp, true); err != nil { return err }
			if err = vxaceCopyFileNew(target, backup); err != nil { return err }
		}
	}
	if err = vxaceEnsureArchiveSpace(fp, false); err != nil { return err }
	stagingRoot := filepath.Join(installDir, "staging")
	stageDir, err := os.MkdirTemp(stagingRoot, ".vxace-run-")
	if err != nil {
		return errors.New("IA_VXACE_STAGING_NO_DISPONIBLE")
	}
	defer os.RemoveAll(stageDir)
	output := filepath.Join(stageDir, outputName)
	command := exec.Command(helper, "install", "--game-root", fp.Root, "--plugin", plugin, "--output", output)
	command.Dir = fp.Root
	outputBytes, runErr := command.CombinedOutput()
	if runErr != nil {
		message := strings.TrimSpace(string(outputBytes))
		if message == "" {
			message = "IA_VXACE_HELPER_FALLO"
		}
		return errors.New(message)
	}
	var report vxaceHelperReport
	if json.Unmarshal(bytes.TrimSpace(outputBytes), &report) != nil ||
		report.Schema != "servidor-vxace-install-v1" || report.Mode != mode ||
		report.OriginalSHA != currentSHA || report.PluginSHA != pluginSHA ||
		(mode == "rgss3a" && (!report.NonScriptEntriesPreserved || report.ArchiveEntries <= 0)) {
		return errors.New("IA_VXACE_HELPER_REPORTE_INVALIDO")
	}
	if !ordinary(output) {
		return errors.New("IA_VXACE_OUTPUT_NO_GENERADO")
	}
	outputInfo, err := os.Stat(output)
	if err != nil || outputInfo.Size() > maxSize {
		return errors.New("IA_VXACE_OUTPUT_TAMANO_INVALIDO")
	}
	outputSHA, err := digestFile(output)
	if err != nil || outputSHA != report.OutputSHA {
		return errors.New("IA_VXACE_OUTPUT_SHA_INVALIDO")
	}
	// Refuse to replace a game resource if another process changed it while
	// the helper was working on its isolated staging copy.
	latestSHA, err := digestFile(target)
	if err != nil || latestSHA != currentSHA {
		return errors.New("IA_VXACE_RECURSO_CAMBIO_DURANTE_INSTALACION")
	}
	receipt = vxaceReceipt{
		Schema: "ia-traductora-vxace-install-v1",
		BeforeSHA: originalSHA,
		AfterSHA: outputSHA,
		PluginSHA: pluginSHA,
		WorkerSHA: workerSHA,
		HelperSHA: helperSHA,
		Mode: mode,
		TargetRel: targetRel,
		Build: vxacePluginBuildID,
		Status: "PREPARED",
	}
	// Record both known hashes and the verified backup before publishing any bytes.
	receiptBytes, _ := json.MarshalIndent(receipt, "", "  ")
	if err = writeAtomic(receiptFile, receiptBytes); err != nil {
		return errors.New("IA_VXACE_RECIBO_NO_GUARDADO")
	}
	latestSHA, err = digestFile(target)
	if err != nil || latestSHA != currentSHA {
		return errors.New("IA_VXACE_RECURSO_CAMBIO_DURANTE_INSTALACION")
	}
	if err = vxaceAtomicReplaceFrom(output, target, outputSHA, currentSHA); err != nil { return err }
	installedSHA, err := digestFile(target)
	if err != nil || installedSHA != outputSHA {
		// Never overwrite unknown bytes; retain the PREPARED journal for recovery.
		return errors.New("IA_VXACE_POSTCHECK_SHA_FALLO")
	}
	receipt.Status = "INSTALLED"
	receiptBytes, _ = json.MarshalIndent(receipt, "", "  ")
	if err = writeAtomic(receiptFile, receiptBytes); err != nil {
		return errors.New("IA_VXACE_RECIBO_PENDIENTE_VERIFICAR")
	}
	return nil
}

func installedVXAceIdentity(fp vxaceFingerprint, pkg *packageReader) (string, error) {
	if pkg == nil {
		return "", errors.New("IA_VXACE_PAQUETE_INVALIDO")
	}
	sidecar, _, helper, plugin, worker, receiptFile, _ := vxaceSidecarPaths(fp.Root)
	if err := iaCheckEngine(sidecar, pkg); err != nil {
		return "", err
	}
	receipt, ok, err := vxaceReadReceipt(receiptFile)
	if err != nil || !ok || receipt.Status != "INSTALLED" || receipt.Build != vxacePluginBuildID {
		return "", errors.New("IA_VXACE_INSTALACION_NO_VERIFICADA")
	}
	target, _, targetRel, mode, _, _ := vxacePaths(fp)
	if receipt.Mode != mode || receipt.TargetRel != targetRel {
		return "", errors.New("IA_VXACE_INSTALACION_RECURSO_NO_COINCIDE")
	}
	targetSHA, err := digestFile(target)
	if err != nil || targetSHA != receipt.AfterSHA {
		return "", errors.New("IA_VXACE_INSTALACION_RECURSO_MODIFICADO")
	}
	helperSHA, _ := digestFile(helper)
	pluginSHA, _ := digestFile(plugin)
	workerSHA, _ := digestFile(worker)
	if helperSHA != receipt.HelperSHA || pluginSHA != receipt.PluginSHA || workerSHA != receipt.WorkerSHA {
		return "", errors.New("IA_VXACE_INSTALACION_COMPONENTE_MODIFICADO")
	}
	return receipt.Build + " SHA256=" + targetSHA, nil
}

func recoverVXAce(fp vxaceFingerprint) error {
	_, _, _, _, _, receiptFile, installDir := vxaceSidecarPaths(fp.Root)
	if err := vxaceNoSymlinkAncestors(installDir); err != nil { return err }
	if err := vxaceNoSymlinkAncestors(filepath.Dir(receiptFile)); err != nil { return err }
	receipt, ok, err := vxaceReadReceipt(receiptFile)
	if err != nil || !ok {
		return errors.New("IA_VXACE_RECIBO_NO_DISPONIBLE")
	}
	target, backupName, targetRel, mode, _, _ := vxacePaths(fp)
	if receipt.Mode != mode || receipt.TargetRel != targetRel {
		return errors.New("IA_VXACE_RECIBO_OTRO_RECURSO")
	}
	backup := filepath.Join(installDir, backupName)
	if !ordinary(backup) {
		return errors.New("IA_VXACE_BACKUP_FALTANTE")
	}
	backupSHA, err := digestFile(backup)
	if err != nil || backupSHA != receipt.BeforeSHA {
		return errors.New("IA_VXACE_BACKUP_HASH_MISMATCH")
	}
	currentSHA, err := digestFile(target)
	if err != nil {
		return errors.New("IA_VXACE_RECURSO_HASH_FALLO")
	}
	if currentSHA == receipt.BeforeSHA {
		receipt.Status = "RESTORED"
		raw, _ := json.MarshalIndent(receipt, "", "  ")
		return writeAtomic(receiptFile, raw)
	}
	if currentSHA != receipt.AfterSHA || (receipt.Status != "INSTALLED" && receipt.Status != "PREPARED") {
		return errors.New("IA_VXACE_RECURSO_MODIFICADO_NO_RESTAURADO")
	}
	if err = vxaceAtomicReplaceFrom(backup, target, receipt.BeforeSHA, currentSHA); err != nil {
		return err
	}
	restoredSHA, err := digestFile(target)
	if err != nil || restoredSHA != receipt.BeforeSHA {
		return errors.New("IA_VXACE_RESTAURACION_SHA_FALLO")
	}
	receipt.Status = "RESTORED"
	raw, _ := json.MarshalIndent(receipt, "", "  ")
	if err = writeAtomic(receiptFile, raw); err != nil {
		return errors.New("IA_VXACE_RECIBO_RESTAURACION_NO_GUARDADO")
	}
	return nil
}
