"use strict";
// Synthetic loader contract only. Not a SOLData decoder and no commercial data.
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const docs={
 "System.json":{locale:"en_US",startMapId:1,gameTitle:"Synthetic",terms:{messages:{notice:"Please wait here."}}},
 "Actors.json":[null,{id:1,name:"Alice",nickname:"",profile:"Thank you for your help."}],
 "CommonEvents.json":[null,{list:[{code:401,parameters:["Good morning."]},{code:355,parameters:["Never execute this script"]}]}],
 "MapInfos.json":[null,{id:1,name:"Internal map identifier"}],
 "Map001.json":{events:[null,{pages:[{list:[{code:401,parameters:["The lantern is on the table."]},{code:102,parameters:[["Open the wooden gate."]]}]}]}]},
 "Map369.json":{events:[null,{pages:[{list:[{code:401,parameters:["橋を渡ってください。"]}]}]}]},
 "Items.json":[null,{id:1,name:"Silver Lantern",description:"The lantern is on the table.",note:"Never execute this script"}],
 "Quests.json":[null,{id:1,name:"Find the ancient key.",desc:"Please open the window.",steps:[["Open the wooden gate.",true,5,2,false,"active",true]],rewards:[["custom",0,"Thank you for your help.",false]],script:"Never execute this script"}],
 "Achievements.json":[{id:1,name:"Good morning.",description:"The lantern is on the table.",lockedDescription:"Find the ancient key.",image:"Do not translate this image name"}],
 "message_data.json":[{name:"Alice",face:["Do not translate this image name",0],messages:["Thank you for your help."]}],
 "news_source.json":["Please wait here.","https://example.invalid/never-request"]
};
const excluded=["Test_Actors.soldata","Animations.soldata","precachelist.soldata"];
const marker=n=>crypto.createHash("sha256").update("synthetic opaque source:"+n).digest();
function make(root){
 const content=path.join(root,"www"),js=path.join(content,"js"),data=path.join(content,"data");
 fs.mkdirSync(path.join(js,"plugins"),{recursive:true});fs.mkdirSync(data,{recursive:true});
 for(const n of ["rpg_core","rpg_managers","rpg_objects","rpg_scenes","rpg_windows"])
  fs.writeFileSync(path.join(js,n+".js"),"// synthetic MV");
 fs.writeFileSync(path.join(js,"plugins.js"),"var $plugins = [];");
 fs.writeFileSync(path.join(root,"SOL.exe"),"synthetic launcher");
 for(const n of Object.keys(docs))fs.writeFileSync(path.join(data,n.replace(/\.json$/,".soldata")),marker(n));
 for(const n of excluded)fs.writeFileSync(path.join(data,n),marker(n));
 fs.writeFileSync(path.join(data,"message_data.json"),JSON.stringify(docs["message_data.json"]));
}
function loader(calls,missing){
 return class NativeLogicalLoader {
  open(method,url,async){
   if(method!=="GET"||async!==true||!/^data\/[A-Za-z0-9_]+\.json$/.test(url))throw Error("invalid logical request");
   this.name=url.slice(5);calls.push(this.name);
  }
  overrideMimeType(){}
  send(){setTimeout(()=>{
   if(this.aborted)return;
   if((missing&&missing.has(this.name))||!Object.prototype.hasOwnProperty.call(docs,this.name)){
    this.status=404;this.responseText="";this.onload();return;
   }
   this.status=0;this.responseText=JSON.stringify(docs[this.name]);this.onload();
  },1);}
  abort(){this.aborted=true;}
 };
}
module.exports={docs,excluded,marker,make,loader};
if(require.main===module)make(path.resolve(process.argv[2]));
