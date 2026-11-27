//go:build windows

package main

import (
	"errors"
	"syscall"
	"unsafe"
)

// Query the caller's available bytes on the actual game volume (quota-aware).
// No files are opened for writing and no space is allocated by this check.
func vxaceCheckDiskSpace(root string, needed uint64) error {
	path, err := syscall.UTF16PtrFromString(root)
	if err != nil { return errors.New("IA_VXACE_ESPACIO_NO_VERIFICADO") }
	proc := syscall.NewLazyDLL("kernel32.dll").NewProc("GetDiskFreeSpaceExW")
	var available uint64
	ok, _, _ := proc.Call(uintptr(unsafe.Pointer(path)), uintptr(unsafe.Pointer(&available)), 0, 0)
	if ok == 0 { return errors.New("IA_VXACE_ESPACIO_NO_VERIFICADO") }
	if available < needed { return errors.New("IA_VXACE_ESPACIO_INSUFICIENTE") }
	return nil
}
