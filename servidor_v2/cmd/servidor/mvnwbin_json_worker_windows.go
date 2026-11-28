//go:build windows

package main

import(
 "os/exec"
 "syscall"
)

// Use the normal console bootloader without a secondary console window.
// This does not change the token, ACL, antivirus, or any Windows policy.
func mvJSONConfigureCommand(cmd *exec.Cmd){
 cmd.SysProcAttr=&syscall.SysProcAttr{HideWindow:true,CreationFlags:0x08000000}
}
