package main

import (
	"os"
	"path/filepath"
	"testing"
)

func vxacePEFixture() []byte {
	data := make([]byte, 128)
	copy(data[:2], []byte("MZ"))
	data[0x3c] = 64
	copy(data[64:68], []byte{'P', 'E', 0, 0})
	data[68] = 0x4c
	data[69] = 0x01
	return data
}

func vxaceFixture(t *testing.T, packed bool) string {
	t.Helper()
	root := filepath.Join(t.TempDir(), "VX Ace 日本語")
	if err := os.MkdirAll(root, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "Game.exe"), vxacePEFixture(), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "RGSS301.dll"), vxacePEFixture(), 0600); err != nil {
		t.Fatal(err)
	}
	ini := "[Game]\nLibrary=RGSS301.dll\nScripts=Data\\Scripts.rvdata2\nTitle=Prueba VX Ace\n"
	if err := os.WriteFile(filepath.Join(root, "Game.ini"), []byte(ini), 0600); err != nil {
		t.Fatal(err)
	}
	if packed {
		if err := os.WriteFile(filepath.Join(root, "Game.rgss3a"), []byte{'R', 'G', 'S', 'S', 'A', 'D', 0, 3, 0, 0, 0, 0}, 0600); err != nil {
			t.Fatal(err)
		}
	} else {
		data := filepath.Join(root, "Data")
		if err := os.MkdirAll(data, 0700); err != nil {
			t.Fatal(err)
		}
		for _, name := range []string{"Scripts.rvdata2", "System.rvdata2", "MapInfos.rvdata2"} {
			if err := os.WriteFile(filepath.Join(data, name), []byte{4, 8, 0x00, 0x00}, 0600); err != nil {
				t.Fatal(err)
			}
		}
	}
	return filepath.Join(root, "Game.exe")
}

func TestDetectVXAceLooseProject(t *testing.T) {
	exe := vxaceFixture(t, false)
	fp, matched, err := detectVXAce(exe)
	if err != nil || !matched {
		t.Fatalf("VX Ace loose project not recognized: matched=%v err=%v", matched, err)
	}
	if fp.Packed || fp.ScriptsFile == "" || fp.DataDir == "" || fp.Title != "Prueba VX Ace" {
		t.Fatalf("unexpected fingerprint: %+v", fp)
	}
}

func TestDetectVXAcePackedArchiveHeader(t *testing.T) {
	exe := vxaceFixture(t, true)
	fp, matched, err := detectVXAce(exe)
	if err != nil || !matched {
		t.Fatalf("VX Ace packed project not recognized: matched=%v err=%v", matched, err)
	}
	if !fp.Packed || fp.ArchiveFile == "" {
		t.Fatalf("packed archive not recorded: %+v", fp)
	}
}

func TestVXAceDoesNotMisclassifyOtherEngines(t *testing.T) {
	game := t.TempDir()
	exe := filepath.Join(game, "Game.exe")
	if err := os.WriteFile(exe, []byte("not PE"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, matched, err := detectVXAce(exe); matched || err != nil {
		t.Fatalf("non-VX Ace was claimed: matched=%v err=%v", matched, err)
	}
}

func TestVXAceRejectsBadArchiveBeforeInstall(t *testing.T) {
	exe := vxaceFixture(t, true)
	archive := filepath.Join(filepath.Dir(exe), "Game.rgss3a")
	if err := os.WriteFile(archive, []byte("NOT-RGSS3A"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, matched, err := detectVXAce(exe); !matched || err == nil {
		t.Fatalf("bad archive did not fail closed: matched=%v err=%v", matched, err)
	}
}

func TestVXAceRejectsSymlinkedScripts(t *testing.T) {
	if os.Getenv("GOOS") == "windows" {
		t.Skip("symlink creation requires elevated privileges on some Windows runners")
	}
	exe := vxaceFixture(t, false)
	root := filepath.Dir(exe)
	data := filepath.Join(root, "Data")
	scripts := filepath.Join(data, "Scripts.rvdata2")
	if err := os.Remove(scripts); err != nil {
		t.Fatal(err)
	}
	outside := filepath.Join(t.TempDir(), "Scripts.rvdata2")
	if err := os.WriteFile(outside, []byte{4, 8, 0, 0}, 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, scripts); err != nil {
		t.Skipf("symlink unavailable: %v", err)
	}
	if _, matched, err := detectVXAce(exe); !matched || err == nil {
		t.Fatalf("symlinked Scripts.rvdata2 was accepted: matched=%v err=%v", matched, err)
	}
}

func TestVXAceRejectsNonMarshalLooseData(t *testing.T) {
	exe := vxaceFixture(t, false)
	scripts := filepath.Join(filepath.Dir(exe), "Data", "Scripts.rvdata2")
	if err := os.WriteFile(scripts, []byte("not marshal"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, matched, err := detectVXAce(exe); !matched || err == nil {
		t.Fatalf("non-Marshal Scripts.rvdata2 was accepted: matched=%v err=%v", matched, err)
	}
}
