package main

// Read-only command-line companion to the native Windows catalog.
// The existing V95 translator is NOT replaced by this tool.
import (
    "encoding/json"
    "flag"
    "fmt"
    "os"
    "path/filepath"
    "github.com/eduardolupaca01-lgtm/public-translation-regression-lab/tenshixgame-next/internal/engine"
    "github.com/eduardolupaca01-lgtm/public-translation-regression-lab/tenshixgame-next/internal/portable"
)
func main(){
    catalog:=flag.Bool("catalogo",false,"mostrar los 17 grupos (no certificaciones)")
    family:=flag.String("familia","","familia elegida: rpg-maker, renpy, unity...")
    game:=flag.String("juego","","ruta del EXE, JAR, SWF o carpeta del juego")
    flag.Parse()
    encoder:=json.NewEncoder(os.Stdout)
    encoder.SetIndent("","  ")
    if *catalog {
        if err:=encoder.Encode(engine.CloneCatalog());err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}
        return
    }
    if *family==""||*game=="" {
        fmt.Fprintln(os.Stderr,"Uso: Tenshixgame-Detector.exe -catalogo  o  -familia rpg-maker -juego C:\\Juegos\\Copia\\Game.exe")
        os.Exit(2)
    }
    result,err:=engine.Inspect(*game,*family)
    if err!=nil{
        fmt.Fprintln(os.Stderr,"Inspección segura bloqueada:",err)
        os.Exit(3)
    }
    root:=*game
    if st,e:=os.Stat(root);e==nil&&!st.IsDir(){root=filepath.Dir(root)}
    audit:=portable.AuditRoot(root)
    payload:=struct{
        engine.Result
        InstalacionPortable portable.Report `json:"InstalacionPortable"`
    }{Result:result,InstalacionPortable:audit}
    if err=encoder.Encode(payload);err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}
    if result.Status!="identified"{os.Exit(3)}
}
