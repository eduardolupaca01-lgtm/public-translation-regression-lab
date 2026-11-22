"use strict";
// PUBLIC, independent reproduction of TX765's bridge and first-paint contract.
// Does not include original private code, a model, user game or credentials.
const fs=require("node:fs"),path=require("node:path");
const JAPANESE=/[\u3040-\u30ff\u3400-\u9fff]/;
const FOLDERS=["TenshigameTranduccion","TenshigameTraduccion"];
const RPG=/^(?:Map\d{3,4}|Actors|Classes|Skills|Items|Weapons|Armors|Enemies|States|System|CommonEvents|Troops|MapInfos|Animations)\.json$/;

function discoverBridge(root){
  const base=path.resolve(root,"data"),canonical=fs.realpathSync(base);
  for(const folder of FOLDERS){
    const entry=path.join(base,folder,"embedded-v87-bridge.json");
    try {
      const info=fs.lstatSync(entry);
      if(!info.isFile()||info.isSymbolicLink()||info.size<=0||info.size>4096)continue;
      const relative=path.relative(canonical,fs.realpathSync(entry));
      if(relative===".."||relative.startsWith(".."+path.sep)||path.isAbsolute(relative))continue;
      const obj=JSON.parse(fs.readFileSync(entry,"utf8"));
      if(obj.schema==="tenshixgame-bridge-v87"&&Number.isInteger(obj.pid)&&obj.pid>0&&
         Number.isInteger(obj.port)&&obj.port>=1024&&obj.port<=65535&&
         typeof obj.token==="string"&&/^[a-f0-9]{64}$/.test(obj.token)){
        return {status:"STRUCTURE_VALID_NOT_YET_AUTHENTICATED",folder};
      }
    }catch(_){}
  }
  return {status:"MISSING"};
}
function firstPaint(win,source,translated,startMessage){
  const bitmap=win.contents,drawBitmap=bitmap&&bitmap.drawText,drawWindow=win.drawTextEx;
  let replaced=false,paintCalls=0;
  const fit=typeof translated==="string"&&translated!==source&&JAPANESE.test(source)&&
    !JAPANESE.test(translated)&&!win._nameWindow&&!win._nameBoxWindow&&
    typeof win.textWidth==="function"&&typeof win.contentsWidth==="function"&&
    win.textWidth(translated)<=win.contentsWidth();
  function choose(s){
    if(s===source&&win._textState&&win._textState.text===source&&win._textState.index===0){
      paintCalls++;
      if(fit&&!replaced){replaced=true;win._textState.text=translated;return translated;}
    }
    return s;
  }
  if(typeof drawWindow==="function")win.drawTextEx=function(...a){a[0]=choose(a[0]);return drawWindow.apply(this,a);};
  if(typeof drawBitmap==="function")bitmap.drawText=function(...a){a[0]=choose(a[0]);return drawBitmap.apply(this,a);};
  try{startMessage.call(win);}finally{
    if(typeof drawWindow==="function")win.drawTextEx=drawWindow;
    if(typeof drawBitmap==="function")bitmap.drawText=drawBitmap;
  }
  return {replaced,paintCalls,requiresLateOverlay:false};
}
function scanRpgData(root){
  const dir=path.join(root,"data"),files=fs.readdirSync(dir).filter(n=>RPG.test(n));
  const s={selected:files.length,visited:0,read:0,skipped:0,errors:0,segments:0,capReached:false};
  for(const name of files){
    if(s.segments>=16000){s.capReached=true;break;}
    s.visited++;
    try{
      const p=path.join(dir,name),st=fs.lstatSync(p);
      if(!st.isFile()||st.isSymbolicLink()||st.size>8*1024*1024){s.skipped++;continue;}
      const doc=JSON.parse(fs.readFileSync(p,"utf8"));s.read++;
      function walk(v,d){
        if(!v||d>30||s.segments>=16000)return;
        if(Array.isArray(v)){for(const el of v)walk(el,d+1);return;}
        if(typeof v!=="object")return;
        if(Number.isInteger(v.code)&&Array.isArray(v.parameters)){
          let vals=v.code===401||v.code===405?[v.parameters[0]]:v.code===102&&Array.isArray(v.parameters[0])?v.parameters[0]:[];
          for(const item of vals)if(typeof item==="string"&&item.length<=4000&&JAPANESE.test(item))s.segments++;
          return;
        }
        for(const [k,item] of Object.entries(v))if(!["script","note","meta","path"].includes(k.toLowerCase())&&item&&typeof item==="object")walk(item,d+1);
      }
      walk(doc,0);
    }catch(_){s.errors++;}
  }
  return s;
}
module.exports={FOLDERS,discoverBridge,firstPaint,scanRpgData};
