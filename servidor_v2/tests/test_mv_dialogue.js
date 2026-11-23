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
    const posts=[],batches=[],state=options.fsState||{files:{},dirs:{}};
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
        readdir(p,callback){
            setTimeout(()=>callback(null,Object.keys(read).filter(k=>path.dirname(k)===p)
                .map(k=>path.basename(k))),0);
        },
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
                let result;
                if(requestOptions.path==="/status"){
                    result={schema:"ia-traductora-bridge-v1",active:true,batch:!!options.batch};
                }else{
                    const payload=JSON.parse(body.toString());
                    if(requestOptions.path==="/translate_batch"){
                        batches.push(payload.texts.length);
                        result={results:payload.texts.map(text=>responseFor({source:payload.source,text}))};
                    }else result=responseFor(payload);
                }
                const response=new EventEmitter();
                response.statusCode=options.qualityReject&&requestOptions.path!=="/status"?422:200;
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
        if(options.namedResponse&&body.text.indexOf("Natsumi")>=0)
            return {translated:"Natsumi vive al lado."};
        return {translated:body.source==="ja"?"Buenos días.":"Hello"===body.text?"Hola.":"Buenos días."};
    }
    function Window_Base(){}
    Window_Base.prototype.initialize=function(x,y,w,h){
        this.x=x;this.y=y;this.width=w;this.height=h;
        this.contents={fontSize:12,outlineWidth:1,clear(){}};
    };
    Window_Base.prototype.contentsWidth=function(){return this.width-20};
    Window_Base.prototype.hide=function(){this.visible=false;};
    Window_Base.prototype.show=function(){this.visible=true;};
    Window_Base.prototype.drawTextEx=function(t){
        this.lastTextEx=t;return String(t).length;
    };
    Window_Base.prototype.drawText=function(t,x,y){
        this.lastText=t;
        if(!this.drawn)this.drawn=[];
        this.drawn.push({text:t,y:y});
    };
    function Bitmap(){}
    Bitmap.prototype.drawText=function(t){this.lastText=String(t);return t;};
    function Scene_Name(){}
    function Scene_Title(){
        this.starts=0;this.launches=0;this.frames=0;this.windows=[];
        this._commandWindow={activate:()=>{this.titleActive=true;}};
    }
    Scene_Title.prototype.start=function(){this.starts++;};
    Scene_Title.prototype.commandNewGame=function(){this.launches++;};
    Scene_Title.prototype.update=function(){this.frames++;};
    Scene_Title.prototype.addWindow=function(win){this.windows.push(win);};
    Scene_Title.prototype.commandContinue=function(){this.continued=true;};
    function Window_Message(){this.originalStarts=0;this.updates=0}
    Window_Message.prototype.createSubWindows=function(){
        const name=new Window_Base();name.initialize(0,0,300,90);
        name.setText=function(t){this.assigned=t;this.drawText(t,0,0,300);};
        this._nameWindow=name;
    };
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
    LegacyBuffer.from=undefined;LegacyBuffer.byteLength=Buffer.byteLength;
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
        setTimeout(fn,delay){const timer=setTimeout(fn,delay);timer.unref();return timer;},
        clearTimeout,setInterval(){return 1},
        Window_Base,Window_Message,Scene_Map,Game_Message,Bitmap,Scene_Name,Scene_Title,
        Graphics:{boxWidth:1280},
        Input:{keyMapper:{},isTriggered(){return false}},
        SceneManager:{_scene:null},
        $gameMessage
    };
    vm.runInNewContext(source,context,{filename:"IATraductora.js"});
    return {context,posts,batches,$gameMessage,spawnCount:()=>spawnCount};
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
async function testFullNativeMenusAndNameOnlyText(){
    const f=fixture(1);await wait(24);
    const w=new f.context.Window_Base();
    w.initialize(0,0,500,100);
    w.drawText("持ち物",0,0,160,"left");
    assert.equal(w.lastText,"Objetos");
    w.drawText("オプション",0,0,160,"left");
    assert.equal(w.lastText,"Opciones");
    w.drawTextEx("大事なもの",0,0);
    assert.equal(w.lastTextEx,"Objetos importantes");
    const bitmap=new f.context.Bitmap();
    bitmap.drawText("夏実",0,0,100,30);
    assert.equal(bitmap.lastText,"Natsumi",
        "approved exact name label may render in native bitmap");
    bitmap.drawText("保林 隼人",0,0,160,30);
    assert.equal(bitmap.lastText,"Hobayashi Hayato",
        "pilot nameplate should display a consistent Latin reading");
    bitmap.drawText("08月 24日 (金)",0,0,180,30);
    assert.equal(bitmap.lastText,"24/08 (vie.)");
    bitmap.drawText("午前07時00分",0,0,180,30);
    assert.equal(bitmap.lastText,"07:00 a. m.");
    w.drawText("タスク手帳",0,0,160,"left");
    assert.equal(w.lastText,"Agenda de tareas");
    f.context.SceneManager._scene=new f.context.Scene_Name();
    bitmap.drawText("夏実",0,0,100,30);
    assert.equal(bitmap.lastText,"夏実",
        "name editing must preserve original player data");
}
async function testSpeakerHeadersAreNotMixedWithSpanish(){
    const f=fixture(1);await wait(24);
    const source="夏実\nおはようございます。";
    f.$gameMessage._texts=source.split("\n");
    const message=new f.context.Window_Message();message.startMessage();
    assert.equal(message.originalStarts,1);
    await wait(42);
    assert.equal(f.posts.length,1,"only spoken line can reach neural engine");
    assert.equal(f.posts[0].text,"おはようございます。");
    f.$gameMessage._texts=source.split("\n");
    new f.context.Window_Message().startMessage();
    assert.equal(f.$gameMessage.allText(),"Natsumi\nBuenos días.",
        "speaker and speech must never be glued together");
}
async function testNativeControlsNeverReachNeuralOrChangeOnScreen(){
    const samples=[
        {src:"\\C[6]おはようございます。\\C[0]",
            expected:"\\C[6]Buenos días.\\C[0]"},
        {src:"おはようございます。%1",
            expected:"Buenos días.%1"},
        {src:"おはようございます。\${actor}",
            expected:"Buenos días.\${actor}"},
        {src:"\\N[2] おはようございます。",
            expected:"\\N[2] Buenos días."},
        {src:"\\N[2]おはようございます。",
            expected:"\\N[2] Buenos días."},
        {src:"\\N<保林 \\N[2]>「おはようございます。」",
            expected:"\\N<保林 \\N[2]>「Buenos días.」"},
        {src:"（【おはようございます。】）",expected:"（【Buenos días.】）"},
        {src:"(おはようございます。",expected:"(Buenos días."}
    ];
    for(const sample of samples){
        const f=fixture(1);await wait(22);
        f.$gameMessage._texts=[sample.src];
        new f.context.Window_Message().startMessage();
        await wait(28);
        assert.deepEqual(f.posts.map(x=>x.text),["おはようございます。"],
            "control codes must never reach the neural model");
        f.$gameMessage._texts=[sample.src];
        new f.context.Window_Message().startMessage();
        assert.equal(f.$gameMessage.allText(),sample.expected,
            "result must contain every exact RPG/format control");
    }
}
async function testApprovedBilingualCorrectionsOverridePreviousNeuralCache(){
    const shared={files:{},dirs:{}};
    const original="おはようございます。";
    const first=fixture(1,{fsState:shared});await wait(35);
    first.$gameMessage._texts=[original];
    new first.context.Window_Message().startMessage();
    await wait(35);
    const folder=path.join("/tmp","servidor-qa-juego-日本語",
        "IA Traductora",".local","Rpg","cache");
    shared.files[path.join(folder,"traducciones_aprobadas_es.json")]=
        JSON.stringify({[original]:"Buen día."});
    shared.files[path.join(folder,"nombres_es.json")]=
        JSON.stringify({"保林 隼人":"Hayato Hobayashi (revisado)"});
    const reopened=fixture(1,{fsState:shared,disconnected:true});await wait(40);
    reopened.$gameMessage._texts=[original];
    new reopened.context.Window_Message().startMessage();
    assert.equal(reopened.$gameMessage.allText(),"Buen día.",
        "owner-approved phrase must supersede an old persisted result");
    assert.equal(reopened.posts.length,0,"approved phrase never calls neural model");
    const w=new reopened.context.Window_Base();w.initialize(0,0,300,90);
    w.drawText("保林 隼人",0,0,240);
    assert.equal(w.lastText,"Hayato Hobayashi (revisado)",
        "owner-approved name reading must supersede pilot default");
}
async function testNamesStayVisibleWhenMentionedInsideDialogue(){
    const text="夏実が隣に住んでいます。";
    const f=fixture(1,{namedResponse:true});await wait(20);
    f.$gameMessage._texts=[text];
    new f.context.Window_Message().startMessage();
    await wait(30);
    assert.equal(f.posts.length,1);
    assert.ok(f.posts[0].text.indexOf("Natsumi")>=0);
    assert.equal(f.posts[0].text.indexOf("夏実"),-1,
        "Japanese proper name reading must be supplied before neural inference");
    f.$gameMessage._texts=[text];
    new f.context.Window_Message().startMessage();
    assert.equal(f.$gameMessage.allText(),"Natsumi vive al lado.");
    const bad=fixture(1);await wait(20);
    bad.$gameMessage._texts=[text];
    new bad.context.Window_Message().startMessage();await wait(30);
    bad.$gameMessage._texts=[text];
    new bad.context.Window_Message().startMessage();
    assert.equal(bad.$gameMessage.allText(),text,
        "neural output dropping a character's name must be rejected");
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
    assert.deepEqual(Array.from(f.$gameMessage._choices),["Sí","No"]);
    await wait(22);
    f.$gameMessage.setChoices(["はい","いいえ"],0,1);
    assert.deepEqual(Array.from(f.$gameMessage._choices),
        ["Sí","No"],"deterministic choices preserve their distinct indices");
    assert.equal(f.posts.length,0,"known choices must not use neural inference");
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
async function testNameIdentityMigrationAndNameSetupFirstPaint(){
    const root=path.join("/tmp","servidor-qa-juego-日本語");
    const folder=path.join(root,"IA Traductora",".local","Rpg","cache");
    const state={files:{},dirs:{[folder]:true}};
    const cacheFile=path.join(folder,"translations-ja-en-es-v2.jsonl");
    const old=[
        ["保林","Conservación"],
        ["保林 Mc","Conservación Mc"],
        ["姫乃 Hanami","Su Alteza Hanami"],
        ["※苗字は《姫乃（ひめの）》で固定です。","Apellido incorrecto."],
        ["モブ生徒Ａ","Estupenda Mob A."],
        ["モブ生徒Ｂ","Estupenda MobB."],
        ["おはようございます。","Buenos días."]
    ];
    state.files[cacheFile]=old.map(row=>JSON.stringify({schema:"ia-traductora-cache-v2",
        source:"ja",original:row[0],translated:row[1],composed:false})).join("\n")+"\n";
    const untouched=state.files[cacheFile];
    const f=fixture(1,{fsState:state,disconnected:true});await wait(40);
    const msg=new f.context.Window_Message();msg.createSubWindows();
    const name=msg._nameWindow;
    for(const [source,expected] of [
        ["保林 Mc","Hobayashi Mc"],["姫乃 Hanami","Himeno Hanami"],
        ["モブ生徒Ａ","Estudiante A"],["モブ生徒Ｂ","Estudiante B"],
        ["未知の名前","未知の名前"]
    ]){
        name.setText(source);
        assert.equal(name.assigned,expected,"name must be correct before window measures width");
        assert.equal(name.lastText,expected);
    }
    const lines=["このキャラクターの名前を決めて下さい。",
        "デフォルト名は『隼人』(はやと)です。","",
        "※苗字は《保林（ほばやし）》で固定です。"];
    f.$gameMessage._texts=lines.slice();
    msg.startMessage();
    assert.equal(f.$gameMessage.allText(),
        "Elige el nombre de este personaje.\nEl nombre predeterminado es «Hayato».\n\nEl apellido «Hobayashi» es fijo.",
        "name setup must be readable on first paint even offline");
    f.$gameMessage._texts=["おはようございます。"];msg.startMessage();
    assert.equal(f.$gameMessage.allText(),"Buenos días.","valid previous cache must survive");
    assert.ok(state.files[cacheFile].startsWith(untouched),"old journal is not deleted or overwritten");
    assert.equal(f.posts.length,0,"neither names nor fixed setup need neural translation");
}
async function testPreloadUnvisitedMapsAndBatchesWithoutReadingScripts(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const state={files:{},dirs:{[data]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:2});
    const makeMap=lines=>({events:[null,{pages:[{list:[
        {code:101,parameters:["Actor1",0,0,2]},
        ...lines.map(t=>({code:401,parameters:[t]})),
        {code:355,parameters:["実行禁止スクリプト"]},
        {code:102,parameters:[["おはようございます。"],0,0,2,0]}
    ]}]}]});
    state.files[path.join(data,"Map001.json")]=JSON.stringify(makeMap(["別の町です。"]));
    state.files[path.join(data,"Map002.json")]=JSON.stringify(makeMap(["こんにちは。","今日は晴れです。"]));
    state.files[path.join(data,"CommonEvents.json")]=JSON.stringify([null,{list:[{code:401,parameters:["ようこそ。"]}]}]);
    state.files[path.join(data,"Actors.json")]=JSON.stringify([null,{name:"未知の俳優",profile:"元気です。"}]);
    state.files[path.join(data,"Save01.json")]=JSON.stringify({text:"絶対読まない"});
    const originals=Object.assign({},state.files);
    const f=fixture(1,{fsState:state,batch:true});
    const title=new f.context.Scene_Title();title.start();assert.equal(title.starts,1);
    title.commandNewGame();
    assert.equal(title.launches,0,"cold title prepares first map without starting the original handler");
    assert.equal(title.titleActive,true,"title remains interactive during bounded preparation");
    title.update();assert.equal(title.frames,1,"native title updates are never blocked");
    // Wait for an observed readiness condition, not a scheduler-dependent
    // 350ms deadline. The test still fails if the unvisited map never loads.
    const deadline=Date.now()+2500;
    while(Date.now()<deadline&&!f.posts.some(x=>x.text==="別の町です。"))await wait(25);
    const scene=new f.context.Scene_Map();scene.createAllWindows();
    const diag=scene.windows[1].drawn.map(x=>x.text).join(" | ");
    assert.ok(f.posts.some(x=>x.text==="別の町です。"),
        "never visited map must be translated; posts="+JSON.stringify(f.posts.map(x=>x.text))+"; "+diag);
    // The final network response and cache write may be one turn behind POST.
    await wait(50);
    title.update();
    assert.equal(title.launches,1,"first-map preparation launches once");
    title.update();assert.equal(title.launches,1,"deferred start must not repeat");
    assert.ok(f.posts.some(x=>x.text==="ようこそ。"),"common events must be preloaded");
    assert.ok(f.batches.some(n=>n>1&&n<=6),"genuine batch endpoint must group requests");
    assert.ok(!f.posts.some(x=>/実行禁止|絶対読まない|未知の俳優/.test(x.text)),
        "scripts, saves and actor identities must not be sent to model");
    for(const k of Object.keys(originals))assert.equal(state.files[k],originals[k],"original game files stay byte-identical");
    f.$gameMessage._texts=["別の町です。"];const m=new f.context.Window_Message();m.startMessage();
    assert.equal(f.$gameMessage.allText(),"Buenos días.","unvisited map already available on first draw");
    assert.equal(m.originalStarts,1);
}
async function testR3PatchRepairsStandardNoticeAndKeepsColor(){
    const folder=path.join("/tmp","servidor-qa-juego-日本語",
        "IA Traductora",".local","Rpg","cache");
    const journal=path.join(folder,"translations-ja-en-es-v2.jsonl");
    const old=[
        ["この物語はフィクションであり、","(Aplausos)"],
        ["これは架空の人物です。","Es un personaje ficticio."]
    ];
    const state={files:{[journal]:old.map(row=>JSON.stringify({
        schema:"ia-traductora-cache-v2",source:"ja",original:row[0],
        translated:row[1],composed:false})).join("\n")+"\n"},dirs:{[folder]:true}};
    const f=fixture(1,{fsState:state,disconnected:true});await wait(40);
    const message=new f.context.Window_Message();
    // Synthetic Latin acronym; no commercial game content is needed.
    const lines=["この物語はフィクションであり、","これは架空の人物です。",
        "また、本作では\\C[6]ＡＢＣ\\C[0]要素が含まれております。予めご了承下さい。"];
    f.$gameMessage._texts=lines.slice();message.startMessage();
    assert.equal(message.originalStarts,1);
    assert.equal(f.$gameMessage.allText(),
        "Esta historia es ficticia y\nEs un personaje ficticio.\nAdemás, esta obra incluye elementos de tipo \\C[6]ＡＢＣ\\C[0]. Tenlo en cuenta.");
    assert.equal(f.posts.length,0,"known repaired notice works offline without new inference");
    assert.ok(state.files[journal].includes("Es un personaje ficticio."),
        "unaffected old cache is preserved");
    const online=fixture(1);await wait(25);
    online.$gameMessage._texts=lines.slice();
    const m=new online.context.Window_Message();m.startMessage();
    await wait(45);
    assert.deepEqual(online.posts.map(v=>v.text),["これは架空の人物です。"],
        "a missing ordinary line cannot force already reviewed colored lines through the neural model");
    online.$gameMessage._texts=lines.slice();m.startMessage();
    assert.equal(online.$gameMessage.allText(),
        "Esta historia es ficticia y\nBuenos días.\nAdemás, esta obra incluye elementos de tipo \\C[6]ＡＢＣ\\C[0]. Tenlo en cuenta.");
}
async function testR3P2NoticeVariantsOnFirstNativeDraw(){
    const first="この物語はフィクションであり、";
    const second="実在する人物・団体・その他法律等とは一切関係ありません。";
    const forms=[
        ["\\C[6]ＡＢＣ\\C[0]","\\C[6]ＡＢＣ\\C[0]"],
        ["\\c[6]ＡＢＣ\\c[0]","\\c[6]ＡＢＣ\\c[0]"],
        ["ＡＢＣ","ＡＢＣ"],
        ["\\c[27]Ａ　Ｂ　Ｃ\\C[0]","\\c[27]Ａ　Ｂ　Ｃ\\C[0]"],
        ["\x1bC[6]ABC\x1bc[0]","\x1bC[6]ABC\x1bc[0]"]
    ];
    for(const form of forms){
        const f=fixture(1,{disconnected:true});await wait(20);
        const last="また、本作では"+form[0]+"要素が含まれております。予めご了承下さい。";
        f.$gameMessage._texts=[first,second,last];
        const win=new f.context.Window_Message();win.startMessage();
        assert.equal(win.originalStarts,1);
        assert.equal(f.$gameMessage.allText(),
            "Esta historia es ficticia y\nno tiene relación con personas, organizaciones ni leyes reales.\nAdemás, esta obra incluye elementos de tipo "+form[1]+". Tenlo en cuenta.",
            "full notice must render even offline; no return to menu required");
        assert.equal(f.posts.length,0);
    }
}
async function testR3P2KnownLinesNotHiddenByOnePendingLine(){
    const folder=path.join("/tmp","servidor-qa-juego-日本語",
        "IA Traductora",".local","Rpg","cache");
    const journal=path.join(folder,"translations-ja-en-es-v2.jsonl");
    const first="おはようございます。",missing="明日は雨が降ります。";
    const original=[first,missing];
    const record=JSON.stringify({schema:"ia-traductora-cache-v2",source:"ja",
        original:first,translated:"Buenos días.",composed:false})+"\n";
    const shared={files:{[journal]:record},dirs:{[folder]:true}};
    const f=fixture(1,{fsState:shared,disconnected:true});await wait(35);
    const win=new f.context.Window_Message();
    f.$gameMessage._texts=original.slice();win.startMessage();
    assert.equal(win.originalStarts,1);
    assert.equal(f.$gameMessage.allText(),"Buenos días.\n"+missing,
        "one pending line must not hide a validated ordinary line");
    assert.equal(shared.files[journal],record,"mixed output is not persisted");
    // Name/variable and timing-bearing messages retain R3's safe fallback.
    const dynamic="\\N[2]"+missing;
    f.$gameMessage._texts=[first,dynamic];win.startMessage();
    assert.equal(f.$gameMessage.allText(),first+"\n"+dynamic);
    const online=fixture(20,{fsState:shared});await wait(35);
    const second=new online.context.Window_Message();
    online.$gameMessage._texts=original.slice();second.startMessage();
    assert.equal(online.$gameMessage.allText(),"Buenos días.\n"+missing);
    await wait(65);
    assert.deepEqual(online.posts.map(x=>x.text),[missing],
        "only missing Japanese line reaches the model");
    assert.equal(online.$gameMessage.allText(),"Buenos días.\n"+missing,
        "late response does not restart or alter the active message");
    online.$gameMessage._texts=original.slice();second.startMessage();
    assert.equal(online.$gameMessage.allText(),"Buenos días.\nBuenos días.");
    assert.equal(second.originalStarts,2);
}

async function testTitlePreparationCanBeSkipped(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const state={files:{},dirs:{[data]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1});
    state.files[path.join(data,"Map001.json")]=JSON.stringify({events:[null,{pages:[{
        list:[{code:401,parameters:["はじめまして。"]}]
    }]}]});
    const f=fixture(300,{fsState:state,disconnected:true});
    const title=new f.context.Scene_Title();title.start();
    title.commandNewGame();
    assert.equal(title.launches,0);
    title.commandNewGame();
    assert.equal(title.launches,1,"explicit second selection skips preparation");
    title.update();assert.equal(title.launches,1);
}
async function testPermanentQualityFailureIsNotRetried(){
    const f=fixture(1,{qualityReject:true});await wait(25);
    const original="おはようございます。";
    for(let i=0;i<3;i++){
        f.$gameMessage._texts=[original];new f.context.Window_Message().startMessage();
        await wait(30);
    }
    await wait(950);
    assert.equal(f.posts.length,1,"permanent QA rejection is not a transport error");
    assert.equal(f.$gameMessage.allText(),original);
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
    await testNameIdentityMigrationAndNameSetupFirstPaint();
    await testPreloadUnvisitedMapsAndBatchesWithoutReadingScripts();
    await testR3PatchRepairsStandardNoticeAndKeepsColor();
    await testR3P2NoticeVariantsOnFirstNativeDraw();
    await testR3P2KnownLinesNotHiddenByOnePendingLine();
    await testTitlePreparationCanBeSkipped();
    await testPermanentQualityFailureIsNotRetried();
    await testApprovedBilingualCorrectionsOverridePreviousNeuralCache();
    await testFullNativeMenusAndNameOnlyText();
    await testSpeakerHeadersAreNotMixedWithSpanish();
    await testNativeControlsNeverReachNeuralOrChangeOnScreen();
    await testNamesStayVisibleWhenMentionedInsideDialogue();
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
