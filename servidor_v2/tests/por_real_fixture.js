"use strict";
// Create an independent synthetic compressed MZ game using the real LZString
// library in the CI-only dependency directory. No commercial files or prose.
const fs=require("node:fs");
const path=require("node:path");
const assert=require("node:assert/strict");
const root=path.resolve(process.argv[2]),lz=require(path.resolve(process.argv[3]));
const js=path.join(root,"js"),data=path.join(root,"data"),plugins=path.join(js,"plugins");
fs.mkdirSync(plugins,{recursive:true});fs.mkdirSync(data,{recursive:true});
fs.writeFileSync(path.join(root,"Game.exe"),Buffer.from([77,90,0,0]));
for(const n of ["rmmz_core","rmmz_managers","rmmz_objects","rmmz_scenes","rmmz_windows"])
    fs.writeFileSync(path.join(js,n+".js"),"// synthetic MZ marker\n");
for(const n of ["POR_DatabaseEncoder","lz-string.min"])
    fs.writeFileSync(path.join(plugins,n+".js"),"// synthetic loader marker; test uses real LZString API\n");
const registry=[
    {name:"lz-string.min",status:true,parameters:{}},
    {name:"POR_DatabaseEncoder",status:true,parameters:{}},
    {name:"Iavra_MZ_Localization_byNeomaStudio",status:true,parameters:{"Escape Code":"{{key}}","Languages":"jp, en, zh","File Path":"data/lang_g_{lang}.json,data/lang_h_{lang}.json,data/lang_items_{lang}.json"}},
    {name:"TSR_MapPopups",status:true,parameters:{}}
];
fs.writeFileSync(path.join(js,"plugins.js"),"var $plugins = "+JSON.stringify(registry)+";\n");
const docs={
    "System":{locale:"en_US",startMapId:1},"Actors":[null,{id:1,name:"{n1}",profile:"",note:""}],"CommonEvents":[null],"MapInfos":[null,{id:1,name:""}],
    "Map001":{events:[null,{pages:[{list:[{code:101,parameters:["",0,0,2,"{n1}"]},{code:401,parameters:["{line1}"]},{code:102,parameters:[["{choice1}"],0,0,2,0]},{code:357,parameters:["TSR_MapPopups","text","",{text:"{notice1}",duration:"60",target:"0",color:"2"}]}]}]}]},
    "lang_g_en":{n1:"Alice",choice1:"Open the wooden gate.",notice1:"Thank you for your help."},
    "lang_h_en":{line1:"The lantern is on the table."},
    "lang_items_en":{item1:"Silver lantern"},
    "lang_g_jp":{n1:"アリス",choice1:"木の門を開けてください。",notice1:"おはようございます。"},
    "lang_h_jp":{line1:"橋を渡ってください。"},
    "lang_items_jp":{item1:"銀のランタン"},
    "lang_g_zh":{n1:"爱丽丝",choice1:"打开木门。",notice1:"谢谢你的帮助。"},
    "lang_h_zh":{line1:"灯笼在桌子上。"},"lang_items_zh":{item1:"银灯笼"}
};
for(const [name,doc] of Object.entries(docs)){
    const plain=JSON.stringify(doc),compressed=lz.compressToBase64(plain);
    assert.equal(lz.decompressFromBase64(compressed),plain);
    fs.writeFileSync(path.join(data,name+".jsono"),compressed);
}
assert.ok(!fs.existsSync(path.join(data,"System.json")));
console.log("IA_R18_SYNTHETIC_JSONO_NATIVE_CODEC_PASS");
