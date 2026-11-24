"use strict";
// Release gate: installed MV plugin -> real local worker -> native UI state.
// Synthetic game and authored text only; no credentials or model output in logs.
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const cp=require("node:child_process");

const game=path.resolve(process.argv[2]||"");
const content=fs.existsSync(path.join(game,"www","js","rpg_core.js"))?
    path.join(game,"www"):game;
const plugin=path.join(content,"js","plugins","IATraductora.js");
const source=fs.readFileSync(plugin,"utf8");
const intervals=[],children=[];

function Window_Base(){}
Window_Base.prototype.initialize=function(x,y,width,height){
    this.x=x;this.y=y;this.width=width;this.height=height;
    this.drawn=[];
    const self=this;
    this.contents={fontSize:12,outlineWidth:1,clear(){self.drawn=[];}};
};
Window_Base.prototype.contentsWidth=function(){return this.width-24;};
Window_Base.prototype.drawText=function(value){this.drawn.push(String(value));};
function Window_Message(){this.starts=0;}
Window_Message.prototype.startMessage=function(){this.starts++;};
Window_Message.prototype.update=function(){};
function Game_Message(){this._texts=[];this._choices=[];}
Game_Message.prototype.hasText=function(){return this._texts.length>0;};
Game_Message.prototype.allText=function(){return this._texts.join("\n");};
Game_Message.prototype.setChoices=function(choices){
    this._choices=choices.slice();
};
function Scene_Map(){this.windows=[];}
Scene_Map.prototype.createAllWindows=function(){};
Scene_Map.prototype.update=function(){};
Scene_Map.prototype.addWindow=function(window){this.windows.push(window);};

