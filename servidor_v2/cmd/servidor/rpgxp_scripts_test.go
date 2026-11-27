package main

import (
    "bytes"
    "encoding/json"
    "os"
    "path/filepath"
    "testing"
)
func xpTestRow(t *testing.T,id int64,name,code []byte) []byte{
    t.Helper();packed,e:=xpCompress(code);if e!=nil{t.Fatal(e)}
    return xpEncodeRow(id,name,packed)
}
func xpTestOriginal(t *testing.T) []byte{
    t.Helper()
    b,e:=xpEncodeRows([][]byte{
        xpTestRow(t,340,[]byte("Window_Message"),[]byte("# fixture only")),
        xpTestRow(t,-150,[]byte{0x82,0xa0},[]byte{0x82,0xa0,0xff}),
        xpTestRow(t,22,[]byte(""),[]byte{}),
        xpTestRow(t,44,[]byte("Main"),[]byte("# main not executed")),
    });if e!=nil{t.Fatal(e)};return b
}
func xpTestPlugin(t *testing.T) []byte{
    t.Helper();b,e:=os.ReadFile(filepath.Join("..","..","rpgxp","IATraductoraXP.rb"));if e!=nil{t.Fatal(e)};return b
}
func TestRPGXPScriptsPreserveOriginalRows(t *testing.T){
    original:=xpTestOriginal(t)
    before,e:=xpParseScripts(original);if e!=nil{t.Fatal(e)}
    if before[1].id!=-150{t.Fatal("negative Fixnum damaged")}
    updated,e:=xpPatchScripts(original,xpTestPlugin(t));if e!=nil{t.Fatal(e)}
    after,e:=xpParseScripts(updated);if e!=nil{t.Fatal(e)}
    if len(after)!=5||string(after[3].name)!=xpScriptName||string(after[4].name)!="Main"{t.Fatal("incorrect insertion order")}
    for i,row:=range before{j:=i;if i==3{j++};if !bytes.Equal(row.raw,after[j].raw){t.Fatal("original row changed")}}
    if _,e=xpPatchScripts(updated,xpTestPlugin(t));e==nil{t.Fatal("duplicate translator accepted")}
}
func TestRPGXPScriptsRejectUnsupportedMarshal(t *testing.T){
    original:=xpTestOriginal(t);plugin:=xpTestPlugin(t)
    for _,v:=range [][]byte{original[:len(original)-1],append(append([]byte{},original...),0),{4,8,'I',0},{4,8,'[',6,'o',0},{4,8,'[',6,'@',0}}{
        if _,e:=xpPatchScripts(v,plugin);e==nil{t.Fatal("malformed or executable Marshal accepted")}
    }
    broken,e:=xpEncodeRows([][]byte{xpEncodeRow(1,[]byte("Main"),[]byte("not zlib"))});if e!=nil{t.Fatal(e)}
    if _,e=xpPatchScripts(broken,plugin);e==nil{t.Fatal("invalid compression accepted")}
    duplicate,e:=xpEncodeRows([][]byte{xpTestRow(t,1,[]byte("Main"),[]byte{}),xpTestRow(t,2,[]byte("Main"),[]byte{})});if e!=nil{t.Fatal(e)}
    if _,e=xpPatchScripts(duplicate,plugin);e==nil{t.Fatal("ambiguous Main accepted")}
    if _,e=xpPatchScripts(original,[]byte("unknown code"));e==nil{t.Fatal("unknown plugin accepted")}
}
func TestRPGXPStageBackupAndCandidate(t *testing.T){
    exe:=rpgxpFixture(t)
    target:=filepath.Join(filepath.Dir(exe),"Data","Scripts.rxdata")
    original:=xpTestOriginal(t)
    if e:=os.WriteFile(target,original,0600);e!=nil{t.Fatal(e)}
    parent:=t.TempDir()
    stage,e:=xpStageScripts(exe,parent,xpTestPlugin(t));if e!=nil{t.Fatal(e)}
    backup,e:=os.ReadFile(filepath.Join(stage,"Scripts.original.rxdata"));if e!=nil{t.Fatal(e)}
    candidate,e:=os.ReadFile(filepath.Join(stage,"Scripts.candidate.rxdata"));if e!=nil{t.Fatal(e)}
    raw,e:=os.ReadFile(filepath.Join(stage,"receipt.json"));if e!=nil{t.Fatal(e)}
    var receipt xpStageReceipt
    if e=json.Unmarshal(raw,&receipt);e!=nil{t.Fatal(e)}
    current,e:=os.ReadFile(target);if e!=nil{t.Fatal(e)}
    if !bytes.Equal(original,backup)||!bytes.Equal(current,original)||hash(backup)!=receipt.Before||hash(candidate)!=receipt.After||hash(xpTestPlugin(t))!=receipt.Plugin{t.Fatal("stage/source integrity failed")}
    if bytes.Equal(candidate,original){t.Fatal("candidate unchanged")}
    if _,e=xpStageScripts(exe,filepath.Dir(exe),xpTestPlugin(t));e==nil{t.Fatal("stage inside game accepted")}
    if _,e=os.Stat(filepath.Join(filepath.Dir(exe),"IA Traductora"));!os.IsNotExist(e){t.Fatal("sidecar created by lab stage")}
}
func TestRPGXPInflateRejectsTrailingAndOverflow(t *testing.T){
    packed,e:=xpCompress(bytes.Repeat([]byte("a"),1024));if e!=nil{t.Fatal(e)}
    if _,e=xpInflate(packed,10);e==nil{t.Fatal("expansion limit failed")}
    if _,e=xpInflate(append(packed,1),2048);e==nil{t.Fatal("trailing compressed data accepted")}
}

func TestRPGXPPluginHeaderExactLFAndCRLF(t *testing.T){
    original:=xpTestOriginal(t)
    for _,eol:=range []string{"\n","\r\n"}{
        plugin:=[]byte(xpScriptMarker+eol+"# test"+eol)
        staged,e:=xpPatchScripts(original,plugin);if e!=nil{t.Fatal(e)}
        rows,e:=xpParseScripts(staged);if e!=nil{t.Fatal(e)}
        code,e:=xpInflate(rows[3].packed,int64(len(plugin)));if e!=nil||!bytes.Equal(code,plugin){t.Fatal("plugin bytes normalized or changed")}
    }
    for _,suffix:=range []string{"X\n","\rX","\r",""}{
        if _,e:=xpPatchScripts(original,[]byte(xpScriptMarker+suffix));e==nil{t.Fatal("ambiguous marker accepted")}
    }
}
