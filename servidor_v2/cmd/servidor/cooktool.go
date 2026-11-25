package main

// Cook Tool / Halva identification only. Never open package payloads,
// execute the bootstrapper, alter caches, or claim that a packed game is
// installable. This preflight is shared by the normal RPG installer,
// recovery and the read-only CLI.
import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

const (
	cookToolPackedCode = "IA_RPG_HALVA_REQUIERE_EXPORTACION"
	cookToolUnsafeCode = "IA_RPG_HALVA_ESTRUCTURA_INVALIDA"
	cookToolEntryBudget = 512
	cookToolMaxDepth = 3
)

type cookToolInventory struct {
	halva, halva2, other int
	partial bool
}

func (s cookToolInventory) summary() string {
	return fmt.Sprintf("halva=%d halva2=%d otros=%d inventario_parcial=%t", s.halva,s.halva2,s.other,s.partial)
}

// A bounded directory inventory; read only metadata and extensions. The
// config might contain confidential settings and is deliberately not read.
func cookToolScan(dir string, depth int, remaining *int, result *cookToolInventory) {
	if depth>cookToolMaxDepth||*remaining<=0{result.partial=true;return}
	st,err:=os.Lstat(dir)
	if err!=nil||!st.IsDir()||st.Mode()&os.ModeSymlink!=0{result.partial=true;return}
	f,err:=os.Open(dir)
	if err!=nil{result.partial=true;return}
	entries,err:=f.ReadDir(*remaining+1)
	_ = f.Close()
	if err!=nil&&!errors.Is(err,io.EOF){result.partial=true}
	if len(entries)>*remaining{entries=entries[:*remaining];result.partial=true}
	for _,entry:=range entries{
		if *remaining<=0{result.partial=true;return}
		*remaining = *remaining-1
		full:=filepath.Join(dir,entry.Name())
		info,e:=os.Lstat(full)
		if e!=nil||info.Mode()&os.ModeSymlink!=0{result.partial=true;continue}
		if info.IsDir(){cookToolScan(full,depth+1,remaining,result);continue}
		if !info.Mode().IsRegular(){result.partial=true;continue}
		switch strings.ToLower(filepath.Ext(entry.Name())){
		case ".halva": result.halva++
		case ".halva2": result.halva2++
		default: result.other++
		}
	}
}

// Marker pair is required, regardless of the launcher name (customizable by
// the publisher). Do not treat an arbitrary GamePackages folder as Halva.
func cookToolPreflight(root string) error {
	config:=filepath.Join(root,"GameConfig.sbcf")
	packages:=filepath.Join(root,"GamePackages")
	cfg,ce:=os.Lstat(config)
	pkg,pe:=os.Lstat(packages)
	if os.IsNotExist(ce)||os.IsNotExist(pe){return nil}
	if ce!=nil||pe!=nil{return errors.New(cookToolUnsafeCode)}
	if !cfg.Mode().IsRegular()||cfg.Mode()&os.ModeSymlink!=0||
		!pkg.IsDir()||pkg.Mode()&os.ModeSymlink!=0{return errors.New(cookToolUnsafeCode)}
	budget:=cookToolEntryBudget
	result:=cookToolInventory{}
	cookToolScan(packages,0,&budget,&result)
	return fmt.Errorf("%s: %s",cookToolPackedCode,result.summary())
}
