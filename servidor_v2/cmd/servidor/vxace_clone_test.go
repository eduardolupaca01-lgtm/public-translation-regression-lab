package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestVXAceCloneOriginalPreparedAndInstalled(t *testing.T){
	for _,published:=range []bool{false,true}{
		exe:=vxaceFixture(t,true)
		fp,matched,e:=detectVXAce(exe)
		if e!=nil||!matched{t.Fatalf("fixture: %v",e)}
		original,e:=os.ReadFile(fp.ArchiveFile);if e!=nil{t.Fatal(e)}
		after:=append(append([]byte{},original...),[]byte("patched fixture")...)
		sidecar,_,_,_,_,receiptFile,installDir:=vxaceSidecarPaths(fp.Root)
		if e=os.MkdirAll(installDir,0700);e!=nil{t.Fatal(e)}
		owner:=ownerManifest{Schema:ownerSchema,Product:"SERVIDOR-IA-TRADUCTORA",WorkerSHA:hash([]byte("worker")),PluginSHA:hash([]byte("js")),
			VXACEPluginSHA:hash([]byte("ruby")),VXACEHelperSHA:hash([]byte("helper")),VXACEPluginBuild:vxacePluginBuildID}
		raw,_:=json.Marshal(owner)
		if e=os.WriteFile(filepath.Join(sidecar,"owner-v1.json"),raw,0600);e!=nil{t.Fatal(e)}
		backup:=filepath.Join(installDir,"original-Game.rgss3a")
		if e=os.WriteFile(backup,original,0600);e!=nil{t.Fatal(e)}
		receipt:=vxaceReceipt{Schema:"ia-traductora-vxace-install-v1",BeforeSHA:hash(original),AfterSHA:hash(after),PluginSHA:owner.VXACEPluginSHA,
			WorkerSHA:owner.WorkerSHA,HelperSHA:owner.VXACEHelperSHA,Mode:"rgss3a",TargetRel:"Game.rgss3a",Build:vxacePluginBuildID,Status:"PREPARED"}
		if published{receipt.Status="INSTALLED";if e=os.WriteFile(fp.ArchiveFile,after,0600);e!=nil{t.Fatal(e)}}
		raw,_=json.Marshal(receipt)
		if e=os.WriteFile(receiptFile,raw,0600);e!=nil{t.Fatal(e)}
		source,sha,current,e:=vxaceCloneOriginal(fp)
		if e!=nil||sha!=hash(original){t.Fatalf("archive source: %v",e)}
		if published{
			if source!=backup||current!=hash(after){t.Fatal("must copy original backup for installed source")}
		}else if source!=fp.ArchiveFile||current!=hash(original){t.Fatal("must use unchanged original for failed source")}
		if e=os.WriteFile(backup,[]byte("altered"),0600);e!=nil{t.Fatal(e)}
		if _,_,_,e=vxaceCloneOriginal(fp);e==nil{t.Fatal("altered backup accepted")}
	}
}

func TestVXAceClonePlanPreservesSaveAndExcludesOnlyKnownFiles(t *testing.T){
	exe:=vxaceFixture(t,true)
	fp,matched,e:=detectVXAce(exe)
	if e!=nil||!matched{t.Fatalf("fixture: %v",e)}
	save:=filepath.Join(fp.Root,"Save777.rvdata2")
	if e=os.WriteFile(save,[]byte("save fixture"),0600);e!=nil{t.Fatal(e)}
	entries,_,e:=vxaceClonePlan(fp);if e!=nil{t.Fatal(e)}
	found:=false
	for _,entry:=range entries{
		if entry.rel=="Save777.rvdata2"{found=true}
		if entry.rel=="Game.exe"||entry.rel=="Game.rgss3a"{t.Fatal("must defer publication of executable and archive")}
	}
	if !found{t.Fatal("save omitted")}
	outside:=filepath.Join(t.TempDir(),"foreign")
	if e=os.WriteFile(outside,[]byte("foreign"),0600);e!=nil{t.Fatal(e)}
	link:=filepath.Join(fp.Root,"linked")
	if e=os.Symlink(outside,link);e==nil{
		if _,_,e=vxaceClonePlan(fp);e==nil{t.Fatal("symlink accepted")}
	}
}
