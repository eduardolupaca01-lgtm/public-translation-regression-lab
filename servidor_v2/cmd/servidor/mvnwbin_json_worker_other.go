//go:build !windows

package main

import "os/exec"

func mvJSONConfigureCommand(cmd *exec.Cmd){}
