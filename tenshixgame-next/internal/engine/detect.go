package engine

import (
    "bytes"
    "errors"
    "fmt"
    "io"
    "os"
    "path/filepath"
    "regexp"
    "strings"
)

// Inspect only reads bounded, ordinary files inside a selected copy of a game.
// It NEVER runs Game.exe, installs plugins, starts an AI worker or touches saves.
type Result struct {
    SelectedFamily string
    FamilyName string
    DetectedEngine string
    EngineVersion string
    Status string
    Evidence []string
    Explanation string
    CanInstall bool
    GameLabel string
}
type candidate struct {
    engine string
    version string
    signals []string
    ambiguous bool
}
const maxSmallFile int64=2<<20
const maxProbeEntries=512

func isInside(root,full string) bool {
    rel,err:=filepath.Rel(root,full)
    if err!=nil||rel==".."||filepath.IsAbs(rel){return false}
    return !strings.HasPrefix(rel,".."+string(filepath.Separator))
}
func ordinaryFile(root,rel string) bool {
    full:=filepath.Join(root,filepath.FromSlash(rel))
    if !isInside(root,full){return false}
    st,err:=os.Lstat(full)
    if err!=nil||!st.Mode().IsRegular()||st.Mode()&os.ModeSymlink!=0{return false}
    canonical,err:=filepath.EvalSymlinks(full)
    if err!=nil{return false}
    canonicalRoot,err:=filepath.EvalSymlinks(root)
    return err==nil&&isInside(canonicalRoot,canonical)
}
func ordinaryDir(root,rel string)bool {
    full:=filepath.Join(root,filepath.FromSlash(rel))
    if !isInside(root,full){return false}
    st,err:=os.Lstat(full)
    if err!=nil||!st.IsDir()||st.Mode()&os.ModeSymlink!=0{return false}
    actual,err:=filepath.EvalSymlinks(full)
    if err!=nil{return false}
    canonicalRoot,err:=filepath.EvalSymlinks(root)
    return err==nil&&isInside(canonicalRoot,actual)
}
func boundedRead(root,rel string) ([]byte,error) {
    if !ordinaryFile(root,rel){return nil,errors.New("archivo no ordinario o fuera del juego")}
    path:=filepath.Join(root,filepath.FromSlash(rel))
    st,err:=os.Stat(path)
    if err!=nil{return nil,err}
    if st.Size()>maxSmallFile{return nil,errors.New("archivo excede límite de lectura")}
    f,err:=os.Open(path)
    if err!=nil{return nil,err}
    defer f.Close()
    return io.ReadAll(io.LimitReader(f,maxSmallFile+1))
}
func gameLocation(value string)(root, selectedFile string, err error){
    if strings.TrimSpace(value)==""{return "","",errors.New("selecciona un archivo EXE o carpeta")}
    absolute,e:=filepath.Abs(value)
    if e!=nil{return "","",e}
    absolute=filepath.Clean(absolute)
    st,e:=os.Lstat(absolute)
    if e!=nil{return "","",e}
    if st.Mode()&os.ModeSymlink!=0{return "","",errors.New("selección enlazada no permitida")}
    if st.IsDir(){root=absolute}else if st.Mode().IsRegular(){
        ext:=strings.ToLower(filepath.Ext(absolute))
        if ext!=".exe"&&ext!=".jar"&&ext!=".swf"{
            return "","",errors.New("selecciona el EXE, JAR, SWF o carpeta del juego")
        }
        selectedFile=filepath.Base(absolute)
        root=filepath.Dir(absolute)
    }else{return "","",errors.New("selección no ordinaria")}
    // Root itself must be an ordinary directory. Windows 8.3 aliases,
    // drive spellings and platform-managed parent junctions are compared
    // by file ID, not by textual representation (TX200 Windows regression).
    originalInfo,e:=os.Lstat(root)
    if e!=nil||!originalInfo.IsDir()||originalInfo.Mode()&os.ModeSymlink!=0{
        return "","",errors.New("raíz de juego enlazada o inexistente")
    }
    canonical,e:=filepath.EvalSymlinks(root)
    if e!=nil{return "","",e}
    realInfo,e:=os.Stat(canonical)
    if e!=nil||!os.SameFile(originalInfo,realInfo){
        return "","",errors.New("ruta de juego no verificable")
    }
    return root,selectedFile,nil
}
var (
    reRPGVersion=regexp.MustCompile(`(?i)Utils\.RPGMAKER_VERSION\s*=\s*['"]([0-9]+\.[0-9]+(?:\.[0-9]+)?)['"]`)
    reRGSS=regexp.MustCompile(`(?im)^\s*Library\s*=\s*RGSS([123])\d+[a-z]?(?:\.dll)\s*$`)
    reRenpy=regexp.MustCompile(`(?m)version_tuple\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)`)
)
func versionFromJS(root,rel string)string{
    b,e:=boundedRead(root,rel)
    if e!=nil{return "no identificada"}
    m:=reRPGVersion.FindSubmatch(b)
    if len(m)==2{return string(m[1])}
    return "no identificada"
}
func rpg(root string)[]candidate {
    result:=[]candidate{}
    for _,prefix:=range []string{"","www/"} {
        common:=prefix+"data/System.json"
        reg:=prefix+"js/plugins.js"
        if !ordinaryFile(root,common)||!ordinaryFile(root,reg){continue}
        mv:=prefix+"js/rpg_core.js"
        mgr:=prefix+"js/rpg_managers.js"
        if ordinaryFile(root,mv)&&ordinaryFile(root,mgr){
            result=append(result,candidate{engine:"RPG Maker MV",version:versionFromJS(root,mv),
               signals:[]string{mv,mgr,common,reg}})
        }
        mz:=prefix+"js/rmmz_core.js"
        mzmgr:=prefix+"js/rmmz_managers.js"
        if ordinaryFile(root,mz)&&ordinaryFile(root,mzmgr){
            result=append(result,candidate{engine:"RPG Maker MZ",version:versionFromJS(root,mz),
               signals:[]string{mz,mzmgr,common,reg}})
        }
    }
    ini,err:=boundedRead(root,"Game.ini")
    if err==nil{
        match:=reRGSS.FindSubmatch(ini)
        if len(match)==2{
            typeInfo:=map[string]struct{title,ext,archive string}{
                "1":{"RPG Maker XP","Data/Actors.rxdata","Game.rgssad"},
                "2":{"RPG Maker VX","Data/Actors.rvdata","Game.rgss2a"},
                "3":{"RPG Maker VX Ace","Data/Actors.rvdata2","Game.rgss3a"},
            }
            t:=typeInfo[string(match[1])]
            if ordinaryFile(root,t.ext)||ordinaryFile(root,t.archive){
                result=append(result,candidate{engine:t.title,version:"revisión RGSS no identificada",
                   signals:[]string{"Game.ini",t.ext+" / "+t.archive}})
            }
        }
    }
    if ordinaryFile(root,"RPG_RT.ldb")&&ordinaryFile(root,"RPG_RT.lmt"){
        result=append(result,candidate{engine:"RPG Maker 2000/2003",version:"subtipo no distinguible por estas firmas",
            signals:[]string{"RPG_RT.ldb","RPG_RT.lmt"},ambiguous:true})
    }
    return result
}
func listSafe(root string)[]os.DirEntry {
    es,err:=os.ReadDir(root)
    if err!=nil||len(es)>maxProbeEntries{return nil}
    return es
}
func renpy(root string)[]candidate{
    if !ordinaryDir(root,"renpy")||!ordinaryDir(root,"game"){return nil}
    version:="no identificada"
    if b,e:=boundedRead(root,"renpy/version.py");e==nil{
        if m:=reRenpy.FindSubmatch(b);len(m)==4{
            version=fmt.Sprintf("%s.%s.%s",m[1],m[2],m[3])
        }
    }
    return []candidate{{engine:"Ren'Py",version:version,
        signals:[]string{"renpy/","game/"}}}
}
func godot(root,sel string)[]candidate{
    if sel!=""{
        stem:=strings.TrimSuffix(sel,filepath.Ext(sel))
        if ordinaryFile(root,stem+".pck"){
            return []candidate{{engine:"Godot",version:"no identificada",signals:[]string{stem+".pck"}}}
        }
    }
    if ordinaryFile(root,"project.godot"){
        return []candidate{{engine:"Godot (proyecto)",version:"no identificada",signals:[]string{"project.godot"}}}
    }
    return nil
}
func unity(root,sel string)[]candidate {
    if !ordinaryFile(root,"UnityPlayer.dll"){return nil}
    if sel!=""{
        base:=strings.TrimSuffix(sel,filepath.Ext(sel))+"_Data"
        if ordinaryDir(root,base)&&ordinaryFile(root,base+"/globalgamemanagers"){
            return []candidate{{engine:"Unity",version:"no identificada",
                signals:[]string{"UnityPlayer.dll",base+"/globalgamemanagers"}}}
        }
    }
    for _,d:=range listSafe(root){
        if strings.HasSuffix(strings.ToLower(d.Name()),"_data")&&ordinaryDir(root,d.Name())&&ordinaryFile(root,d.Name()+"/globalgamemanagers"){
            return []candidate{{engine:"Unity",version:"no identificada",
                signals:[]string{"UnityPlayer.dll",d.Name()+"/globalgamemanagers"}}}
        }
    }
    return nil
}
func unreal(root string)[]candidate {
    if ordinaryDir(root,"Engine/Binaries")&&ordinaryDir(root,"Content/Paks"){
        return []candidate{{engine:"Unreal Engine",version:"no identificada",
            signals:[]string{"Engine/Binaries/","Content/Paks/"}}}
    }
    for _,d:=range listSafe(root){
        if !d.IsDir()||d.Type()&os.ModeSymlink!=0{continue}
        rel:=d.Name()+"/Content/Paks"
        if ordinaryDir(root,rel)&&ordinaryDir(root,d.Name()+"/Binaries"){
            return []candidate{{engine:"Unreal Engine",version:"no identificada",
                signals:[]string{rel,d.Name()+"/Binaries"}}}
        }
    }
    return nil
}
func gamemaker(root string)[]candidate {
    if !ordinaryFile(root,"data.win"){return nil}
    b,e:=boundedRead(root,"data.win")
    if e!=nil {return []candidate{{engine:"GameMaker (archivo grande sin firma verificada)",version:"sin verificar",signals:[]string{"data.win"},ambiguous:true}}}
    if len(b)>=16&&bytes.Equal(b[:4],[]byte("FORM"))&&
       bytes.Contains(b,[]byte("GEN8"))&&bytes.Contains(b,[]byte("STRG")){
        return []candidate{{engine:"GameMaker",version:"perfil FORM/GEN8/STRG; versión sin verificar",
            signals:[]string{"data.win FORM","GEN8","STRG"}}}
    }
    return []candidate{{engine:"GameMaker (candidato)",version:"sin verificar",signals:[]string{"data.win"},ambiguous:true}}
}
func wolf(root string)[]candidate {
    if ordinaryFile(root,"Data.wolf"){return []candidate{{engine:"WOLF RPG",version:"no identificada",signals:[]string{"Data.wolf"},ambiguous:true}}}
    return nil
}
func tyrano(root string)[]candidate {
    if ordinaryDir(root,"tyrano/plugins/kag")&&ordinaryDir(root,"data/scenario"){
        return []candidate{{engine:"TyranoScript",version:"no identificada",
            signals:[]string{"tyrano/plugins/kag/","data/scenario/"}}}
    }
    return nil
}
func kirikiri(root string)[]candidate {
    if ordinaryFile(root,"data.xp3"){return []candidate{{engine:"KiriKiri/KAG (candidato)",version:"no identificada",signals:[]string{"data.xp3"},ambiguous:true}}}
    return nil
}
func html5(root string)[]candidate {
    if ordinaryFile(root,"package.json")&&ordinaryFile(root,"index.html"){
        return []candidate{{engine:"HTML5/NW.js (candidato)",version:"no identificada",
            signals:[]string{"package.json","index.html"},ambiguous:true}}
    }
    return nil
}
func flash(root,sel string)[]candidate {
    target:=sel
    if !strings.EqualFold(filepath.Ext(target),".swf"){return nil}
    b,e:=boundedRead(root,target)
    if e!=nil||len(b)<8{return nil}
    if bytes.Equal(b[:3],[]byte("FWS"))||bytes.Equal(b[:3],[]byte("CWS"))||
       bytes.Equal(b[:3],[]byte("ZWS")){
        return []candidate{{engine:"Flash / SWF",version:fmt.Sprintf("SWF byte de versión %d",b[3]),
            signals:[]string{"cabecera SWF válida"},ambiguous:true}}
    }
    return nil
}
func java(root,sel string)[]candidate {
    if !strings.EqualFold(filepath.Ext(sel),".jar"){return nil}
    b,e:=boundedRead(root,sel)
    if e==nil&&len(b)>4&&bytes.Equal(b[:4],[]byte{0x50,0x4b,0x03,0x04}){
        return []candidate{{engine:"JAR/JVM (candidato)",version:"versión de motor no identificada",
            signals:[]string{"cabecera ZIP de JAR"},ambiguous:true}}
    }
    return nil
}
func node(root string)[]candidate {
    if ordinaryFile(root,"package.json")&&ordinaryDir(root,"locales"){
        return []candidate{{engine:"Node/i18next (candidato)",version:"no identificada",
            signals:[]string{"package.json","locales/"},ambiguous:true}}
    }
    return nil
}
func candidates(root,selected,sel string)[]candidate{
    switch selected {
    case "rpg-maker":return rpg(root)
    case "renpy":return renpy(root)
    case "godot":return godot(root,sel)
    case "unity":return unity(root,sel)
    case "unreal":return unreal(root)
    case "gamemaker":return gamemaker(root)
    case "wolf":return wolf(root)
    case "tyrano":return tyrano(root)
    case "kirikiri":return kirikiri(root)
    case "html5":return html5(root)
    case "flash":return flash(root,sel)
    case "java":return java(root,sel)
    case "node-i18next":return node(root)
    default:return nil
    }
}
func Inspect(gameSelection,familyID string)(Result,error){
    group,exists:=Find(familyID)
    if !exists{return Result{},fmt.Errorf("familia desconocida: %q",familyID)}
    root,sel,err:=gameLocation(gameSelection)
    result:=Result{SelectedFamily:group.ID,FamilyName:group.Name,Status:"unknown",
        Explanation:"No hay firmas suficientes. No se modifica el juego.",
        CanInstall:false,GameLabel:filepath.Base(root)}
    if err!=nil{return result,err}
    found:=candidates(root,group.ID,sel)
    if len(found)==0{
        result.Explanation="No se verificó un motor de la familia seleccionada. No se instalará un adaptador equivocado."
        return result,nil
    }
    if len(found)>1 {
        result.Status="conflict"
        result.Explanation="Varias firmas de motor contradictorias o múltiples instalaciones. Selección manual segura requerida."
        for _,s:=range found {result.Evidence=append(result.Evidence,s.engine)}
        return result,nil
    }
    c:=found[0]
    result.DetectedEngine=c.engine
    result.EngineVersion=c.version
    result.Evidence=c.signals
    result.Status="identified"
    if c.ambiguous{result.Status="ambiguous"}
    result.Explanation="Motor inspeccionado sin ejecutar el juego. La instalación de IA queda bloqueada hasta validar su adaptador y su versión exacta."
    return result,nil
}
