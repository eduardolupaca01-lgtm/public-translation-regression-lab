package engine

// The 17 entries are navigation groups, not 17 certified translation engines.
// Family is for choosing WHICH evidence to inspect, never for writing to games.
type Family struct {
    ID string `json:"id"`
    Name string `json:"name"`
    Variants []string `json:"variants"`
    Inspection string `json:"inspection"`
    TranslationCertified bool `json:"translation_certified"`
}
var Families = []Family{
    {ID:"rpg-maker",Name:"RPG Maker",Variants:[]string{"2000","2003","XP","VX","VX Ace","MV","MZ","Unite (Unity)","U2U (sin verificación)"},Inspection:"subtipo por archivos, sin asumir MV/MZ"},
    {ID:"renpy",Name:"Ren'Py",Variants:[]string{"6.x","7.x","8.x"},Inspection:"distribución y versión si hay manifiesto"},
    {ID:"godot",Name:"Godot",Variants:[]string{"3.x","4.x"},Inspection:"paquete .pck y manifiesto si está disponible"},
    {ID:"tyrano",Name:"TyranoScript",Inspection:"archivos tyrano y escenarios .ks"},
    {ID:"kirikiri",Name:"KiriKiri / KAG",Inspection:"archivos .xp3 y scripts"},
    {ID:"html5",Name:"HTML5 / NW.js",Inspection:"package.json y recursos web"},
    {ID:"lightvn",Name:"Light.vn",Inspection:"inspección conservadora"},
    {ID:"flash",Name:"Flash / SWF",Inspection:"cabecera de SWF"},
    {ID:"srpg",Name:"SRPG Studio",Inspection:"inspección conservadora"},
    {ID:"vnm",Name:"Visual Novel Maker",Inspection:"inspección conservadora"},
    {ID:"wolf",Name:"WOLF RPG",Inspection:"contenedor y ficheros de proyecto"},
    {ID:"unity",Name:"Unity",Inspection:"UnityPlayer.dll y carpeta *_Data"},
    {ID:"unreal",Name:"Unreal Engine",Inspection:"binaries, Content/Paks, .pak"},
    {ID:"gamemaker",Name:"GameMaker",Inspection:"FORM/GEN8/STRG en data.win"},
    {ID:"java",Name:"Java / JVM",Inspection:"JAR/manifest; versión por confirmar"},
    {ID:"bakin",Name:"RPG Developer Bakin",Inspection:"inspección conservadora"},
    {ID:"node-i18next",Name:"Node / i18next",Inspection:"catálogos locales y package.json"},
}
func Find(id string)(Family,bool){
    for _,f:=range Families {if f.ID==id{return f,true}}
    return Family{},false
}
func CloneCatalog() []Family { out:=make([]Family,len(Families));copy(out,Families);return out }
