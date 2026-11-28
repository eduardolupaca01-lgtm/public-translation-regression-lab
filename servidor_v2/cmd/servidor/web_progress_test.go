package main

import (
 "path/filepath"
 "strings"
 "testing"
)

func TestWebProgressStopsAtActualFailure(t *testing.T){
 var events []string
 report:=func(s string){events=append(events,s)}
 if _,e:=webCloneFromEXEProgress(filepath.Join(t.TempDir(),"missing.exe"),"",nil,report);e==nil{t.Fatal("missing source accepted")}
 if len(events)!=1||!strings.Contains(events[0],"IA_WEB_EXE_ANALISIS"){t.Fatalf("unexpected EXE progress: %v",events)}
 events=nil
 if _,e:=webCloneInstallProgress(t.TempDir(),"",nil,report);e==nil{t.Fatal("incomplete frontend accepted")}
 if len(events)!=1||!strings.Contains(events[0],"IA_WEB_VALIDANDO_RECURSOS"){t.Fatalf("unexpected folder progress: %v",events)}
}
