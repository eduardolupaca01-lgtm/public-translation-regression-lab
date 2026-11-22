"use strict";
const a=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),os=require("node:os");
const x=require("../../tools/tx765_public_core");
const ja="ありがとうございます。",es="Muchas gracias.";
function scenario(mode,cache,namebox=false){
 const win={drawn:[],_textState:null,contents:{width:900,clear(){throw Error("MUST_NOT_CLEAR");}},contentsWidth(){return 900;},textWidth(s){return s.length*10;},drawTextEx(s){this.drawn.push("window:"+s);}};
 win.contents.drawText=function(s){win.drawn.push("bitmap:"+s)};
 if(namebox)win._nameBoxWindow={visible:true};
 const beforeBitmap=win.contents.drawText,beforeWin=win.drawTextEx;
 const result=x.firstPaint(win,ja,cache?es:null,function(){
   this._textState={text:ja,index:0};
   if(mode==="bitmap")this.contents.drawText(this._textState.text);
   else this.drawTextEx(this._textState.text);
 });
 a.equal(win.drawTextEx,beforeWin);a.equal(win.contents.drawText,beforeBitmap);
 a.equal(win.drawn.length,1);
 a.equal(win._textState.text,cache&&!namebox?es:ja);
 a.equal(win.drawn[0],(mode==="bitmap"?"bitmap:":"window:")+(cache&&!namebox?es:ja));
 a.equal(result.requiresLateOverlay,false);
}
for(const mode of ["bitmap","window"])for(const cache of [true,false])scenario(mode,cache);
scenario("window",true,true);
const root=fs.mkdtempSync(path.join(os.tmpdir(),"tx765-public-"));
try{
 const data=path.join(root,"data");fs.mkdirSync(data);
 const name=x.FOLDERS[1];fs.mkdirSync(path.join(data,name));
 fs.writeFileSync(path.join(data,name,"embedded-v87-bridge.json"),JSON.stringify({
  schema:"tenshixgame-bridge-v87",pid:1234,port:45000,token:"a".repeat(64)
 }));
 const bridge=x.discoverBridge(root);
 a.equal(bridge.folder,name);a.equal(bridge.status,"STRUCTURE_VALID_NOT_YET_AUTHENTICATED");
 a.equal(Object.keys(bridge).includes("token"),false);
 fs.writeFileSync(path.join(data,"Map001.json"),JSON.stringify({events:[{pages:[{list:[
  {code:401,parameters:[ja]}, {code:405,parameters:["学校です。"]},
  {code:102,parameters:[["はい。","いいえ。"],0,0,2,0]},
  {code:355,parameters:["日本語のスクリプトを変えない。"]}
 ]}]}]}));
 fs.writeFileSync(path.join(data,"CommonEvents.json"),"{ invalid json");
 fs.writeFileSync(path.join(data,"Custom.txt"),"not a supported game JSON");
 const scan=x.scanRpgData(root);
 a.deepEqual(scan,{selected:2,visited:2,read:1,skipped:0,errors:1,segments:4,capReached:false});
 console.log("TX765_PUBLIC_PASS: Windows/Linux first-paint, original fallback, actor name, bridge spelling and supported-file counts");
}finally{fs.rmSync(root,{recursive:true,force:true});}
