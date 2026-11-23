"use strict";
// Real MV plugin loaded as written, against mock NW.js and custom-window APIs.
// No game saves, neural weight downloads, network access or GUI processes.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const EventEmitter=require("node:events");
const crypto=require("node:crypto");

function fixture(translationDelay=0){
    const posts=[],read={},source=fs.readFileSync(
        path.join(__dirname,"..","plugin","IATraductora.js"),"utf8");
    const root=path.join("/tmp","servidor-qa-juego-日本語");
    const descriptor=path.join(root,"www","data","IATraductora","bridge.json");
    const core=path.join(root,"www","js","rpg_core.js");
    read[core]="// mock rpg core";
    read[descriptor]=JSON.stringify({schema:"ia-traductora-bridge-v1",
        port:24123,pid:123,token:"a".repeat(64)});
    const mockFS={
        realpathSync(p){return path.normalize(p);},
        lstatSync(p){
            if(!Object.prototype.hasOwnProperty.call(read,p))
                throw Error("not found");
            return {isFile:()=>true,isSymbolicLink:()=>false};
        },
        readFileSync(p){if(!(p in read))throw Error("missing");return read[p];},
        mkdirSync(){throw Error("a second process should not be needed")},
        createReadStream(){throw Error("worker must not spawn")},
    };
    let spawnCount=0;
    const fakeHTTP={
        request(options,callback){
            const request=new EventEmitter();
            request.setTimeout=()=>{};
            request.destroy=e=>request.emit("error",e);
            request.end=body=>{
                const result=options.path==="/status"
                    ?{schema:"ia-traductora-bridge-v1",active:true}
                    :responseFor(JSON.parse(body.toString()));
                const response=new EventEmitter();
                response.statusCode=200;
                response.resume=()=>{};
                setTimeout(()=>{
                    callback(response);
                    response.emit("data",Buffer.from(JSON.stringify(result)));
                    response.emit("end");
                },options.path==="/status"?0:translationDelay);
            };
            return request;
        }
    };
    function responseFor(body){
        posts.push(body);
        return {translated:body.source==="ja"?"Buenos días.":"Hello"===body.text?"Hola.":"Buenos días."};
    }
    function Window_Base(){}
    Window_Base.prototype.initialize=function(x,y,w,h){
        this.x=x;this.y=y;this.width=w;this.height=h;
        this.contents={fontSize:12,outlineWidth:1,clear(){}};
    };
    Window_Base.prototype.contentsWidth=function(){return this.width-20};
    Window_Base.prototype.drawText=function(t){this.lastText=t};
    function Window_Message(){this.originalStarts=0;this.updates=0}
    Window_Message.prototype.startMessage=function(){this.originalStarts++};
    Window_Message.prototype.update=function(){this.updates++};
    function Scene_Map(){this.windows=[]}
    Scene_Map.prototype.createAllWindows=function(){};
    Scene_Map.prototype.update=function(){};
    Scene_Map.prototype.addWindow=function(win){this.windows.push(win)};
    function Game_Message(){this._texts=[];this._choices=[];}
    Game_Message.prototype.hasText=function(){return this._texts.length>0;};
    Game_Message.prototype.allText=function(){return this._texts.join("\n");};
    Game_Message.prototype.setChoices=function(choices){
        this._choices=choices.slice();
    };
    const $gameMessage=new Game_Message();
    const context={
        window:{location:{pathname:path.join(root,"www","index.html")}},
        Utils:{isNwjs:()=>true},
        require(name){
            switch(name){
                case "fs":return mockFS;
                case "path":return path;
                case "crypto":return crypto;
                case "http":return fakeHTTP;
                case "child_process":
                    return {spawn(){spawnCount++;throw Error("unexpected worker spawn")}};
                default:throw Error("unexpected dependency "+name);
            }
        },
        Buffer,Promise,process,Date,Map,Number,Error,
        setTimeout,clearTimeout,setInterval(){return 1},
        Window_Base,Window_Message,Scene_Map,Game_Message,
        Graphics:{boxWidth:1280},
        Input:{keyMapper:{},isTriggered(){return false}},
        SceneManager:{_scene:null},
        $gameMessage
    };
    vm.runInNewContext(source,context,{filename:"IATraductora.js"});
    return {context,posts,$gameMessage,spawnCount:()=>spawnCount};
}
const wait=t=>new Promise(resolve=>setTimeout(resolve,t));

