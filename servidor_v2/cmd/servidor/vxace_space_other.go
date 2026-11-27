//go:build !windows

package main

// The shipped installer is Windows-only. Non-Windows development tests
// still exercise the bounded streaming/copying and atomic rollback paths.
func vxaceCheckDiskSpace(root string, needed uint64) error { return nil }