// Match the real Galv Scene_Map factory contract, with a private caption
// class and layout that does not call any inherited drawText hook.
(function(){
    function Window_GalvCaption(target,time,textArray,data,delay,skin,yoffset){
        this.target=target;this._time=time+delay;this._txtArray=textArray;
        this.data=data;this.skin=skin;this.yoffset=yoffset;this.active=true;
        this.imagesLoaded=true;this.layoutCount=0;this.setWindowDimensions();
    }
    Window_GalvCaption.prototype.setWindowDimensions=function(){
        this.layoutCount++;this.painted=this._txtArray.slice();
        this.width=240;
    };
    Window_GalvCaption.prototype.update=function(){this._time--;};
    Scene_Map.prototype.createCaptionWindow=function(target,time,textArray,data,delay,skin,yoffset){
        const w=new Window_GalvCaption(target,time,textArray,data,delay,skin,yoffset);
        (this._captionWindows||(this._captionWindows=[])).push(w);
        w.parent=this;this.addWindow(w);
    };
})();
const gameMessage=new Game_Message();
let keyPressed=false;
const ctx={
    window:{location:{pathname:"/"+path.join(content,"index.html").replace(/\\/g,"/")}},
    Utils:{isNwjs:()=>true},
    require(name){
        if(name==="child_process"){
            return {spawn(command,args,opts){
                const child=cp.spawn(command,args,opts);
                children.push(child);
                return child;
            }};
        }
        return require(name);
    },
    process,Buffer,Promise,Date,Number,Map,Error,
    setTimeout,clearTimeout,
    setInterval(fn,ms){const id=setInterval(fn,ms);intervals.push(id);return id;},
    Window_Base,Window_Message,Game_Message,Scene_Map,
    Graphics:{boxWidth:1280},
    Input:{keyMapper:{},isTriggered(){return keyPressed;}},
    SceneManager:{_scene:null},
    $gameMessage:gameMessage,
    $plugins:[{name:"GALV_TimedMessagePopups",status:true,parameters:{}}]
};
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(predicate,limitMs,code){
    const deadline=Date.now()+limitMs;
    while(Date.now()<deadline){
        if(predicate())return;
        await wait(250);
    }
    throw Error(code);
}
function japanese(value){return /[\u3040-\u30ff\u3400-\u9fff]/.test(value);}
async function run(){
    vm.runInNewContext(source,ctx,{filename:"IATraductora.js"});
    assert.equal(ctx.Input.keyMapper[121],"ia-traductora","IA_F10_MAPPER_MISSING");
    const scene=new Scene_Map();
    ctx.SceneManager._scene=scene;
    scene.createAllWindows();
    assert.equal(scene.windows.length,2,"IA_F10_NATIVE_WINDOWS_MISSING");
    keyPressed=true;scene.update();keyPressed=false;
    assert.equal(scene.windows[1].visible,true,"IA_F10_PANEL_NOT_VISIBLE");
    keyPressed=true;scene.update();keyPressed=false;
    assert.equal(scene.windows[1].visible,false,"IA_F10_PANEL_NOT_CLOSED");
    // In fail-open mode the worker is intentionally not launched during
    // title/boot. Wait for an actual authenticated connection after Map.update.
    await until(()=>{
        if(!scene.windows[1]||typeof scene.windows[1].refresh!=="function")return false;
        scene.windows[1].refresh();
        return scene.windows[1].drawn.some(line=>line.indexOf("IA local conectada")!==-1);
    },120000,"IA_WORKER_DID_NOT_CONNECT_AFTER_MAP");

    const sourceText="\\N[2] おはようございます。";
    gameMessage._texts=[sourceText];
    const first=new Window_Message();
    first.startMessage();
    assert.equal(first.starts,1,"IA_NATIVE_FIRST_DIALOG_MUST_NOT_STALL");
    assert.equal(gameMessage.allText(),sourceText,
        "IA_PENDING_DIALOG_MUST_REMAIN_ORIGINAL");
    await until(()=>{
        gameMessage._texts=[sourceText];
        const repeated=new Window_Message();
        repeated.startMessage();
        return !japanese(gameMessage.allText());
    },120000,"IA_NATIVE_DIALOG_CACHE_TIMEOUT");
    const displayed=gameMessage.allText();
    assert.ok(displayed.startsWith("\\N[2] "),
        "IA_GAME_CONTROL_CODE_CHANGED");
    assert.ok(!japanese(displayed)&&displayed!==sourceText,
        "IA_DIALOG_NOT_TRANSLATED");

    const sourceChoices=["はい、お願いします。","いいえ、けっこうです。"];
    gameMessage.setChoices(sourceChoices,0,1);
    assert.ok(gameMessage._choices.every(japanese),
        "IA_UNCACHED_CHOICES_CANNOT_REPAINT_LIVE_PROMPT");
    await until(()=>{
        gameMessage.setChoices(sourceChoices,0,1);
        return gameMessage._choices.every(v=>!japanese(v));
    },120000,"IA_NATIVE_CHOICES_CACHE_TIMEOUT");
    assert.equal(gameMessage._choices.length,2,"IA_CHOICE_COUNT_CHANGED");
    assert.ok(gameMessage._choices.every(v=>typeof v==="string"&&v.trim()),
        "IA_NATIVE_CHOICES_EMPTY");
    const captionText="Please wait here.",list=[captionText],meta=["",0,0,2],target={id:1};
    scene.createCaptionWindow(target,360,list,meta,0,"Window",-40);
    const caption=scene._captionWindows[0];
    await until(()=>{
        for(let i=0;i<4;i++)caption.update();
        // If the original timed caption has expired, a new native display
        // uses the durable result instead of reviving an old window.
        if(caption.painted[0]!==captionText)return true;
        return false;
    },20000,"IA_NATIVE_GALV_CAPTION_TIMEOUT");
    assert.ok(/esper|aguard/i.test(caption.painted[0]),"IA_NATIVE_GALV_CAPTION_NOT_SPANISH");
    assert.equal(list[0],captionText,"IA_NATIVE_GALV_INPUT_CHANGED");
    assert.equal(caption.target,target,"IA_NATIVE_GALV_TARGET_CHANGED");
    assert.equal(caption.data,meta,"IA_NATIVE_GALV_METADATA_CHANGED");
    assert.equal(caption.skin,"Window","IA_NATIVE_GALV_SKIN_CHANGED");
    assert.equal(caption.yoffset,-40,"IA_NATIVE_GALV_OFFSET_CHANGED");
    assert.equal(scene._captionWindows.length,1,"IA_NATIVE_GALV_DUPLICATE");
    scene.createCaptionWindow(target,60,list,meta,0,"Window",-40);
    assert.equal(scene._captionWindows[1].painted[0],caption.painted[0],"IA_NATIVE_GALV_REPLAY_FAILED");
    console.log("SERVIDOR_V2_REAL_OPUS_NATIVE_GALV_CAPTION_PASS");
    console.log("SERVIDOR_V2_REAL_OPUS_PASSIVE_NATIVE_CACHE_TEXT_AND_CHOICES_PASS");
}
run().catch(err=>{
    const code=err&&typeof err.message==="string"&&/^IA_[A-Z0-9_]+$/.test(err.message)?
        err.message:"IA_NATIVE_BRIDGE_ASSERTION_FAILED";
    console.error(code);
    process.exitCode=1;
}).finally(()=>{
    for(const timer of intervals)clearInterval(timer);
    for(const child of children){
        try{if(child.pid && child.exitCode===null)child.kill();}catch(_){}
    }
});