async function testJapaneseDialogAndF10(){
    const f=fixture(1);
    await wait(12);
    f.$gameMessage._texts=["おはようございます。"];
    const msg=new f.context.Window_Message();
    msg.startMessage();
    assert.equal(msg.originalStarts,0,"must await asynchronous translation");
    await wait(12);msg.update();
    assert.equal(f.$gameMessage.allText(),"Buenos días.");
    assert.equal(msg.originalStarts,1,"start message exactly once");
    assert.equal(f.posts.length,1);
    assert.equal(f.posts[0].source,"ja");
    const second=new f.context.Window_Message();
    f.$gameMessage._texts=["おはようございます。"];
    second.startMessage();
    assert.equal(second.originalStarts,1,"cache bypasses inference");
    assert.equal(f.posts.length,1);
    const scene=new f.context.Scene_Map();
    scene.createAllWindows();
    assert.equal(scene.windows.length,2,"single mini badge and one hidden panel");
    assert.equal(scene.windows[0].lastText,"◆ IA Traductora · F10");
    assert.equal(scene.windows[1].visible,false);
    f.context.Input.isTriggered=()=>true;
    scene.update();
    assert.equal(scene.windows[1].visible,true,"F10 shows native state panel");
    scene.update();
    assert.equal(scene.windows[1].visible,false,"F10 closes native panel");
    assert.equal(f.spawnCount(),0,"single application; no child GUI when connected");
}
async function testAutomaticEnglishAndSpanishExclusion(){
    const f=fixture(1);
    await wait(12);
    const msg=new f.context.Window_Message();
    f.$gameMessage._texts=["Hello, how are you today?"];
    msg.startMessage();await wait(12);msg.update();
    assert.equal(f.posts.length,1,"English sentence must reach model");
    assert.equal(f.posts[0].source,"en","Origen Auto must not hardcode Japanese");
    f.$gameMessage._texts=["Hola, ¿cómo estás hoy?"];
    const spanish=new f.context.Window_Message();spanish.startMessage();
    assert.equal(spanish.originalStarts,1);
    assert.equal(f.posts.length,1,"don't retranslate Spanish player content");
}
async function testProtectedCommandsAndMovingDialog(){
    const f=fixture(22);await wait(12);
    f.$gameMessage._texts=["\\V[1] おはようございます。"];
    const protectedMessage=new f.context.Window_Message();
    protectedMessage.startMessage();
    assert.equal(protectedMessage.originalStarts,0,"wait for safely masked translation");
    await wait(40);protectedMessage.update();
    assert.equal(f.$gameMessage.allText(),"\\V[1] Buenos días.",
        "RPG variable must be preserved while natural text is translated");
    assert.equal(protectedMessage.originalStarts,1);
    assert.equal(f.posts.length,1,"control sequence must not block translation");
    assert.equal(f.posts[0].text,"おはようございます。",
        "neural model must never receive the RPG variable token");
    const msg=new f.context.Window_Message();
    f.$gameMessage._texts=["さようなら。"];
    msg.startMessage();
    f.$gameMessage._texts=["次のシーンです。"];
    await wait(35);msg.update();
    assert.equal(f.$gameMessage.allText(),"次のシーンです。",
        "stale translation must never change another scene's dialogue");
    assert.equal(msg.originalStarts,0,"stale text must not be displayed");
    assert.equal(msg._iaWaiting,null,"stale async state must be cleared");
}
async function testNativeChoiceTranslationAndNoStaleChoiceOverwrite(){
    const f=fixture(1);await wait(12);
    f.$gameMessage.setChoices(["はい","いいえ"],0,1);
    await wait(12);
    assert.deepEqual(Array.from(f.$gameMessage._choices),
        ["Buenos días.","Buenos días."],
        "choices should be updated natively without changing indices");
    assert.equal(f.posts.length,2);
    const late=fixture(24);await wait(12);
    late.$gameMessage.setChoices(["はい"],0,0);
    late.$gameMessage.setChoices(["No, gracias."],0,0);
    await wait(35);
    assert.deepEqual(Array.from(late.$gameMessage._choices),["No, gracias."],
        "late translation must never overwrite a new choice list");
}
(async()=>{
    await testJapaneseDialogAndF10();
    await testAutomaticEnglishAndSpanishExclusion();
    await testProtectedCommandsAndMovingDialog();
    await testNativeChoiceTranslationAndNoStaleChoiceOverwrite();
    console.log("SERVIDOR_V2_MV_NATIVE_DIALOGUE_AUTOSOURCE_AND_NO_STALE_OVERWRITE_PASS");
})().catch(e=>{console.error(e.stack);process.exitCode=1});
