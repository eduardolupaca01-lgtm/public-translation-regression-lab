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
    $gameMessage:gameMessage
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

    gameMessage._texts=["\\N[2] おはようございます。"];
    const dialog=new Window_Message();
    dialog.startMessage();
    await until(()=>{dialog.update();return dialog.starts===1;},120000,
        "IA_NATIVE_DIALOG_TIMEOUT");
    const displayed=gameMessage.allText();
    assert.ok(displayed.startsWith("\\N[2] "),
        "IA_GAME_CONTROL_CODE_CHANGED");
    assert.ok(!japanese(displayed) && displayed!=="\\N[2] おはようございます。",
        "IA_DIALOG_NOT_TRANSLATED");
    assert.equal(dialog.starts,1,"IA_DIALOG_DOUBLE_STARTED");

    gameMessage.setChoices(["はい、お願いします。","いいえ、けっこうです。"],0,1);
    await until(()=>gameMessage._choices.every(v=>!japanese(v)),120000,
        "IA_NATIVE_CHOICES_TIMEOUT");
    assert.equal(gameMessage._choices.length,2,"IA_CHOICE_COUNT_CHANGED");
    assert.ok(gameMessage._choices.every(v=>typeof v==="string"&&v.trim()),
        "IA_NATIVE_CHOICES_EMPTY");
    console.log("SERVIDOR_V2_INSTALLED_PLUGIN_TO_REAL_V95_NATIVE_TEXT_AND_CHOICES_PASS");
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
