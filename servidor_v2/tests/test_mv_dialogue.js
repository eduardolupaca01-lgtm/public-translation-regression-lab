"use strict";
// Real MV plugin loaded as written, against mock NW.js and custom-window APIs.
// No game saves, neural weight downloads, network access or GUI processes.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const EventEmitter=require("node:events");
const crypto=require("node:crypto");

function fixture(translationDelay=0,options={}){
    const posts=[],state=options.fsState||{files:{},dirs:{}};
    const read=state.files,dirs=state.dirs;
    const source=fs.readFileSync(
        path.join(__dirname,"..","plugin","IATraductora.js"),"utf8");
    const root=path.join("/tmp","servidor-qa-juego-日本語");
    const descriptor=path.join(root,"www","data","IATraductora","bridge.json");
    const core=path.join(root,"www","js","rpg_core.js");
    read[core]="// mock rpg core";
    read[path.join(root,"www","js","plugins.js")]="var $plugins = [];";
    read[descriptor]=JSON.stringify({schema:"ia-traductora-bridge-v1",
        port:24123,pid:123,token:"a".repeat(64)});
    const mockFS={
        realpathSync(p){return path.normalize(p);},
        lstatSync(p){
            if(dirs[p])return {isDirectory:()=>true,isFile:()=>false,
                isSymbolicLink:()=>false,size:0};
            if(!Object.prototype.hasOwnProperty.call(read,p)){
                const e=Error("not found");e.code="ENOENT";throw e;
            }
            return {isDirectory:()=>false,isFile:()=>true,
                isSymbolicLink:()=>false,size:Buffer.byteLength(read[p],"utf8")};
        },
        readFileSync(p){if(!(p in read))throw Error("missing");return read[p];},
        readFile(p,encoding,callback){
            setTimeout(()=>{
                if(!(p in read)){
                    const e=Error("not found");e.code="ENOENT";
                    callback(e);return;
                }
                callback(null,read[p]);
            },0);
        },
        appendFile(p,value,options,callback){
            setTimeout(()=>{read[p]=(read[p]||"")+String(value);callback(null);},1);
        },
        mkdir(p,mode,callback){
            setTimeout(()=>{dirs[p]=true;callback(null);},0);
        },
        mkdirSync(){throw Error("a second process should not be needed")},
        createReadStream(){throw Error("worker must not spawn")},
    };
    let spawnCount=0;
    const fakeHTTP={
        request(requestOptions,callback){
            const request=new EventEmitter();
            request.setTimeout=()=>{};
            request.destroy=e=>request.emit("error",e);
            request.end=body=>{
                if(options.disconnected){
                    setTimeout(()=>request.emit("error",Error("IA connection unavailable")),0);
                    return;
                }
                const result=requestOptions.path==="/status"
                    ?{schema:"ia-traductora-bridge-v1",active:true}
                    :responseFor(JSON.parse(body.toString()));
                const response=new EventEmitter();
                response.statusCode=200;
                response.resume=()=>{};
                setTimeout(()=>{
                    callback(response);
                    response.emit("data",Buffer.from(JSON.stringify(result)));
                    response.emit("end");
                },requestOptions.path==="/status"?0:translationDelay);
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
    Window_Base.prototype.drawText=function(t,x,y){
        this.lastText=t;
        if(!this.drawn)this.drawn=[];
        this.drawn.push({text:t,y:y});
    };
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
    function LegacyPromise(executor){
        const p=new Promise(executor);
        p.finally=undefined; // simulate NW.js before Promise.finally
        return p;
    }
    LegacyPromise.resolve=Promise.resolve.bind(Promise);
    LegacyPromise.all=Promise.all.bind(Promise);
    function LegacyBuffer(value,encoding){return Buffer.from(value,encoding);}
    LegacyBuffer.prototype=Buffer.prototype;
    LegacyBuffer.from=undefined;
    function LegacyNumber(value){return Number(value);}
    LegacyNumber.prototype=Number.prototype;
    LegacyNumber.isInteger=undefined;
    const context={
        window:{location:{pathname:options.pathname||path.join(root,"www","index.html")}},
        document:options.scriptSrc?{currentScript:{src:options.scriptSrc}}:null,
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
        Buffer:options.legacyBuffer?LegacyBuffer:Buffer,
        Promise:options.legacyPromise?LegacyPromise:Promise,process,Date,Map,
        Number:options.legacyBuffer?LegacyNumber:Number,Error,
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

async function testPersistentCacheAfterRestartWithoutWorker(){
    const shared={files:{},dirs:{}};
    const first=fixture(1,{fsState:shared});
    await wait(35);
    first.$gameMessage._texts=["おはようございます。"];
    new first.context.Window_Message().startMessage();
    await wait(45);
    const filename=Object.keys(shared.files).find(v=>v.endsWith("translations-ja-en-es-v2.jsonl"));
    assert.ok(filename,"asynchronous cache journal must be created");
    assert.ok(shared.files[filename].includes("Buenos días."),
        "model result must reach durable cache");
    const second=fixture(1,{fsState:shared,disconnected:true});
    await wait(35);
    second.$gameMessage._texts=["おはようございます。"];
    const replay=new second.context.Window_Message();replay.startMessage();
    assert.equal(replay.originalStarts,1);
    assert.equal(second.$gameMessage.allText(),"Buenos días.",
        "reopened game must display stored Spanish even while worker offline");
    assert.equal(second.posts.length,0,
        "already cached line cannot trigger inference again");
}
async function testRejectDamagedOutputBeforeDiskOrRender(){
    const state={files:{},dirs:{}};
    const f=fixture(1,{fsState:state});
    await wait(30);
    f.$gameMessage._texts=["今日は08月24日です。"];
    new f.context.Window_Message().startMessage();
    await wait(30);
    f.$gameMessage._texts=["今日は08月24日です。"];
    new f.context.Window_Message().startMessage();
    assert.equal(f.$gameMessage.allText(),"今日は08月24日です。",
        "missing dates must not be accepted just because response is Spanish");
}
async function testJapaneseDialogAndF10(){
    const f=fixture(1);await wait(12);
    f.$gameMessage._texts=["おはようございます。"];
    const msg=new f.context.Window_Message();msg.startMessage();
    assert.equal(msg.originalStarts,1,"native first dialogue cannot wait on IA");
    assert.equal(f.$gameMessage.allText(),"おはようございます。");
    await wait(22);
    assert.equal(f.posts.length,1);
    assert.equal(f.posts[0].source,"ja");
    f.$gameMessage._texts=["おはようございます。"];
    const second=new f.context.Window_Message();second.startMessage();
    assert.equal(second.originalStarts,1);
    assert.equal(f.$gameMessage.allText(),"Buenos días.",
        "verified cached result renders inside native message");
    assert.equal(f.posts.length,1,"cached text avoids repeated inference");
    const scene=new f.context.Scene_Map();scene.createAllWindows();
    assert.equal(scene.windows.length,2);
    assert.equal(scene.windows[0].lastText,"◆ IA Traductora · F10");
    assert.equal(scene.windows[1].visible,false);
    assert.ok(scene.windows[1].height>=340);
    const ys=scene.windows[1].drawn.map(v=>v.y);
    assert.ok(ys.every((v,i)=>i===0||v-ys[i-1]>=36),
        "F10 must be readable");
    f.context.Input.isTriggered=()=>true;
    scene.update();assert.equal(scene.windows[1].visible,true);
    scene.update();assert.equal(scene.windows[1].visible,false);
    assert.equal(f.spawnCount(),0);
}
async function testEnglishAndSpanish(){
    const f=fixture(1);await wait(12);
    f.$gameMessage._texts=["Hello, how are you today?"];
    new f.context.Window_Message().startMessage();
    await wait(22);
    assert.equal(f.posts.length,1);assert.equal(f.posts[0].source,"en");
    f.$gameMessage._texts=["Hola, ¿cómo estás hoy?"];
    const spanish=new f.context.Window_Message();spanish.startMessage();
    assert.equal(spanish.originalStarts,1);
    assert.equal(f.posts.length,1,"never retranslate Spanish");
}
async function testRPGControlsAndNoLateRewrite(){
    const f=fixture(12);await wait(12);
    f.$gameMessage._texts=["\\V[1] おはようございます。"];
    const first=new f.context.Window_Message();first.startMessage();
    assert.equal(first.originalStarts,1);
    await wait(30);
    assert.equal(f.posts.length,1);
    assert.equal(f.posts[0].text,"おはようございます。",
        "model must not receive native variable escape");
    f.$gameMessage._texts=["\\V[1] おはようございます。"];
    new f.context.Window_Message().startMessage();
    assert.equal(f.$gameMessage.allText(),"\\V[1] Buenos días.");
    f.$gameMessage._texts=["さようなら。"];
    new f.context.Window_Message().startMessage();
    f.$gameMessage._texts=["次のシーンです。"];
    await wait(30);
    assert.equal(f.$gameMessage.allText(),"次のシーンです。",
        "late result may only enter cache; it must not modify a new message");
}
async function testChoiceCacheOnlyAndNoOverwrite(){
    const f=fixture(1);await wait(12);
    f.$gameMessage.setChoices(["はい","いいえ"],0,1);
    assert.deepEqual(Array.from(f.$gameMessage._choices),["はい","いいえ"]);
    await wait(22);
    f.$gameMessage.setChoices(["はい","いいえ"],0,1);
    assert.deepEqual(Array.from(f.$gameMessage._choices),
        ["Buenos días.","Buenos días."],"cached choices preserve their indices");
    assert.equal(f.posts.length,2);
    const late=fixture(25);await wait(12);
    late.$gameMessage.setChoices(["はい"],0,0);
    late.$gameMessage.setChoices(["No, gracias."],0,0);
    await wait(40);
    assert.deepEqual(Array.from(late.$gameMessage._choices),["No, gracias."],
        "async choice must never overwrite later prompt");
}
async function testOriginalNWJSWithoutBufferFromOrNumberIsInteger(){
    const f=fixture(1,{legacyBuffer:true,legacyPromise:true});
    await wait(15);
    f.$gameMessage._texts=["おはようございます。"];
    new f.context.Window_Message().startMessage();
    await wait(25);
    assert.equal(f.posts.length,1,
        "older NW.js must still send a real UTF-8 neural request");
    f.$gameMessage._texts=["おはようございます。"];
    new f.context.Window_Message().startMessage();
    assert.equal(f.$gameMessage.allText(),"Buenos días.",
        "verified translation must show on old NW.js");
}
async function testOldNWJSAndPathFallback(){
    const f=fixture(1,{legacyPromise:true});await wait(12);
    f.$gameMessage._texts=["おはようございます。"];
    new f.context.Window_Message().startMessage();await wait(22);
    f.$gameMessage._texts=["おはようございます。"];
    new f.context.Window_Message().startMessage();
    assert.equal(f.$gameMessage.allText(),"Buenos días.",
        "Promise.finally must not be required");
    const script=path.join("/tmp","servidor-qa-juego-日本語",
        "www","js","plugins","IATraductora.js");
    const fallback=fixture(1,{pathname:"/not-the-game/index.html",
        scriptSrc:"file://"+encodeURI(script)});
    await wait(12);
    fallback.$gameMessage._texts=["おはようございます。"];
    new fallback.context.Window_Message().startMessage();await wait(22);
    fallback.$gameMessage._texts=["おはようございます。"];
    new fallback.context.Window_Message().startMessage();
    assert.equal(fallback.$gameMessage.allText(),"Buenos días.");
}
async function testUnconnectedGameIsPlayableAndF10Safe(){
    const f=fixture(0,{disconnected:true});await wait(16);
    f.$gameMessage._texts=["おはようございます。"];
    const msg=new f.context.Window_Message();msg.startMessage();
    assert.equal(msg.originalStarts,1);
    assert.equal(msg._iaWaiting,undefined);
    msg.update();assert.equal(msg.updates,1);
    assert.equal(f.spawnCount(),0,"worker must not start at title");
    const bad=fixture(1,{pathname:"/no-such-mv-game/index.html"});
    const scene=new bad.context.Scene_Map();scene.createAllWindows();
    const content=scene.windows[1].drawn.map(v=>v.text).join("\n");
    assert.match(content,/IA_INICIO_RUTA_FALLIDO/);
}
async function testSlowModelNeverPausesText(){
    const f=fixture(80);await wait(12);
    f.$gameMessage._texts=["おはようございます。"];
    const msg=new f.context.Window_Message();msg.startMessage();
    assert.equal(msg.originalStarts,1);
    assert.equal(f.$gameMessage.allText(),"おはようございます。");
    f.$gameMessage._texts=["次のシーンです。"];
    await wait(95);
    assert.equal(f.$gameMessage.allText(),"次のシーンです。");
}
async function testBoundedMapPrefetchAndPressure(){
    const f=fixture(1);await wait(12);
    const commands=[];
    for(let i=0;i<600;i++)commands.push({code:401,parameters:["こんにちは "+i+"。"]});
    f.context.$dataMap={events:[null,{pages:[{list:commands}]}]};
    const scene=new f.context.Scene_Map();scene.createAllWindows();scene.update();
    await wait(70);
    assert.ok(f.posts.length<=12,"background scan must not flood requests");
    f.$gameMessage._texts=["おはようございます。"];
    const msg=new f.context.Window_Message();
    for(let i=0;i<300;i++)msg.startMessage();
    assert.equal(msg.originalStarts,300,"native hook cannot recurse under pressure");
}
(async()=>{
    await testPersistentCacheAfterRestartWithoutWorker();
    await testRejectDamagedOutputBeforeDiskOrRender();
    await testUnconnectedGameIsPlayableAndF10Safe();
    await testSlowModelNeverPausesText();
    await testOriginalNWJSWithoutBufferFromOrNumberIsInteger();
    await testOldNWJSAndPathFallback();
    await testJapaneseDialogAndF10();
    await testEnglishAndSpanish();
    await testRPGControlsAndNoLateRewrite();
    await testChoiceCacheOnlyAndNoOverwrite();
    await testBoundedMapPrefetchAndPressure();
    console.log("SERVIDOR_V2_MV_NATIVE_FAIL_OPEN_CACHE_PREFETCH_AND_F10_PASS");
})().catch(e=>{console.error(e.stack);process.exitCode=1});
