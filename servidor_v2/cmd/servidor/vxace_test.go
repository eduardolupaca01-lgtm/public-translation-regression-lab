package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
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

func TestVXAceLargePackedArchiveSizeGate(t *testing.T) {
	exe := vxaceFixture(t, true)
	archive := filepath.Join(filepath.Dir(exe), "Game.rgss3a")
	// Header-only detection is intentional here; the real CI acceptance
	// separately builds and processes a valid archive larger than this.
	if err := os.Truncate(archive, 1216546*1024); err != nil { t.Fatal(err) }
	fp, matched, err := detectVXAce(exe)
	if err != nil || !matched || !fp.Packed {
		t.Fatalf("large packed game rejected: %v %v", matched, err)
	}
	if err = os.Truncate(archive, vxaceMaxArchive+1); err != nil { t.Fatal(err) }
	if _, matched, err = detectVXAce(exe); !matched || err == nil {
		t.Fatal("oversized legacy archive was accepted")
	}
}

func TestVXAceArchiveSpaceIncludesBackupAndStaging(t *testing.T) {
	const size = int64(1216546*1024)
	with := vxaceArchiveSpaceNeeded(size,true)
	without := vxaceArchiveSpaceNeeded(size,false)
	if with-without != uint64(size) || without <= 2*uint64(size) {
		t.Fatal("archive space estimate omitted backup or staging")
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


func TestVXAceStandardSystemRuntimeAndEmptyRTP(t *testing.T) {
	exe := vxaceFixture(t, false)
	root := filepath.Dir(exe)
	if err := os.Mkdir(filepath.Join(root, "System"), 0700); err != nil { t.Fatal(err) }
	if err := os.Rename(filepath.Join(root, "RGSS301.dll"), filepath.Join(root, "System", "RGSS301.dll")); err != nil { t.Fatal(err) }
	ini := "[Game]\r\nRTP=\r\nLibrary=System\\RGSS301.dll\r\nScripts=Data\\Scripts.rvdata2\r\nTitle=日本語\r\n"
	if err := os.WriteFile(filepath.Join(root,"Game.ini"), []byte(ini), 0600); err != nil { t.Fatal(err) }
	fp, matched, err := detectVXAce(exe)
	if !matched || err != nil || filepath.Base(filepath.Dir(fp.Library)) != "System" { t.Fatalf("standard VX Ace: %v %v %+v", matched, err, fp) }
}

func TestVXAceRecoveryAfterPreparedJournal(t *testing.T) {
	for _, published := range []bool{false,true} {
		t.Run(map[bool]string{false:"before_replace",true:"after_replace"}[published],func(t *testing.T){
			exe := vxaceFixture(t,false)
			fp, matched, err := detectVXAce(exe)
			if err != nil || !matched { t.Fatalf("fixture: %v",err) }
			_,_,_,_,_,receiptFile,installDir := vxaceSidecarPaths(fp.Root)
			if err = os.MkdirAll(installDir,0700);err != nil {t.Fatal(err)}
			original,err := os.ReadFile(fp.ScriptsFile);if err != nil{t.Fatal(err)}
			patched := append(append([]byte{},original...),[]byte("synthetic patched")...)
			backup:=filepath.Join(installDir,"original-Scripts.rvdata2")
			if err=os.WriteFile(backup,original,0600);err!=nil{t.Fatal(err)}
			receipt := vxaceReceipt{Schema:"ia-traductora-vxace-install-v1",BeforeSHA:hash(original),AfterSHA:hash(patched),PluginSHA:hash([]byte("plugin")),WorkerSHA:hash([]byte("worker")),HelperSHA:hash([]byte("helper")),Mode:"loose",TargetRel:"Data/Scripts.rvdata2",Build:vxacePluginBuildID,Status:"PREPARED"}
			raw,_:=json.Marshal(receipt)
			if err=os.WriteFile(receiptFile,raw,0600);err!=nil{t.Fatal(err)}
			if published {if err=os.WriteFile(fp.ScriptsFile,patched,0600);err!=nil{t.Fatal(err)}}
			save:=filepath.Join(fp.Root,"Save01.rvdata2")
			if err=os.WriteFile(save,[]byte("player save"),0600);err!=nil{t.Fatal(err)}
			for i:=0;i<2;i++{if err=recoverVXAce(fp);err!=nil{t.Fatal(err)}}
			restored,_:=os.ReadFile(fp.ScriptsFile)
			if hash(restored)!=hash(original){t.Fatal("original not restored")}
			saved,_:=os.ReadFile(save)
			if string(saved)!="player save"{t.Fatal("save modified")}
			got,ok,err:=vxaceReadReceipt(receiptFile)
			if err!=nil||!ok||got.Status!="RESTORED"{t.Fatalf("receipt: %+v %v",got,err)}
		})
	}
}

func TestVXAceReplacementRetriesAndRefusesChangedTarget(t *testing.T){
	for _,change:=range []bool{false,true}{
		t.Run(map[bool]string{false:"transient",true:"changed"}[change],func(t *testing.T){
			dir:=t.TempDir()
			src,dst:=filepath.Join(dir,"prepared"),filepath.Join(dir,"Game.rgss3a")
			before,after:=[]byte("original archive"),[]byte("patched archive")
			if e:=os.WriteFile(src,after,0600);e!=nil{t.Fatal(e)}
			if e:=os.WriteFile(dst,before,0600);e!=nil{t.Fatal(e)}
			move,sleep:=vxaceMoveReplacement,vxaceReplacementSleep
			t.Cleanup(func(){vxaceMoveReplacement=move;vxaceReplacementSleep=sleep})
			calls:=0
			vxaceMoveReplacement=func(s,d string,info os.FileInfo)error{
				calls++
				if calls==1{return os.ErrPermission}
				return move(s,d,info)
			}
			vxaceReplacementSleep=func(time.Duration){
				if change{
					if e:=os.WriteFile(dst,[]byte("external modification"),0600);e!=nil{t.Fatal(e)}
				}
			}
			e:=vxaceAtomicReplaceFrom(src,dst,hash(after),hash(before))
			raw,readErr:=os.ReadFile(dst);if readErr!=nil{t.Fatal(readErr)}
			if change{
				if e==nil||e.Error()!="IA_VXACE_RECURSO_CAMBIO_DURANTE_REEMPLAZO"||calls!=1||string(raw)!="external modification"{t.Fatalf("changed target overwritten: %v %d",e,calls)}
			}else if e!=nil||calls!=2||string(raw)!=string(after){t.Fatalf("retry failed: %v %d",e,calls)}
			got,_:=os.ReadFile(src);if string(got)!=string(after){t.Fatal("verified source changed")}
		})
	}
}

func TestVXAceReplacementRejectsBadPreparedHash(t *testing.T){
	dir:=t.TempDir()
	src,dst:=filepath.Join(dir,"prepared"),filepath.Join(dir,"Game.rgss3a")
	if e:=os.WriteFile(src,[]byte("corrupted prepared"),0600);e!=nil{t.Fatal(e)}
	if e:=os.WriteFile(dst,[]byte("original"),0600);e!=nil{t.Fatal(e)}
	e:=vxaceAtomicReplaceFrom(src,dst,hash([]byte("approved prepared")),hash([]byte("original")))
	if e==nil||e.Error()!="IA_VXACE_REPLACE_TEMP_SHA_INVALIDO"{t.Fatalf("unexpected error: %v",e)}
	got,_:=os.ReadFile(dst);if string(got)!="original"{t.Fatal("original changed")}
}
