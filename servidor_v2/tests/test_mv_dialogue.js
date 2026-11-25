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
    const posts=[],batches=[],jsonParseSizes=options.jsonParseSizes||[],state=options.fsState||{files:{},dirs:{}};
    const read=state.files,dirs=state.dirs;
    const source=fs.readFileSync(
        path.join(__dirname,"..","plugin","IATraductora.js"),"utf8");
    const root=options.root||path.join("/tmp","servidor-qa-juego-日本語");
    const content=options.mz||options.noWww?root:path.join(root,"www");
    const descriptor=path.join(content,"data","IATraductora","bridge.json");
    if(options.mz){
        for(const n of ["rmmz_core","rmmz_managers","rmmz_objects","rmmz_scenes","rmmz_windows"])read[path.join(content,"js",n+".js")]="// MZ synthetic fixture";
        read[path.join(content,"data","System.json")]=read[path.join(content,"data","System.json")]||"{}";
        dirs[path.join(content,"data")]=true;
    }else read[path.join(content,"js","rpg_core.js")]="// mock rpg core";
    read[path.join(content,"js","plugins.js")]="var $plugins = [];";
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
            setTimeout(()=>callback(null,Array.from(new Set(Object.keys(read).concat(Object.keys(dirs)).filter(k=>path.dirname(k)===p)
                .map(k=>path.basename(k))))),0);
        },
        readFile(p,encoding,callback){
            setTimeout(()=>{
                if(!(p in read)){
                    const e=Error("not found");e.code="ENOENT";
                    callback(e);return;
                }
                callback(null,read[p]);
            },p.endsWith(".jsonl")?(options.cacheReadDelay||0):0);
        },
        appendFile(p,value,opts,callback){
            setTimeout(()=>{
                if(options.appendFailures>0){options.appendFailures--;callback(Error("temporary disk error"));return;}
                read[p]=(read[p]||"")+String(value);callback(null);
            },1);
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
        if(options.responses&&Object.prototype.hasOwnProperty.call(options.responses,body.text))
            return {translated:options.responses[body.text]};
        if(options.namedResponse&&body.text.indexOf("Natsumi")>=0)
            return {translated:"Natsumi vive al lado."};
        return {translated:body.source==="ja"?"Buenos días.":"Hello"===body.text?"Hola.":"Buenos días."};
    }
    function Rectangle(x,y,width,height){Object.assign(this,{x,y,width,height});}
    function Window_Base(rect){if(options.mz&&rect)this.initialize(rect);}
    Window_Base.prototype.initialize=function(x,y,w,h){
        if(options.mz){assert.ok(x instanceof Rectangle,"MZ requires Rectangle");[x,y,w,h]=[x.x,x.y,x.width,x.height];}
        this.x=x;this.y=y;this.width=w;this.height=h;
        this.contents={fontSize:12,outlineWidth:1,clear(){}};
    };
    Window_Base.prototype.contentsWidth=function(){return this.width-20};
    Window_Base.prototype.hide=function(){this.visible=false;};
    Window_Base.prototype.show=function(){this.visible=true;};
    Window_Base.prototype.drawTextEx=function(t,x,y){
        this.lastTextEx=t;
        if(this._testAmbientPaint&&this.contents)this.contents.drawText(t,x,y,this.contents.width-x,32);
        return String(t).length;
    };
    Window_Base.prototype.drawText=function(t,x,y){
        this.lastText=t;
        if(!this.drawn)this.drawn=[];
        this.drawn.push({text:t,y:y});
    };
    function Bitmap(w,h){
        this.width=w||0;this.height=h||0;this.fontFace="GameFont";this.fontSize=24;
        this.textColor="#ffffff";this.outlineWidth=2;this.paintOpacity=255;this.ops=[];
    }
    Bitmap.prototype.measureTextWidth=function(t){this.measuredFont=this.fontFace;return String(t).length*12;};
    Bitmap.prototype.drawText=function(t,x,y,w,h){
        this.lastText=String(t);this.ops.push({text:String(t),x:x||0,y:y||0,w:w||0,h:h||0,color:this.textColor,font:this.fontFace});return t;
    };
    Bitmap.prototype.clearRect=function(x,y,w,h){
        this.ops=this.ops.filter(v=>v.x<x||v.y<y||v.x>=x+w||v.y>=y+h);
        this.clears=(this.clears||0)+1;
    };
    Bitmap.prototype.blt=function(src,sx,sy,sw,sh,dx,dy){
        const copied=src.ops.filter(v=>v.x>=sx&&v.y>=sy&&v.x<sx+sw&&v.y<sy+sh)
            .map(v=>Object.assign({},v,{x:v.x-sx+dx,y:v.y-sy+dy}));
        this.ops=this.ops.concat(copied);
    };
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
    Window_Message.prototype.startMessage=function(){
        this.originalStarts++;
        if(options.nativePaint){
            this.pause=false;this._textState={text:$gameMessage.allText()
                .replace(/<\/?wordwrap>/gi,"").replace(/\\n[cr]?<[^>]+>/gi,"")
                .replace(/\\m\[things\]/gi,"\x1bC[11]")
                .replace(/\\m\[quests\]/gi,"\x1bC[23]")
                .replace(/\\c\[/gi,"\x1bC[").replace(/\\i\[/gi,"\x1bI["),index:0,x:168,left:168,y:0,height:32};
            this.contents=new Bitmap(options.nativeWidth||900,options.nativeHeight||128);
            this.contents.drawText("FACE",0,0,144,128);
            this.newPage(this._textState);
        }
    };
    if(options.nativePaint){
        Window_Message.prototype.textColor=function(i){return "color-"+i;};
        Window_Message.prototype.newPage=function(){this.pages=(this.pages||0)+1;};
        Window_Message.prototype.finishPage=function(){
            if(this.contents&&this._textState)this.contents.drawText(this._textState.text,168,0,720,32);
            this._textState=null;this.pause=true;
        };
        Window_Message.prototype.isAnySubWindowActive=function(){return !!this.choiceActive;};
    }
    Window_Message.prototype.update=function(){this.updates++};
    Window_Message.prototype.terminateMessage=function(){this.terminated=(this.terminated||0)+1;};
    Window_Message.prototype.updateWait=function(){return false;};
    if(options.nativeWait){
        Window_Message.prototype.startWait=function(n){this._waitCount=n;};
        Window_Message.prototype.updateWait=function(){
            if(this._waitCount>0){this._waitCount--;return true;}
            return false;
        };
    }
    function Scene_Map(){this.windows=[]}
    Scene_Map.prototype.createAllWindows=function(){};
    Scene_Map.prototype.update=function(){};
    Scene_Map.prototype.addWindow=function(win){this.windows.push(win)};
    function Game_Message(){this._texts=[];this._choices=[];}
    Game_Message.prototype.hasText=function(){return this._texts.length>0;};
    Game_Message.prototype.allText=function(){return this._texts.join("\n");};
    Game_Message.prototype.add=function(text){this._texts.push(text);};
    Game_Message.prototype.setChoices=function(choices){
        this._choices=choices.slice();
    };
    Game_Message.prototype.clear=function(){
        this._texts=[];this._choices=[];this._choiceCallback=null;
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
    const iconAtlas=new Bitmap(512,512);
    iconAtlas.ops.push({text:"ICON17",x:32,y:32,w:32,h:32,color:"icon"});
    iconAtlas.isReady=()=>true;
    const context={
        ImageManager:{loadSystem(name){assert.equal(name,"IconSet");return iconAtlas;}},
        window:{location:{pathname:options.pathname||path.join(content,"index.html")},__IA_TRADUCTORA_TEST_HOOKS__:options.testHooks===true},
        document:options.scriptSrc?{currentScript:{src:options.scriptSrc}}:null,
        Utils:{isNwjs:()=>true,RPGMAKER_NAME:options.mz?"MZ":"MV"},Rectangle,ColorManager:{textColor:i=>"color-"+i},
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
        JSON:{
            parse(value,reviver){jsonParseSizes.push(String(value).length);return JSON.parse(value,reviver);},
            stringify(value,replacer,space){return JSON.stringify(value,replacer,space);}
        },
        setTimeout(fn,delay){const timer=setTimeout(fn,delay);timer.unref();return timer;},
        clearTimeout,setInterval(){return 1},
        Window_Base,Window_Message,Scene_Map,Game_Message,Bitmap,Scene_Name,Scene_Title,
        Graphics:{boxWidth:1280},
        Input:{keyMapper:{},isTriggered(){return false}},
        SceneManager:{_scene:null},
        $gameMessage,$plugins:options.plugins||[]
    };
    if(options.configure)options.configure(context);
    vm.runInNewContext(source,context,{filename:"IATraductora.js"});
    return {context,posts,batches,$gameMessage,jsonParseSizes,spawnCount:()=>spawnCount};
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
async function testDirectStartFallbackDoesNotOverwriteNextScene(){
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

async function testR4EnglishFormatContextAndStaleCache(){
    const root=path.join("/tmp","servidor-qa-juego-日本語");
    const folder=path.join(root,"IA Traductora",".local","Rpg","cache");
    const journal=path.join(folder,"translations-ja-en-es-v2.jsonl");
    const plain="A visitor opens the gate and enters the hall.";
    const raw="<WordWrap>A visitor opens the \\m[things]gate\\c[0] and enters the \\c[6]hall\\c[0].";
    const bad="Hay un sonido <<<W wordwordWrap> Hay Hay Hay \\m[things]gate\\c[0] \\c[6]hall\\c[0].";
    const old=JSON.stringify({schema:"ia-traductora-cache-v2",source:"en",original:raw,translated:bad,composed:true})+"\n";
    const shared={files:{[journal]:old},dirs:{[folder]:true}};
    const responses={};responses[plain]="Un visitante abre la puerta y entra en el salón.";
    responses.gate="puerta";responses.hall="salón";
    const plugins=[{name:"YEP_X_MessageMacros1",status:true,parameters:{"Macro 1 Name":"Things","Macro 1 Text":"\\c[11]"}}];
    const f=fixture(1,{fsState:shared,responses,nativeWait:true,nativePaint:true,plugins});await wait(30);
    const m=new f.context.Window_Message();
    const scene=new f.context.Scene_Map();f.context.SceneManager._scene=scene;
    f.$gameMessage._texts=[raw];m.startMessage();
    assert.equal(m.originalStarts,1,"untranslated text cannot pause native message start");
    assert.equal(m.updateWait(),false,"no artificial message wait");
    m.finishPage();const bitmap=m.contents;
    await wait(60);m.update();
    assert.equal(m.originalStarts,1,"late answer does not restart native message");
    assert.equal(f.$gameMessage.allText(),raw,"late result cannot mutate active source");
    assert.equal(scene.windows.length,0,"late translation must never create a window");
    assert.equal(m.contents,bitmap,"native bitmap instance remains the same");
    assert.equal(bitmap.clears,1,"replace the English in its original region");
    assert.ok(bitmap.ops.some(x=>x.text==="FACE"),"native face retained");
    assert.ok(bitmap.ops.some(x=>x.text==="puerta"&&x.color==="color-11"));
    assert.ok(bitmap.ops.some(x=>x.text==="salón"&&x.color==="color-6"));
    assert.ok(!bitmap.ops.some(x=>x.text.includes("A visitor")));
    m.terminateMessage();assert.equal(m.terminated,1);assert.equal(m._iaLateTicket,null);
    f.$gameMessage._texts=[raw];m.startMessage();
    const expected="<WordWrap>Un visitante abre la \\m[things]puerta\\c[0] y entra en el \\c[6]salón\\c[0].";
    assert.equal(m.originalStarts,2);
    assert.equal(f.$gameMessage.allText(),expected);
    assert.ok(f.posts.some(x=>x.text===plain),"model sees complete natural context");
    assert.ok(f.posts.some(x=>x.text==="gate")&&f.posts.some(x=>x.text==="hall"),
        "short colored words are no longer skipped");
    assert.ok(f.posts.every(x=>!/[<>\\]/.test(x.text)),"never send controls to model");
    await wait(30);
    const reopened=fixture(1,{fsState:shared,disconnected:true});await wait(35);
    reopened.$gameMessage._texts=[raw];new reopened.context.Window_Message().startMessage();
    assert.equal(reopened.$gameMessage.allText(),f.$gameMessage.allText());
    assert.equal(reopened.posts.length,0);
}
async function testR4InkAndCsvReadOnlyPreload(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const ink=path.join(data,"ink"),loc=path.join(data,"localization");
    const state={files:{},dirs:{[data]:true,[ink]:true,[loc]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1});
    const story="There is a sound at the gate.";
    const plain="A traveler enters the hall.";
    state.files[path.join(ink,"main.json")]=JSON.stringify({inkVersion:21,root:[
        ["ev","str","^this is an internal value","/str","/ev","#","^this is a private tag","/#",
        "^There is a sound at the (mt:gate).","\n",null],
        {branch:["^A traveler enters the (mp:hall).","\n",null],
         "global decl":["^this is global data",null]}
    ],listDefs:{example:{"this is a key":1}}});
    state.files[path.join(ink,"test.json")]=JSON.stringify({inkVersion:21,root:["^this is a test backup",null]});
    state.files[path.join(loc,"strings.csv")]='id,en,es\r\nK1,"Hello, how are you today?",\r\nK2,"We are here.",\r\nK3,"=this is a formula",';
    state.files[path.join(loc,"unrelated.csv")]="id,script\r\nA,this is a command";
    const originals=Object.assign({},state.files);
    const responses={[story]:"Se oye un ruido en la puerta.",[plain]:"Un viajero entra en el salón.",
        gate:"puerta",hall:"salón","Hello, how are you today?":"Hola, ¿cómo estás hoy?",
        "We are here.":"Estamos aquí."};
    const f=fixture(1,{fsState:state,batch:true,responses,nativeWait:true});
    new f.context.Scene_Title().start();
    const deadline=Date.now()+2500;
    while(Date.now()<deadline&&![story,plain,"We are here."].every(v=>f.posts.some(x=>x.text===v)))await wait(25);
    await wait(70);
    assert.ok([story,plain,"We are here."].every(v=>f.posts.some(x=>x.text===v)),
        "preload compiled unseen story and schema-validated CSV");
    assert.ok(!f.posts.some(x=>/internal value|private tag|global data|test backup|formula|command/.test(x.text)));
    for(const k of Object.keys(originals))assert.equal(state.files[k],originals[k],"data files are read-only");
    const m=new f.context.Window_Message();
    f.$gameMessage._texts=["<WordWrap>A traveler enters the \\m[places]hall\\c[0]."];m.startMessage();
    assert.equal(m.originalStarts,1,"unvisited compiled text is ready on first draw");
    assert.equal(f.$gameMessage.allText(),"<WordWrap>Un viajero entra en el \\m[places]salón\\c[0].");
    const smart="“We are here.”";
    f.$gameMessage._texts=[smart];m.startMessage();await wait(30);m.startMessage();
    assert.ok(f.posts.some(x=>x.text===smart&&x.source==="en"),"typographic quotes detected");
}


async function testR4P2NoStaleLateOverlayAndNoArtificialWait(){
    const sentence="We are ready to open the gate.";
    const response={};response[sentence]="Estamos listos para abrir la puerta.";
    const f=fixture(90,{responses:response,nativeWait:true,nativePaint:true});await wait(30);
    const scene=new f.context.Scene_Map();f.context.SceneManager._scene=scene;
    const m=new f.context.Window_Message();f.$gameMessage._texts=[sentence];m.startMessage();
    assert.equal(m.originalStarts,1);assert.equal(m.updateWait(),false);
    m.finishPage();const before=JSON.stringify(m.contents.ops);
    f.context.SceneManager._scene=new f.context.Scene_Map();
    await wait(120);m.update();
    assert.equal(JSON.stringify(m.contents.ops),before,"no old dialogue may appear in another scene");
    assert.equal(m._iaLateTicket,null);
    assert.equal(m.originalStarts,1);assert.equal(m.updates,1);
}
async function testR4P2QuestMetadataAndVisibleRefresh(){
    const root=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const state={files:{},dirs:{[root]:true}};
    state.files[path.join(root,"System.json")]=JSON.stringify({startMapId:1});
    const title="Find the missing key",desc="You must find the key before dawn.",obj="Search the garden.";
    const quest=JSON.stringify({Title:title,Description:JSON.stringify([JSON.stringify(desc)]),
        "Objectives List":JSON.stringify([obj]),"Rewards List":JSON.stringify(["20 gold"]),
        From:"Aldren",Location:"Westbridge", "Visible Objectives":"[1]",Script:"this is never a display field"});
    const plugins=[{name:"YEP_QuestJournal",status:true,parameters:{"Quest 1":quest}},
        {name:"YEP_X_MoreQuests1",status:false,parameters:{"Quest 101":JSON.stringify({Title:"This is disabled content."})}},
        {name:"Unrelated",status:true,parameters:{"Quest 1":JSON.stringify({Title:"This is unrelated content."})}}];
    const untouched=JSON.stringify(plugins);
    const responses={[title]:"Encuentra la llave perdida",[desc]:"Debes encontrar la llave antes del amanecer.",
        [obj]:"Registra el jardín.","20 gold":"20 monedas","This is a live objective.":"Este es un objetivo activo."};
    const f=fixture(5,{fsState:state,plugins,batch:true,responses});
    new f.context.Scene_Title().start();
    const deadline=Date.now()+2500;
    while(Date.now()<deadline&&![title,desc,obj].every(x=>f.posts.some(p=>p.text===x)))await wait(25);
    await wait(70);
    assert.ok([title,desc,obj].every(x=>f.posts.some(p=>p.text===x)),"nested mission fields inventoried before opening quest journal");
    assert.ok(!f.posts.some(p=>/disabled content|unrelated content|never a display field|Aldren|Westbridge/.test(p.text)));
    assert.equal(JSON.stringify(plugins),untouched,"quest parameters are not modified");
    const scene=new f.context.Scene_Map();f.context.SceneManager._scene=scene;
    function Window_QuestData(){this.initialize(0,0,400,200);this.parent=scene;this.visible=true;this.selection=3;this.refreshes=0;}
    Window_QuestData.prototype=Object.create(f.context.Window_Base.prototype);
    Window_QuestData.prototype.constructor=Window_QuestData;
    Window_QuestData.prototype.index=function(){return this.selection;};
    Window_QuestData.prototype.refresh=function(){this.refreshes++;this.drawTextEx("This is a live objective.",0,0);};
    const win=new Window_QuestData();
    win.drawText(title,0,0,400);assert.equal(win.lastText,"Encuentra la llave perdida");
    win.drawTextEx(desc,0,0);assert.equal(win.lastTextEx,"Debes encontrar la llave antes del amanecer.");
    win.refresh();assert.equal(win.lastTextEx,"This is a live objective.");
    await wait(160);assert.equal(win.lastTextEx,"Este es un objetivo activo.");
    assert.equal(win.selection,3);assert.equal(win.refreshes,2);
}
async function testR4P2PriorityCommonAndInkChoice(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data"),ink=path.join(data,"ink");
    const state={files:{},dirs:{[data]:true,[ink]:true}};
    const initial="We have arrived at the city.",background="The far village is quiet.",choice="Open the gate.";
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1});
    state.files[path.join(data,"Map001.json")]=JSON.stringify({events:[null,{pages:[{list:[{code:117,parameters:[2]}]}]}]});
    state.files[path.join(data,"CommonEvents.json")]=JSON.stringify([null,
        {list:[{code:401,parameters:[background]}]},
        {list:[{code:117,parameters:[3]}]},
        {list:[{code:401,parameters:[initial]},{code:117,parameters:[2]}]}]);
    state.files[path.join(ink,"main.json")]=JSON.stringify({inkVersion:21,root:[[
        "ev","str","^"+choice,"/str","/ev",{"*":"dest","flg":4},
        "ev","str","^This is an internal string.","/str","/ev","pop",null],null]});
    const f=fixture(1,{fsState:state,batch:true});
    new f.context.Scene_Title().start();
    const deadline=Date.now()+2500;
    while(Date.now()<deadline&&![initial,background,choice].every(v=>f.posts.some(x=>x.text===v)))await wait(25);
    assert.ok([initial,background,choice].every(v=>f.posts.some(x=>x.text===v)),"transitive event chain and literal choice are prepared");
    assert.ok(f.posts.findIndex(x=>x.text===initial)<f.posts.findIndex(x=>x.text===background),"starting common event ahead of distant event");
    assert.ok(!f.posts.some(x=>/internal string/.test(x.text)));
}


async function testR4P3NativeSafetyAndNames(){
    const plugins=[{name:"YEP_X_MessageMacros1",status:true,parameters:{
        "Macro 1 Name":"People","Macro 1 Text":"\\c[25]",
        "Macro 2 Name":"Quests","Macro 2 Text":"\\c[23]"}}];
    const folder=path.join("/tmp","servidor-qa-juego-日本語","IA Traductora",".local","Rpg","cache");
    const journal=path.join(folder,"translations-ja-en-es-v2.jsonl");
    const person="<WordWrap>\\n<Captain>\\c[25]Silver-Fox\\c[0] is here.";
    const wrong="<WordWrap>\\n<Captain>\\c[25]Zorro Plateado\\c[0] está aquí.";
    const quest="<WordWrap>Choose a \\m[Quests]Quest\\c[0] from the categories.";
    const qbad="<WordWrap>Elija una \\m[Quests]búsqueda\\c[0] de las categorías.";
    const shared={files:{[journal]:[[person,wrong],[quest,qbad]].map(v=>JSON.stringify({
        schema:"ia-traductora-cache-v2",source:"en",original:v[0],translated:v[1],composed:true})).join("\n")+"\n"},dirs:{[folder]:true}};
    const f=fixture(1,{plugins,fsState:shared,disconnected:true});await wait(40);
    const m=new f.context.Window_Message();
    f.$gameMessage._texts=[person];m.startMessage();
    assert.equal(f.$gameMessage.allText(),"<WordWrap>\\n<Captain>\\c[25]Silver-Fox\\c[0] está aquí.","only author-declared proper-name color is preserved");
    f.$gameMessage._texts=[quest];m.startMessage();
    assert.equal(f.$gameMessage.allText(),"<WordWrap>Elija una \\m[Quests]misión\\c[0] de las categorías.");
    assert.equal(f.posts.length,0,"repair existing journal without inference");
    const bitmap=new f.context.Bitmap(500,100);
    bitmap.drawText("-Main Quests (3)",0,0,500,30);
    assert.equal(bitmap.lastText,"-Misiones principales (3)","custom book category and count");
    const long="We are ready to go.";
    const responses={[long]:"Estamos preparados para emprender un recorrido de considerable duración."};
    const slow=fixture(10,{nativePaint:true,nativeWidth:320,nativeHeight:32,responses});
    await wait(30);
    const scene=new slow.context.Scene_Map();slow.context.SceneManager._scene=scene;
    const win=new slow.context.Window_Message();
    slow.$gameMessage._texts=[long];win.startMessage();win.finishPage();
    const before=JSON.stringify(win.contents.ops);await wait(40);win.update();
    assert.equal(JSON.stringify(win.contents.ops),before,"overflow never erases or clips the original");
    assert.equal(scene.windows.length,0);
    const command="We are here.\\!";
    slow.$gameMessage._texts=[command];win.startMessage();win.finishPage();await wait(30);win.update();
    assert.equal(win._iaLateTicket,null,"wait escape cannot be replayed by late renderer");
    assert.equal(scene.windows.length,0);
}
async function testR4P3PageAndChoiceSafety(){
    const line="We are here.",response={[line]:"Estamos aquí."};
    const f=fixture(25,{responses:response,nativePaint:true});await wait(30);
    const scene=new f.context.Scene_Map();f.context.SceneManager._scene=scene;
    const m=new f.context.Window_Message();f.$gameMessage._texts=[line];m.startMessage();
    m.newPage(m._textState);m.finishPage();const before=JSON.stringify(m.contents.ops);
    await wait(50);m.update();
    assert.equal(JSON.stringify(m.contents.ops),before,"multi-page messages do not get repainted as one page");
    const other="We are ready.";f.$gameMessage._texts=[other];m.startMessage();m.finishPage();
    m.choiceActive=true;const active=JSON.stringify(m.contents.ops);await wait(45);m.update();
    assert.equal(JSON.stringify(m.contents.ops),active,"active choices never receive a late repaint");
    assert.equal(scene.windows.length,0);
}


async function testR4P4ShortTextAndMacroAlias(){
    const plugins=[{name:"YEP_X_MessageMacros1",status:true,parameters:{"Macro 1 Name":"Things","Macro 1 Text":"\\c[11]"}}];
    const raw="Ancient \\m[Things]writing\\c[0]? Absurd!";
    const result="¿Escritura \\m[Things]antigua\\c[0]? ¡Absurdo!";
    const folder=path.join("/tmp","servidor-qa-juego-日本語","IA Traductora",".local","Rpg","cache");
    const journal=path.join(folder,"translations-ja-en-es-v2.jsonl");
    const state={files:{[journal]:JSON.stringify({schema:"ia-traductora-cache-v2",source:"en",original:raw,translated:result,composed:true})+"\n"},dirs:{[folder]:true}};
    const f=fixture(1,{plugins,fsState:state,disconnected:true});await wait(40);
    const m=new f.context.Window_Message();
    f.$gameMessage._texts=[raw.replace("\\m[Things]","\\c[11]")];m.startMessage();
    assert.equal(f.$gameMessage.allText(),result.replace("\\m[Things]","\\c[11]"),
        "same words and equivalent macro/color use existing cache while preserving original controls");
    assert.equal(f.posts.length,0);
    const short='"Typical. Always looking out for herself."';
    const n=fixture(1,{responses:{[short]:'"Típico. Siempre pensando en sí misma."'}});await wait(25);
    n.$gameMessage._texts=[short];new n.context.Window_Message().startMessage();
    await wait(50);n.$gameMessage._texts=[short];new n.context.Window_Message().startMessage();
    assert.equal(n.$gameMessage.allText(),'"Típico. Siempre pensando en sí misma."');
}
async function testR4P4LateIconAndAmount(){
    const text="\\nc<Guide>We will pay \\i[17]5 coins.";
    const f=fixture(5,{nativePaint:true,nativeWait:true,responses:{"We will pay":"Pagaremos","5 coins.":"5 monedas."}});await wait(35);
    const scene=new f.context.Scene_Map();f.context.SceneManager._scene=scene;
    const m=new f.context.Window_Message();f.$gameMessage._texts=[text];m.startMessage();
    assert.equal(m.originalStarts,1);assert.equal(m.updateWait(),false);
    m.finishPage();const bitmap=m.contents;
    const deadline=Date.now()+900;
    while(Date.now()<deadline&&!bitmap.clears){await wait(25);m.update();}
    assert.equal(m.contents,bitmap);assert.equal(scene.windows.length,0);
    assert.equal(bitmap.clears,1,"late icon-bearing message repaints original");
    assert.ok(bitmap.ops.some(x=>x.text==="ICON17"),"native icon retained");
    assert.ok(bitmap.ops.some(x=>x.text==="5"),"amount retained");
    assert.ok(bitmap.ops.some(x=>x.text==="Pagaremos"));
    assert.ok(!bitmap.ops.some(x=>x.text.includes("We will pay")));
    assert.ok(f.posts.every(x=>!/[\\<>]/.test(x.text)),"speaker and icon codes never reach inference");
}
async function testR4P4FullQuestTemplateAndAccents(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const folder=path.join("/tmp","servidor-qa-juego-日本語","IA Traductora",".local","Rpg","cache");
    const title="Find the missing key",desc="The key is hidden in the garden.",objective="Look in the garden.";
    const entries=[[title,"Encuentra la llave perdida"],[desc,"La llave está escondida en el jardín."],[objective,"Busca en el jardín."]];
    const state={files:{},dirs:{[data]:true,[folder]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1});
    state.files[path.join(folder,"translations-ja-en-es-v2.jsonl")]=entries.map(v=>JSON.stringify({
        schema:"ia-traductora-cache-v2",source:"en",original:v[0],translated:v[1],composed:false})).join("\n")+"\n";
    const plugins=[{name:"YEP_QuestJournal",status:true,parameters:{
        "Quest Data Window":JSON.stringify({"Font Face":"Handwritten","Quest Data Format":"From: %3"}),
        "Quest 1":JSON.stringify({Title:title,From:"Aldren Fox",Location:"Castle",Description:JSON.stringify([desc]),"Objectives List":JSON.stringify([objective])})}}];
    const before=JSON.stringify(plugins);
    const f=fixture(1,{fsState:state,plugins,disconnected:true});await wait(80);
    function Window_QuestData(){this.initialize(0,0,600,500);}
    Window_QuestData.prototype=Object.create(f.context.Window_Base.prototype);Window_QuestData.prototype.constructor=Window_QuestData;
    const win=new Window_QuestData();
    const template="\\c[15]<WordWrap>\\{"+title+"\\}\n<br>From: Aldren Fox\n<br>Location: Castle\n<br>Description:\n<br>"+desc+"\n<br>Objectives:\n<br>"+objective+"\\c[0]";
    win.drawTextEx(template,0,0);
    assert.equal(win.lastTextEx,"\\c[15]<WordWrap>\\{Encuentra la llave perdida\\}\n<br>De: Aldren Fox\n<br>Ubicación: Castillo\n<br>Descripción:\n<br>La llave está escondida en el jardín.\n<br>Objetivos:\n<br>Busca en el jardín.\\c[0]");
    win.drawTextEx("Location: Westbridge",0,0);assert.equal(win.lastTextEx,"Ubicación: Westbridge");
    win.drawTextEx("\\c[15]Available (4)",0,0);assert.equal(win.lastTextEx,"\\c[15]Disponibles (4)");
    win.drawTextEx("\\c[15]-Tutorial Quests (1)",0,0);assert.equal(win.lastTextEx,"\\c[15]-Misiones de tutorial (1)");
    const bitmap=new f.context.Bitmap(500,100);bitmap.fontFace="Handwritten";
    bitmap.drawText("Barón",0,0,400,40);assert.equal(bitmap.ops[0].font,"Georgia, serif");
    bitmap.measureTextWidth("Barón");assert.equal(bitmap.measuredFont,"Georgia, serif");
    assert.equal(bitmap.fontFace,"Handwritten","font fallback does not permanently change font");
    bitmap.drawText("ABC",0,0,400,40);assert.equal(bitmap.ops[1].font,"Handwritten");
    assert.equal(JSON.stringify(plugins),before,"no quest objects, parameters or script changes");
    assert.equal(f.posts.length,0);
}
async function testR4P4AmbientNativeCaption(){
    const text="Keep moving, friend.",response="Sigue caminando, amigo.";
    const plugins=[{name:"GALV_TimedMessagePopups",status:true,parameters:{}}];
    const f=fixture(10,{plugins,responses:{[text]:response,"Wait here, friend.":"Espera aquí, amigo."}});await wait(30);
    const scene=new f.context.Scene_Map();f.context.SceneManager._scene=scene;
    function Window_GalvCaption(){
        this.contents=new f.context.Bitmap(500,80);this.parent=scene;this.visible=true;
        this.duration=75;this._testAmbientPaint=true;
    }
    Window_GalvCaption.prototype=Object.create(f.context.Window_Base.prototype);
    Window_GalvCaption.prototype.constructor=Window_GalvCaption;
    Window_GalvCaption.prototype.textColor=function(i){return "color-"+i;};
    const win=new Window_GalvCaption(),bitmap=win.contents;
    win.drawTextEx(text,4,0);assert.equal(bitmap.lastText,text);
    const deadline=Date.now()+900;
    while(Date.now()<deadline&&!bitmap.clears)await wait(20);
    assert.equal(win.contents,bitmap);assert.equal(scene.windows.length,0);
    assert.equal(win.duration,75);assert.equal(bitmap.clears,1);
    assert.ok(bitmap.ops.some(x=>x.text==="Sigue"));
    assert.ok(!bitmap.ops.some(x=>x.text===text));
    const stale=new Window_GalvCaption();stale.drawTextEx("Wait here, friend.",4,0);
    stale.visible=false;await wait(60);
    assert.ok(!stale.contents.clears,"expired caption never reappears");
}


async function testR4P5QuestOverrideAndCaptionAlias(){
    const folder=path.join("/tmp","servidor-qa-juego-日本語","IA Traductora",".local","Rpg","cache");
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const questTitle="Find the missing letter",desc="The letter is hidden in the garden.";
    const tag="<c:3,160,0,WindowSpeech,-40>",body="Keep walking, friend.";
    const colored="Keep walking, \\c[5]friend\\c[0].";
    const cache=[
        [questTitle,"Encuentra la carta perdida",false],
        [desc,"La carta está escondida en el jardín.",false],
        ["Castle Westbridge","Castillo Westbridge",false],
        [tag+body,tag+"Sigue caminando, amigo.",true],
        [colored,"Sigue caminando, \\c[5]amigo\\c[0].",true]
    ];
    const state={files:{},dirs:{[folder]:true,[data]:true}};
    state.files[path.join(folder,"translations-ja-en-es-v2.jsonl")]=cache.map(v=>JSON.stringify({
        schema:"ia-traductora-cache-v2",source:"en",original:v[0],translated:v[1],composed:v[2]})).join("\n")+"\n";
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1});
    const plugins=[
        {name:"YEP_QuestJournal",status:true,parameters:{"Quest 1":JSON.stringify({
            Title:questTitle,Description:JSON.stringify([JSON.stringify(desc)]),From:"Baroness",
            Location:"Castle Westbridge"})}},
        {name:"GALV_TimedMessagePopups",status:true,parameters:{}}
    ];
    const before=JSON.stringify(plugins);
    const f=fixture(2,{fsState:state,plugins,disconnected:true,configure(c){
        c.Window_Base.prototype.convertEscapeCharacters=function(v){return v;};
        function Window_QuestData(){this.initialize(0,0,600,500);}
        Window_QuestData.prototype=Object.create(c.Window_Base.prototype);
        Window_QuestData.prototype.constructor=Window_QuestData;
        // The author has captured a base conversion before the IA loads,
        // and its own drawing method does not invoke Window_Base.drawTextEx.
        Window_QuestData.prototype.convertEscapeCharacters=function(text){return text;};
        Window_QuestData.prototype.drawTextEx=function(text){
            this.lastTextEx=this.convertEscapeCharacters(text);return 17;
        };
        c.window.Window_QuestData=Window_QuestData;
        function Window_Caption(){this.initialize(0,0,500,80);this.duration=90;}
        Window_Caption.prototype=Object.create(c.Window_Base.prototype);
        Window_Caption.prototype.constructor=Window_Caption;
        Window_Caption.prototype.drawTextEx=function(text){
            this.lastTextEx=this.convertEscapeCharacters(text);return 9;
        };
        c.window.Window_Caption=Window_Caption;
        function Game_Interpreter(){}
        Game_Interpreter.prototype.command101=function(){
            this.captured=this._list[this._index+1].parameters[0];this._index++;return true;
        };
        c.Game_Interpreter=Game_Interpreter;
    }});
    await wait(100);
    const c=f.context,scene=new c.Scene_Map();c.SceneManager._scene=scene;
    const w=new c.window.Window_QuestData();
    const original="\\c[15]<WordWrap>\\{"+questTitle+"\\}\\n<br>From: Baroness\\n<br>Location: Castle Westbridge\\n<br>Description:\\n<br>"+desc+"\\c[0]";
    // Match actual newlines, not a literal backslash-n.
    const template=original.replace(/\\n(?=<br>)/g,"\n");
    assert.equal(w.drawTextEx(template,0,0),17);
    assert.ok(w.lastTextEx.includes("Descripción:"),w.lastTextEx);
    assert.ok(w.lastTextEx.includes("La carta está escondida en el jardín."),w.lastTextEx);
    assert.ok(w.lastTextEx.includes("De: Baronesa"),w.lastTextEx);
    assert.ok(w.lastTextEx.includes("Ubicación: Castillo Westbridge"),w.lastTextEx);
    assert.equal(JSON.stringify(plugins),before);
    // A custom-named data window reaches the lower conversion path directly.
    const generic=new c.Window_Base();
    const projected=generic.convertEscapeCharacters(template);
    assert.ok(projected.includes("La carta está escondida en el jardín."));
    assert.equal(generic.convertEscapeCharacters("Unrelated internal token"),"Unrelated internal token");
    const caption=new c.window.Window_Caption();
    assert.equal(caption.drawTextEx(body,0,0),9);
    assert.equal(caption.lastTextEx,"Sigue caminando, amigo.");
    caption.drawTextEx(colored,0,0);
    assert.equal(caption.lastTextEx,"Sigue caminando, \\c[5]amigo\\c[0].");
    assert.equal(caption.duration,90);
    const commands=[{code:101,parameters:["",0,0,2]},{code:401,parameters:[tag+body]},{code:0,parameters:[]}];
    const saved=JSON.stringify(commands),interp=new c.Game_Interpreter();
    interp._list=commands;interp._index=0;
    assert.equal(interp.command101(),true);
    assert.equal(interp.captured,tag+"Sigue caminando, amigo.");
    assert.equal(interp._list,commands);assert.equal(interp._index,1);
    assert.equal(JSON.stringify(commands),saved);
    assert.equal(scene.windows.length,0);assert.equal(f.posts.length,0);
}
async function testR4P5DynamicNativeCaptionConversion(){
    const original="Keep walking, friend.",translated="Sigue caminando, amigo.";
    const plugins=[{name:"GALV_TimedMessagePopups",status:true,parameters:{}}];
    const f=fixture(2,{plugins,responses:{[original]:translated},configure(c){
        c.Window_Base.prototype.convertEscapeCharacters=function(v){return v;};
        function Window_Caption(){this.duration=120;}
        Window_Caption.prototype=Object.create(c.Window_Base.prototype);
        Window_Caption.prototype.constructor=Window_Caption;
        c.window.Window_Caption=Window_Caption;
    }});
    await wait(35);
    const c=f.context,scene=new c.Scene_Map();c.SceneManager._scene=scene;
    const win=new c.window.Window_Caption();
    assert.equal(win.convertEscapeCharacters(original),original);
    await wait(150);
    assert.equal(win.convertEscapeCharacters(original),translated);
    assert.ok(f.posts.some(p=>p.text===original),"dynamic caption enters real request pipeline");
    assert.equal(win.duration,120);assert.equal(scene.windows.length,0);
}


async function testR4P5BFormattedMessageBodyReplay(){
    const folder=path.join("/tmp","servidor-qa-juego-日本語","IA Traductora",".local","Rpg","cache");
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const header="<WordWrap>\\n<Commander>";
    const raw=header+"We must find the \\m[Things]missing key\\c[0] before dawn.";
    const result=header+"Debemos encontrar la \\m[Things]llave perdida\\c[0] antes del amanecer.";
    const body="We must find the \x1bC[11]missing key\x1bC[0] before dawn.";
    const expected="Debemos encontrar la \x1bC[11]llave perdida\x1bC[0] antes del amanecer.";
    const state={files:{},dirs:{[folder]:true,[data]:true}};
    state.files[path.join(folder,"translations-ja-en-es-v2.jsonl")]=JSON.stringify({
        schema:"ia-traductora-cache-v2",source:"en",original:raw,translated:result,composed:true})+"\n";
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1});
    const plugins=[{name:"YEP_X_MessageMacros1",status:true,parameters:{"Macro 1 Name":"Things","Macro 1 Text":"\\c[11]"}}];
    const f=fixture(2,{fsState:state,plugins,disconnected:true,configure(c){
        c.Window_Message.prototype.convertEscapeCharacters=function(v){return v;};
    }});
    await wait(100);
    const c=f.context,scene=new c.Scene_Map();c.SceneManager._scene=scene;
    f.$gameMessage._texts=[raw];
    const w=new c.Window_Message();
    assert.equal(w.convertEscapeCharacters(body),expected);
    assert.equal(w.convertEscapeCharacters("Commander"),"Commander");
    assert.equal(w.convertEscapeCharacters("We must open the door."),"We must open the door.");
    assert.equal(f.$gameMessage.allText(),raw,"presentation conversion cannot rewrite the event");
    assert.equal(scene.windows.length,0);assert.equal(f.posts.length,0);
}


// This fixture reproduces the published Galv factory contract: a closure-
// private caption, third argument textArray, native layout before addWindow,
// and the actual _captionWindows / _time lifecycle. No third-party source
// or commercial game assets are redistributed.
function configurePrivateGalv(c){
    const nativeDraw=c.Window_Base.prototype.drawTextEx;
    function Window_GalvCaption(target,time,textArray,data,delay,skin,yoffset,actor){
        this.initialize(0,0,1280,100);
        this.target=target;this._time=time+delay;this._delayTime=time;
        this._txtArray=textArray;this.data=data;this.delay=delay;this.skin=skin;
        this.yoffset=yoffset;this.actor=actor;this.active=true;this.visible=true;
        this.imagesLoaded=true;this.contents=new c.Bitmap(1280,100);
        this.layoutCount=0;this.setWindowDimensions();
    }
    Window_GalvCaption.prototype=Object.create(c.Window_Base.prototype);
    Window_GalvCaption.prototype.constructor=Window_GalvCaption;
    Window_GalvCaption.prototype.setWindowDimensions=function(){
        this.layoutCount++;
        this.contents.clearRect(0,0,1280,100);
        this.painted=this._txtArray.map((line,i)=>{
            // A cached alias to the original native draw bypasses later
            // Window_Base.prototype wrappers, just like a custom renderer.
            nativeDraw.call(this,line,0,i*32);
            this.contents.drawText(line,0,i*32,1280,32);
            return line;
        });
        this.width=Math.max(...this.painted.map(v=>v.length*12))+24;
    };
    Window_GalvCaption.prototype.update=function(){this._time--;this.x=(this.x||0)+1;return "updated";};
    c.Scene_Map.prototype.createCaptionWindow=function(target,time,textArray,data,delay,skin,yoffset,actor){
        const w=new Window_GalvCaption(target,time,textArray,data,delay,skin,yoffset,actor);
        (this._captionWindows||(this._captionWindows=[])).push(w);w.parent=this;
        this.addWindow(w);return "native-created";
    };
}
async function testR4P6GalvRealFactoryContract(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const folder=path.join("/tmp","servidor-qa-juego-日本語","IA Traductora",".local","Rpg","cache");
    const original="Please wait, \\c[5]friend\\c[0].",translated="Espera, \\c[5]amigo\\c[0].";
    const late="Stay near the door.",lateEs="Quédate cerca de la puerta.";
    const short="Wait here, friend.",shortEs="Espera aquí, amigo.";
    const dyn="Please close the gate.",dynEs="Por favor, cierra la puerta.";
    const state={files:{},dirs:{[data]:true,[folder]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1});
    state.files[path.join(folder,"translations-ja-en-es-v2.jsonl")]=JSON.stringify({
        schema:"ia-traductora-cache-v2",source:"en",original,translated,composed:true})+"\n";
    let dynamic=dyn;
    const plugins=[{name:"GALV_TimedMessagePopups",status:true,parameters:{}}];
    const f=fixture(20,{fsState:state,plugins,responses:{[late]:lateEs,[short]:shortEs,[dyn]:dynEs},configure(c){
        configurePrivateGalv(c);
        c.$gameVariables={value(id){assert.equal(id,49);return dynamic;}};
    }});
    await wait(90);
    const c=f.context,scene=new c.Scene_Map();c.SceneManager._scene=scene;
    const target={id:7},metadata=["",0,0,2],list=[original],before=JSON.stringify(list);
    assert.equal(scene.createCaptionWindow(target,100,list,metadata,5,"WindowSpeech",-40,false),"native-created");
    const win=scene._captionWindows[0];
    assert.equal(c.window.Window_GalvCaption,undefined,"native class is not a browser global");
    assert.equal(win.painted[0],translated,"cached translation must reach first native layout");
    assert.equal(win.target,target);assert.equal(win.data,metadata);assert.equal(win._time,105);
    assert.equal(win.skin,"WindowSpeech");assert.equal(win.yoffset,-40);
    assert.equal(win.layoutCount,1);assert.equal(scene.windows.length,1);
    assert.equal(JSON.stringify(list),before);
    assert.ok(!f.posts.some(p=>p.text===original));
    const raw=[late,original];scene.createCaptionWindow(target,100,raw,metadata,0,"WindowSpeech",-40,false);
    const w=scene._captionWindows[1],bitmap=w.contents;
    assert.equal(w.painted[0],late);assert.equal(w.painted[1],translated);
    // An independently expiring native caption cannot be resurrected.
    scene.createCaptionWindow(target,2,[short],metadata,0,"WindowSpeech",-40,false);
    const expired=scene._captionWindows[2];expired.update();expired.update();expired.active=false;
    // Variable-only message is resolved as visual text; variable never written.
    scene.createCaptionWindow(target,120,["\\v[49]"],metadata,0,"WindowSpeech",-40,false);
    const variable=scene._captionWindows[3];
    await wait(180);
    for(let i=0;i<8;i++){assert.equal(w.update(),"updated");expired.update();variable.update();}
    assert.equal(w.painted[0],lateEs);assert.equal(w.painted[1],translated);
    assert.equal(w.contents,bitmap);assert.equal(w._time,92);
    assert.equal(w.layoutCount,2);assert.equal(w.x,8);
    assert.ok(!bitmap.ops.some(v=>v.text===late),"native redraw erased the original");
    assert.equal(expired.layoutCount,1);assert.equal(expired.painted[0],short);
    assert.equal(variable.painted[0],dynEs);assert.equal(dynamic,dyn);
    assert.equal(scene.windows.length,4,"no extra window from translation");
    assert.deepEqual(raw,[late,original]);
    const second=[late];scene.createCaptionWindow(target,60,second,metadata,0,"WindowSpeech",-40,false);
    assert.equal(scene._captionWindows[4].painted[0],lateEs,"repeat uses cache at first paint");
    assert.equal(f.posts.filter(p=>p.text===late).length,1);
    assert.ok(f.posts.some(p=>p.text===dyn),"resolved visual variable reaches inference");
    assert.ok(f.posts.every(p=>!p.text.includes("v[49]")));
    const old=scene._captionWindows[4];c.SceneManager._scene=new c.Scene_Map();
    old.update();assert.equal(old.layoutCount,1);
    assert.equal(f.$gameMessage.allText(),"");
}


function csvFixtureRows(rows){
    return rows.map(r=>r.map(v=>'"'+String(v||"").replace(/"/g,'""')+'"').join(",")).join("\r\n")+"\r\n";
}
async function testR4P7ExternalSheetPreparesBeforeFirstGame(){
    const content=path.join("/tmp","servidor-qa-juego-日本語","www"),data=path.join(content,"data"),csv=path.join(content,"csv");
    const state={files:{},dirs:{[data]:true,[csv]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:2,locale:"en_US"});
    state.files[path.join(data,"Map002.json")]=JSON.stringify({events:[null]});
    const message="\\c[2][\\n[7]]\\c[0]\nPlease bring the lantern.\\I[17]";
    const choice="Accept delivery",other="Decline delivery",late="The ferry leaves tomorrow.";
    const rows=[["","Script","日本語","英語","スペイン語","",""],["$map2","","","","","",""],["$event1","","","","","",""],["$page2","","","","","",""],
        ["$text1","$v[23] = 0","\\c[2][\\n[7]]\\c[0]\nランタンを持ってきて。\\I[17]",message,"","",""],
        ["$text2","","配達を引き受ける",choice,"Aceptar el encargo","",""],
        ["$text3","","配達を断る",other,"","",""],
        ["","$v[23] = 9","","Wait by the bridge.","","",""],
        ["","","","※Developer annotation","","",""],
        ["$text4","","","if(s[10]) This is a condition","","",""]];
    // Large file with all narrative rows above and a unique text after row
    // 25,000. A quoted comma/newline must stay in its cell.
    for(let i=0;i<26000;i++)rows.push(["","","","","","",""]);
    rows.push(["$map99","","","","","",""],["$event1","","","","","",""],["$page1","","","","","",""],
        ["$text1","","明日出発する。",late,"","",""]);
    state.files[path.join(csv,"sheet.csv")]=csvFixtureRows(rows);
    state.files[path.join(csv,"DB_Variable.csv")]=csvFixtureRows([["$id=0","JPN_NAME","ENG_NAME","SPN_NAME"],["$id=17","内部値","Internal event value",""]]);
    state.files[path.join(csv,"DB_Item.csv")]=csvFixtureRows([["$id=0","free","JPN_NAME","DESCRIPTION","ENG_NAME","DESCRIPTION","SPN_NAME","DESCRIPTION"],["$id=5","","鍵","古い鍵","Old key","A key, made of iron.","",""]]);
    state.files[path.join(csv,"DB_NPCJob.csv")]=csvFixtureRows([["","",""],["12","配達人","Courier"]]);
    state.files[path.join(csv,"status.csv")]=csvFixtureRows([["species","種族","Species:"],["species_value","人間","Human"]]);
    const saved=Object.assign({},state.files);
    const responses={"Courier":"Mensajero","Species:":"Especie:","Human":"Humano","Please bring the lantern.":"Por favor, trae la linterna.",[other]:"Rechazar el encargo","Wait by the bridge.":"Espera junto al puente.",[late]:"El ferry sale mañana.","Old key":"Llave antigua","A key, made of iron.":"Una llave, hecha de hierro."};
    const plugins=[{name:"KNS_CsvReader",status:true,parameters:{}}];
    const f=fixture(2,{fsState:state,batch:true,responses,plugins});
    const title=new f.context.Scene_Title();f.context.SceneManager._scene=title;title.start();title.commandNewGame();
    assert.equal(title.launches,0,"external tables hold the optional first-game preparation");
    const deadline=Date.now()+4500;
    while(Date.now()<deadline&&!title.launches){await wait(30);title.update();}
    assert.equal(title.launches,1,"preparation finishes automatically without a second click");
    assert.ok(f.posts.some(p=>p.text===late),"text after row 25000 and on an unvisited map is prepared");
    assert.ok(f.posts.some(p=>p.text===other),"short labelled English choice without stopword is prepared");
    assert.ok(!f.posts.some(p=>p.text===choice),"validated authored Spanish column reused without inference");
    assert.ok(!f.posts.some(p=>/Internal event value|Developer annotation|This is a condition|\$v\[|\\[cnI]\[/.test(p.text)),"no control or internal field reaches inference");
    const w=new f.context.Window_Message();f.$gameMessage._texts=message.split("\n");w.startMessage();
    assert.equal(f.$gameMessage.allText(),"\\c[2][\\n[7]]\\c[0]\nPor favor, trae la linterna.\\I[17]");
    f.$gameMessage.setChoices([choice,other],0,1);
    assert.deepEqual(Array.from(f.$gameMessage._choices),["Aceptar el encargo","Rechazar el encargo"]);
    const conditional="Take the ferry if(s[10])";
    f.$gameMessage.setChoices([conditional,choice],0,1);
    assert.deepEqual(Array.from(f.$gameMessage._choices),[conditional,"Aceptar el encargo"]);
    await wait(30);
    assert.ok(!f.posts.some(p=>p.text.includes("if(s[10])")),"executable choice condition is never sent to inference");
    const bitmap=new f.context.Bitmap(640,100);
    assert.equal(bitmap.measureTextWidth("Courier"),"Mensajero".length*12);
    bitmap.drawText("Courier",0,0,600,36);
    assert.equal(bitmap.lastText,"Mensajero");
    // Alternate source from the same bilingual row has the same exact
    // control contract and is reusable without a second neural inference.
    f.$gameMessage._texts=["明日出発する。"];w.startMessage();
    assert.equal(f.$gameMessage.allText(),"El ferry sale mañana.");
    for(const k of Object.keys(saved))assert.equal(state.files[k],saved[k],"original files unchanged");
    assert.equal(title.launches,1);
}
async function testR4P7JapanesePrimaryAndLiveChoice(){
    const content=path.join("/tmp","servidor-qa-juego-日本語","www"),data=path.join(content,"data"),csv=path.join(content,"csv");
    const state={files:{},dirs:{[data]:true,[csv]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1,locale:"ja_JP"});
    state.files[path.join(csv,"commonSheet.csv")]=csvFixtureRows([["","","日本語","英語",""],["$common1","","","",""],["$text1","","手紙を届ける","Deliver letter",""]]);
    const f=fixture(35,{fsState:state,responses:{"手紙を届ける":"Entregar la carta"},plugins:[{name:"MEO_Csv",status:true,parameters:{}}],configure(c){
        function Window_ChoiceList(){this.active=true;this.openness=255;this._index=0;this._list=[{name:"Deliver letter",symbol:"choice",enabled:true,ext:7}];this.draws=0;}
        Window_ChoiceList.prototype.update=function(){};
        Window_ChoiceList.prototype.itemRectForText=function(){return {width:400};};
        Window_ChoiceList.prototype.textWidthEx=function(v){return v.length*8;};
        Window_ChoiceList.prototype.redrawItem=function(i){this.draws++;this.painted=this._list[i].name;};
        c.Window_ChoiceList=Window_ChoiceList;
    }});
    const deadline=Date.now()+2500;
    while(Date.now()<deadline&&!f.posts.some(p=>p.text==="手紙を届ける"))await wait(20);
    await wait(100);
    const win=new f.context.Window_ChoiceList();
    for(let i=0;i<12;i++)win.update();
    assert.equal(win.painted,"Entregar la carta");assert.equal(win._list[0].name,"Deliver letter");
    assert.equal(win._list[0].ext,7);assert.equal(win._list[0].symbol,"choice");
    assert.equal(win._list[0].enabled,true);assert.equal(win._index,0);assert.equal(win.draws,1);
    assert.ok(f.posts.some(p=>p.text==="手紙を届ける"&&p.source==="ja"));
    assert.ok(!f.posts.some(p=>p.text==="Deliver letter"));
}


async function testR4P8CsvVariablesAndPresentation(){
    const content=path.join("/tmp","servidor-qa-juego-日本語","www"),data=path.join(content,"data"),csv=path.join(content,"csv");
    const state={files:{},dirs:{[data]:true,[csv]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:2,locale:"en_US"});
    const first="Deliver the parcel",second="Wait by the bridge",hint="※Use the lantern.",note="※Developer annotation";
    const profile="An unknown traveler.\nHe meets \\n[2].",log="“I am feeling tired.”",world="Northern forest";
    state.files[path.join(csv,"sheet.csv")]=csvFixtureRows([["","Script","日本語","英語","スペイン語","",""],["$map2","","","","","",""],["$event1","","","","","",""],["$page2","","","","","",""],
        ["$text1","","荷物を届ける",first,"","",""],["$text2","","橋で待つ",second,"","",""],
        ["$text3","","※ランタンを使う。",hint,"","",""],["","","",note,"","",""],
        ["$text4","$v[8] = 9","","Choose the road if(s[10])","","",""],
        ["$text5","","明日。/\n橋を渡る。","We leave tomorrow.","","",""]]);
    state.files[path.join(csv,"EroWindowText.csv")]=csvFixtureRows([["key","jp","en"],["profile_actor_1","旅人。","An unknown traveler.\nHe meets \\n[2]."],["Information","情報","Information"]]);
    state.files[path.join(csv,"logsheet.csv")]=csvFixtureRows([["","日本語","英語","Spanish","","",""],["npc_tired","疲れた。",log,"","","",""],["world_map/2/name","北の森",world,"","","",""]]);
    const head=["共通部","","","","","","日本語","","","","","","","English","","","","","","","Espanol","","","","","",""];
    const labels=Array(27).fill("");labels[0]="$quest_id=0";
    const quest=Array(27).fill("");quest[0]="$quest_id=9";quest[6]="手紙";quest[13]="The letter";quest[8]="商人";quest[15]="Merchant";quest[10]="$progress1= 橋へ行く。\n$progress2= 帰る。";quest[17]="$progress1= Go to the bridge.\n$progress2= Return home.";
    state.files[path.join(csv,"QuestList.csv")]=csvFixtureRows([head,labels,quest]);
    const originalFiles=Object.assign({},state.files);
    const responses={[first]:"Entrega el paquete",[second]:"Espera junto al puente","Use the lantern.":"Usa la linterna.","Choose the road":"Elige el camino","We leave tomorrow.":"Salimos mañana.","明日。":"Mañana.","橋を渡る。":"Cruza el puente.","An unknown traveler.":"Un viajero desconocido.","He meets":"Conoce a",[log]:"«Me siento cansado.»",[world]:"Bosque del norte","The letter":"La carta","Merchant":"Comerciante","Go to the bridge.":"Ve al puente.","Return home.":"Regresa a casa."};
    const values={61:first,62:second};
    const f=fixture(2,{fsState:state,batch:true,responses,plugins:[{name:"KNS_CsvReader",status:true,parameters:{}}],configure(c){
        c.$gameVariables={value(id){return values[id];},setValue(){throw Error("no game writes");}};
        c.$gameActors={actor(id){assert.equal(id,2);return {name(){return "Alice";}};}};
        c.Window_Base.prototype.convertEscapeCharacters=function(text){return text.replace(/\\v\[(\d+)\]/gi,(_,id)=>values[id]);};
        function Window_ChoiceList(){this.active=true;this.openness=255;this._index=1;this._list=[{name:"\\v[61]",symbol:"choice",enabled:true,ext:61},{name:"\\v[62]",symbol:"choice",enabled:false,ext:62}];this.painted=[];}
        Window_ChoiceList.prototype=Object.create(c.Window_Base.prototype);
        Window_ChoiceList.prototype.constructor=Window_ChoiceList;
        // Custom renderer performs its own final conversion.
        Window_ChoiceList.prototype.convertEscapeCharacters=function(text){return text.replace(/\\v\[(\d+)\]/gi,(_,id)=>values[id]);};
        Window_ChoiceList.prototype.textWidthEx=function(v){return this.convertEscapeCharacters(v).length*8;};
        Window_ChoiceList.prototype.drawItem=function(i){this.painted[i]=this.convertEscapeCharacters(this._list[i].name);};
        Window_ChoiceList.prototype.redrawItem=function(i){this.drawItem(i);};
        Window_ChoiceList.prototype.itemRectForText=function(){return {width:500};};
        Window_ChoiceList.prototype.update=function(){};
        c.Window_ChoiceList=Window_ChoiceList;
    }});
    const title=new f.context.Scene_Title();f.context.SceneManager._scene=title;title.start();title.commandNewGame();
    const deadline=Date.now()+5000;
    while(Date.now()<deadline&&!title.launches){await wait(25);title.update();}
    assert.equal(title.launches,1,"external profile, quest and choices prepare before play");
    const w=new f.context.Window_ChoiceList(),before=JSON.stringify(w._list);
    w.drawItem(0);w.drawItem(1);
    assert.deepEqual(w.painted,["Entrega el paquete","Espera junto al puente"]);
    assert.equal(w.textWidthEx("\\v[61]"),"Entrega el paquete".length*8);
    for(let i=0;i<24;i++)w.update();
    assert.equal(JSON.stringify(w._list),before);assert.equal(w._index,1);
    assert.equal(values[61],first);assert.equal(values[62],second);
    f.$gameMessage.setChoices(["\\v[61]","\\v[62]"],1,0);
    assert.deepEqual(Array.from(f.$gameMessage._choices),["\\v[61]","\\v[62]"]);
    const b=new f.context.Window_Base();b.initialize(0,0,600,300);
    assert.equal(b.convertEscapeCharacters("An unknown traveler."),"Un viajero desconocido.");
    const bitmap=new f.context.Bitmap(640,200);bitmap.drawText("Information",0,0,640,30);
    assert.equal(bitmap.lastText,"Información");
    bitmap.drawText("NAME : Alice",0,0,640,30);assert.equal(bitmap.lastText,"NOMBRE : Alice");
    assert.equal(b.convertEscapeCharacters("Northern forest"),"Bosque del norte");
    assert.equal(b.convertEscapeCharacters("Merchant"),"Comerciante");
    assert.equal(b.convertEscapeCharacters("Go to the bridge."),"Ve al puente.");
    assert.ok(f.posts.some(p=>p.text==="Use the lantern."),"explicit display note prepared");
    assert.ok(f.posts.some(p=>p.text==="橋を渡る。"),"unequal bilingual block counts retain alternate");
    assert.ok(f.posts.some(p=>p.text==="Choose the road"),"conditional display label extracted");
    assert.ok(!f.posts.some(p=>/Developer annotation|if\(s\[|\$progress|\$v\[|\\v\[/.test(p.text)),"no executable field inferred");
    for(const k of Object.keys(originalFiles))assert.equal(state.files[k],originalFiles[k]);
}


function r4p9Progress(f){
    const m=new f.context.Scene_Map();m.createAllWindows();m._iaPanel.refresh();
    const line=m._iaPanel.drawn.filter(x=>/^Textos listos: /.test(x.text)).pop();
    const match=/Textos listos: (\d+)\/(\d+)\s+Fallos: (\d+)/.exec(line.text);
    return {ready:Number(match[1]),total:Number(match[2]),failed:Number(match[3])};
}
async function testR4P9ContinueInventoryAndRestore(){
    const content=path.join("/tmp","servidor-qa-juego-日本語","www"),data=path.join(content,"data"),csv=path.join(content,"csv");
    const folder=path.join("/tmp","servidor-qa-juego-日本語","IA Traductora",".local","Rpg","cache");
    const cache=path.join(folder,"translations-ja-en-es-v2.jsonl");
    const state={files:{},dirs:{[data]:true,[csv]:true,[folder]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1,locale:"en_US"});
    const rows=[["","Script","日本語","英語","スペイン語","",""],["$map1","","","","","",""],["$event1","","","","","",""],["$page1","","","","","",""]];
    const responses={},texts=[];
    for(let i=0;i<16;i++){
        const text="Please open the door "+i+".";
        texts.push(text);responses[text]="Por favor, abre la puerta "+i+".";
        rows.push(["$text"+(i+1),"","",text,"","",""]);
    }
    state.files[path.join(csv,"sheet.csv")]=csvFixtureRows(rows);
    // A valid last record without its terminal newline is recoverable.
    state.files[cache]=JSON.stringify({schema:"ia-traductora-cache-v2",source:"en",original:texts[0],translated:responses[texts[0]],composed:false});
    const originalCsv=state.files[path.join(csv,"sheet.csv")];
    const f=fixture(80,{fsState:state,batch:true,responses,cacheReadDelay:100,appendFailures:1,plugins:[{name:"KNS_CsvReader",status:true,parameters:{}}]});
    const title=new f.context.Scene_Title();f.context.SceneManager._scene=title;title.start();title.commandNewGame();title.commandNewGame();
    assert.equal(title.launches,1,"skip gate never blocks gameplay");
    const map=new f.context.Scene_Map();f.context.SceneManager._scene=map;map.createAllWindows();
    await wait(190);
    const early=r4p9Progress(f);
    assert.ok(early.total>=16&&early.ready>=1&&early.ready<early.total,"restored cache is counted before inference completes");
    // An unvisited end-of-table message should not wait for the whole queue.
    f.$gameMessage._texts=[texts[15]];new f.context.Window_Message().startMessage();
    const end=Date.now()+6000;
    while(Date.now()<end&&r4p9Progress(f).ready<early.total)await wait(40);
    const done=r4p9Progress(f);
    assert.equal(done.ready,done.total,"background queue drains while in gameplay without title updates");
    assert.equal(done.failed,0);
    assert.ok(f.posts.some(p=>p.text===texts[15]));
    assert.ok(!f.posts.some(p=>p.text===texts[0]),"cached item never needs neural inference");
    const secondTitle=new f.context.Scene_Title();f.context.SceneManager._scene=secondTitle;secondTitle.start();
    assert.ok(r4p9Progress(f).ready>=done.ready,"returning to title cannot reset completed progress");
    secondTitle.commandNewGame();assert.equal(secondTitle.launches,1);
    await wait(1300);
    const journal=state.files[cache].split("\n").filter(Boolean).map(JSON.parse);
    assert.ok(texts.every(v=>journal.some(r=>r.original===v)),"temporary disk failure must not lose translations");
    const reboot=fixture(1,{fsState:state,disconnected:true,cacheReadDelay:100,plugins:[{name:"KNS_CsvReader",status:true,parameters:{}}]});
    const restoredTitle=new reboot.context.Scene_Title();reboot.context.SceneManager._scene=restoredTitle;restoredTitle.start();
    const deadline=Date.now()+2500;
    while(Date.now()<deadline&&r4p9Progress(reboot).ready<done.ready)await wait(30);
    assert.equal(r4p9Progress(reboot).ready,done.ready,"offline restart restores full completed count");
    reboot.$gameMessage._texts=[texts[15]];new reboot.context.Window_Message().startMessage();
    assert.equal(reboot.$gameMessage.allText(),responses[texts[15]]);
    assert.equal(reboot.posts.length,0);
    assert.equal(state.files[path.join(csv,"sheet.csv")],originalCsv);
}
async function testR4P9LateCsvNamedMessage(){
    const content=path.join("/tmp","servidor-qa-juego-日本語","www"),data=path.join(content,"data"),csv=path.join(content,"csv");
    const state={files:{},dirs:{[data]:true,[csv]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1,locale:"en_US"});
    const head="\\c[6][\\n[2]]\\c[0]\n",body="Please wait by the gate.",text=head+body;
    const f=fixture(120,{fsState:state,nativePaint:true,responses:{[body]:"Espera junto a la puerta."},plugins:[{name:"KNS_CsvReader",status:true,parameters:{}}],configure(c){
        c.$gameActors={actor(id){assert.equal(id,2);return {name(){return "Alice";}};}};
        const original=c.Window_Message.prototype.startMessage;
        c.Window_Message.prototype.startMessage=function(){original.apply(this,arguments);this._textState.text=this._textState.text.replace(/\\n\[2\]/gi,"Alice");};
    }});
    await wait(35);
    const map=new f.context.Scene_Map();f.context.SceneManager._scene=map;
    f.$gameMessage._texts=text.split("\n");const msg=new f.context.Window_Message();msg.startMessage();msg.finishPage();
    const deadline=Date.now()+3000;
    while(Date.now()<deadline&&!msg.contents.ops.some(x=>x.text==="Espera")){await wait(30);msg.update();}
    assert.ok(msg.contents.ops.some(x=>x.text==="Espera"),"late Spanish paints on the current native message");
    assert.equal(msg.originalStarts,1);assert.equal(msg.pages,1);
    assert.equal(f.$gameMessage.allText(),text,"active game message and actor name remain untouched");
    assert.ok(msg.contents.ops.some(x=>x.text==="[Alice]"));
    assert.ok(msg.contents.ops.some(x=>x.text==="FACE"));
    assert.equal(map.windows.length,0,"no extra dialogue window");
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

async function testMZNativeContractsAndControls(){
    const root=path.join("/tmp","servidor-qa-juego-日本語"),data=path.join(root,"data");
    const state={files:{},dirs:{[data]:true}};
    const en="Open the wooden gate.",ja="橋を渡ってください。",choice="Take the letter";
    const body="\\FS[24]\\PX[12]\\PY[8]"+en+"\\I[17]";
    const map={events:[null,{pages:[{list:[
        {code:101,parameters:["",0,0,2,"Haruka"]},{code:401,parameters:[body]},
        {code:102,parameters:[[choice],0,0,2,0]},
        {code:357,parameters:["Custom","command","label",{text:"This script must never be translated."}]},
        {code:355,parameters:["This script must never be translated."]},
        {code:105,parameters:[2,false]},{code:405,parameters:[ja]}
    ]}]}]};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1,locale:"en_US"});
    state.files[path.join(data,"Map001.json")]=JSON.stringify(map);
    const f=fixture(3,{mz:true,fsState:state,batch:true,responses:{[en]:"Abre la puerta de madera.",[ja]:"Cruza el puente.",[choice]:"Toma la carta"},configure(c){
        c.Game_Message.prototype.setSpeakerName=function(v){this._speakerName=v;};
        function Window_NameBox(rect){this.initialize(rect);}
        Window_NameBox.prototype=Object.create(c.Window_Base.prototype);
        Window_NameBox.prototype.constructor=Window_NameBox;
        Window_NameBox.prototype.setName=function(v){this._name=v;this.refresh();};
        Window_NameBox.prototype.refresh=function(){this.drawText(this._name,0,0,200);};
        c.Window_NameBox=Window_NameBox;
        function Window_ChoiceList(){
            this._list=[{name:choice,symbol:"choice",enabled:true,ext:0}];this.active=true;this.openness=255;this.painted=[];
        }
        Window_ChoiceList.prototype=Object.create(c.Window_Base.prototype);
        Window_ChoiceList.prototype.constructor=Window_ChoiceList;
        Window_ChoiceList.prototype.drawItem=function(i){this.painted[i]=this._list[i].name;};
        Window_ChoiceList.prototype.textSizeEx=function(v){return {width:v.length*8,height:32};};
        Window_ChoiceList.prototype.itemLineRect=function(){return {width:600};};
        Window_ChoiceList.prototype.redrawItem=function(i){this.drawItem(i);};
        Window_ChoiceList.prototype.update=function(){};
        c.Window_ChoiceList=Window_ChoiceList;
    }});
    const scene=new f.context.Scene_Map();f.context.SceneManager._scene=scene;scene.createAllWindows();scene.update();
    assert.equal(scene.windows.length,2,"MZ HUD uses Rectangle");
    scene._iaPanel.refresh();
    assert.ok(scene._iaPanel.drawn.some(v=>v.text==="IA Traductora · RPG Maker MZ"));
    const until=Date.now()+5000;
    while(Date.now()<until&&(!f.posts.some(v=>v.text===en)||!f.posts.some(v=>v.text===ja)||!f.posts.some(v=>v.text===choice)))await wait(35);
    await wait(160);
    f.$gameMessage.setSpeakerName("Haruka");
    const name=new f.context.Window_NameBox(new f.context.Rectangle(0,0,250,52));name.setName("Haruka");
    assert.equal(name.lastText,"Haruka");
    assert.equal(f.$gameMessage._speakerName,"Haruka");
    f.$gameMessage._texts=[body];new f.context.Window_Message().startMessage();
    assert.equal(f.$gameMessage.allText(),"\\FS[24]\\PX[12]\\PY[8]Abre la puerta de madera.\\I[17]");
    f.$gameMessage._texts=[ja];new f.context.Window_Message().startMessage();assert.equal(f.$gameMessage.allText(),"Cruza el puente.");
    f.$gameMessage.setChoices([choice],0,1);
    assert.equal(f.$gameMessage._choices[0],choice,"MZ choice data unchanged");
    const win=new f.context.Window_ChoiceList(),before=JSON.stringify(win._list);
    win.drawItem(0);assert.equal(win.painted[0],"Toma la carta");
    assert.equal(win.textSizeEx(choice).width,"Toma la carta".length*8);
    assert.equal(JSON.stringify(win._list),before);
    assert.ok(!f.posts.some(v=>/script|Haruka|\\(?:FS|PX|PY|I)\[/i.test(v.text)));
    assert.equal(state.files[path.join(data,"Map001.json")],JSON.stringify(map));
    console.log("SERVIDOR_V2_MZ_NATIVE_RECTANGLE_NAME_CHOICES_CONTROLS_PASS");
}


async function testExternalTsvLookupAndLatePresentation(mz){
    const content=path.join("/tmp","servidor-qa-juego-日本語",mz?"":"www"),data=path.join(content,"data");
    const state={files:{},dirs:{[data]:true}};
    const line="Please wait here...\\. Can we leave?",spanish="Espera aquí...\\. ¿Podemos salir?";
    const key="\\tl{A0001}",choiceKey="\\tl{A0002}",chineseKey="\\tl{请开门}";
    const rows=[
        ["Key","English","Chinese(Simplified)","Chinese(Traditional)","Japanese"],
        ["A0001",line,"等一下...\\. 可以离开吗？","等一下...\\. 可以離開嗎？","待って...\\. 出られますか？"],
        ["A0002","Open the gate","开门","開門","門を開ける"],
        ["请开门","Take the lantern","请开门","請開門","ランタンを取る"],
        ["A0003","Please read this note.","请阅读","請閱讀","このメモを読んでください。"],
        ["A0004","Please check the door.","查门","查門","ドアを確認してください。"],
        ["A0004","Please check the window.","查窗","查窗","窓を確認してください。"]
    ];
    const raw="\uFEFF"+rows.map(r=>r.join("\t")).join("\r\n")+"\r\n";
    state.files[path.join(data,"Languages.tsv")]=raw;
    state.files[path.join(data,"System.json")]=JSON.stringify({locale:"zh_CN",startMapId:1});
    const originalMap=JSON.stringify({events:[null,{pages:[{list:[
        {code:401,parameters:[key]},{code:102,parameters:[[choiceKey,chineseKey],0,0,2,0]},
        {code:355,parameters:["Do not translate executable instructions."]}
    ]}]}]});
    state.files[path.join(data,"Map001.json")]=originalMap;
    const f=fixture(110,{mz,fsState:state,nativePaint:true,batch:true,
        responses:{"Please wait here...":"Espera aquí...","Can we leave?":"¿Podemos salir?","Open the gate":"Abre la puerta","Take the lantern":"Toma la linterna","Please read this note.":"Lee esta nota, por favor."},
        configure(c){
            const native=function(text){
                return text.replace(/(?:\\|\x1b)tl\{([^{}]+)\}/gi,(token,k)=>{
                    const row=rows.find(r=>r[0]===k);return row?row[1]:token;
                }).replace(/\\/g,"\x1b");
            };
            c.Window_Base.prototype.convertEscapeCharacters=native;
            c.Window_Message.prototype.convertEscapeCharacters=native;
            const start=c.Window_Message.prototype.startMessage;
            c.Window_Message.prototype.startMessage=function(){
                start.apply(this,arguments);this._textState.text=this.convertEscapeCharacters(c.$gameMessage.allText());
            };
            function Window_ChoiceList(){this._list=[{name:choiceKey,symbol:"choice",enabled:true,ext:0}];this.active=true;this.openness=255;this.painted=[];}
            Window_ChoiceList.prototype=Object.create(c.Window_Base.prototype);
            Window_ChoiceList.prototype.constructor=Window_ChoiceList;
            Window_ChoiceList.prototype.drawItem=function(i){this.painted[i]=this.convertEscapeCharacters(this._list[i].name);};
            Window_ChoiceList.prototype.redrawItem=function(i){this.drawItem(i);};
            Window_ChoiceList.prototype.textWidthEx=function(v){return v.length*8;};
            Window_ChoiceList.prototype.textSizeEx=function(v){return {width:v.length*8,height:32};};
            Window_ChoiceList.prototype.itemRectForText=function(){return {width:600};};
            Window_ChoiceList.prototype.itemLineRect=function(){return {width:600};};
            Window_ChoiceList.prototype.update=function(){};
            c.Window_ChoiceList=Window_ChoiceList;
        }
    });
    const map=new f.context.Scene_Map();f.context.SceneManager._scene=map;map.createAllWindows();map.update();
    await wait(35);
    f.$gameMessage._texts=[key];
    const msg=new f.context.Window_Message();msg.startMessage();msg.finishPage();
    const limit=Date.now()+6000;
    while(Date.now()<limit&&!msg.contents.ops.some(x=>x.text.includes("Espera"))){await wait(40);msg.update();}
    assert.ok(msg.contents.ops.some(x=>x.text.includes("Espera")),"TSV message must translate in the original window, even if the first paint was English");
    assert.equal(msg.originalStarts,1);assert.equal(msg.pages,1);
    assert.equal(f.$gameMessage.allText(),key,"the localization reference remains unchanged");
    assert.ok(msg.contents.ops.some(x=>x.text==="FACE"),"native face preserved");
    f.$gameMessage._texts=[key];
    const again=new f.context.Window_Message();again.startMessage();
    assert.equal(again._textState.text,spanish.replace(/\\/g,"\x1b"),"cache preserves native pause on replay");
    assert.equal(f.$gameMessage.allText(),key);
    const choice=new f.context.Window_ChoiceList(),before=JSON.stringify(choice._list);
    while(Date.now()<limit&&choice.painted[0]!=="Abre la puerta"){choice.drawItem(0);await wait(35);}
    assert.equal(choice.painted[0],"Abre la puerta");
    assert.equal(JSON.stringify(choice._list),before,"branch symbol, index and key are unchanged");
    const other=new f.context.Window_Base();other.initialize.apply(other,mz?[new f.context.Rectangle(0,0,400,100)]:[0,0,400,100]);
    assert.notEqual(other.convertEscapeCharacters("\\tl{A0004}"),"\\tl{A0004}","native loader retains ownership of conflicting keys");
    assert.ok(!f.posts.some(v=>/\\tl\{|A000[1-4]|请开门|開門|executable instructions/.test(v.text)),"never send keys, Chinese columns or script to inference");
    assert.equal(state.files[path.join(data,"Languages.tsv")],raw);
    assert.equal(state.files[path.join(data,"Map001.json")],originalMap);
    assert.equal(map.windows.length,2,"no additional dialogue overlay");
    console.log("SERVIDOR_EXTERNAL_TSV_NATIVE_"+(mz?"MZ":"MV")+"_PASS");
}


async function testR3TsvStartWithoutWaitingAndWrappedComposite(mz){
    const root=path.join("/tmp","servidor-qa-juego-日本語"),content=mz?root:path.join(root,"www"),data=path.join(content,"data");
    const state={files:{},dirs:{[data]:true}};
    const key="\\tl{T1001}\n\\tl{T1002}",line1="Please open the wooden gate.",line2="We can leave now.";
    const rows=[["Key","English","Chinese(Simplified)","Chinese(Traditional)","Japanese"],
        ["T1001",line1,"开门","開門","門を開けてください。"],
        ["T1002",line2,"离开","離開","出発できる。"],
        ["T1003","Please check the lantern.","灯","燈","ランタンを確認して。"],
        ["T1004","Please check the window.","窗","窗","窓を確認して。"]];
    // An isolated malformed row must not suppress all valid translations.
    const raw=rows.map(r=>r.join("\t")).join("\n")+"\nmalformed\trow\n";
    state.files[path.join(data,"Languages.tsv")]=raw;
    state.files[path.join(data,"System.json")]=JSON.stringify({locale:"en_US",startMapId:1});
    const mapData={events:[null,{pages:[{list:[{code:401,parameters:["\\tl{T1001}"]},{code:401,parameters:["\\tl{T1002}"]}]}]}]};
    state.files[path.join(data,"Map001.json")]=JSON.stringify(mapData);
    const f=fixture(100,{mz,fsState:state,cacheReadDelay:160,nativePaint:true,batch:true,
        responses:{[line1]:"Abre la puerta de madera.",[line2]:"Ya podemos salir.","Please check the lantern.":"Revisa la linterna.","Please check the window.":"Revisa la ventana."},
        configure(c){
            c.$dataMap=mapData;
            const start=c.Window_Message.prototype.startMessage;
            // Deliberately bypass convertEscapeCharacters wrappers and
            // insert a wrap after the author's native localization.
            c.Window_Message.prototype.startMessage=function(){
                start.apply(this,arguments);
                this._textState.text=c.$gameMessage.allText().replace(/\\tl\{([^}]+)\}/g,(token,id)=>{
                    const row=rows.find(r=>r[0]===id);return row?row[1]:token;
                }).replace("wooden gate","wooden\n gate");
            };
        }});
    const c=f.context,title=new c.Scene_Title();c.SceneManager._scene=title;title.start();title.commandNewGame();
    assert.equal(title.launches,1,"TSV starts on first click, while cache/index are loading");
    const map=new c.Scene_Map();c.SceneManager._scene=map;map.createAllWindows();map.update();
    if(mz)assert.equal(map._iaMini.height,38,"one line plus two six-pixel paddings");
    f.$gameMessage._texts=key.split("\n");
    const msg=new c.Window_Message();msg.startMessage();msg.finishPage();
    const deadline=Date.now()+6500;
    while(Date.now()<deadline&&!msg.contents.ops.some(x=>x.text==="Abre")){await wait(40);msg.update();}
    assert.ok(msg.contents.ops.some(x=>x.text==="Abre"),"wrapped multi-key message recovers without revisiting");
    assert.ok(msg.contents.ops.some(x=>x.text==="salir."),"second localized key is included");
    assert.equal(f.$gameMessage.allText(),key);assert.equal(msg.originalStarts,1);assert.equal(msg.pages,1);
    assert.ok(msg.contents.ops.some(x=>x.text==="FACE"));assert.equal(map.windows.length,2);
    while(Date.now()<deadline&&!f.posts.some(x=>x.text==="Please check the window."))await wait(30);
    assert.ok(f.posts.some(x=>x.text==="Please check the window."),"unvisited text continues processing while playing");
    const replay=new c.Window_Message();replay.startMessage();
    assert.equal(replay._textState.text,"Abre la puerta de madera.\nYa podemos salir.","cached composite used before first glyph");
    assert.equal(f.$gameMessage.allText(),key);
    const again=new c.Scene_Title();c.SceneManager._scene=again;again.start();again.commandNewGame();assert.equal(again.launches,1);
    assert.equal(state.files[path.join(data,"Languages.tsv")],raw);
    assert.ok(!f.posts.some(x=>/\\tl\{|T100[1-4]|malformed/.test(x.text)));
}


async function testR4NativeTsvMixedControlsAndCoverage(mz){
    const root=path.join("/tmp","servidor-qa-juego-日本語"),content=mz?root:path.join(root,"www"),data=path.join(content,"data");
    const state={files:{},dirs:{[data]:true}};
    const key="\\tl{R4002}\n\\tl{R4003}",one="The door is locked. You need the key.",two="\\. Please take the lantern.";
    const rows=[["Key","English","Chinese(Simplified)","Chinese(Traditional)","Japanese"],
        ["R4001","Guide","指南","導覽","ガイド"],
        ["R4002",one,"门锁了。\\. 需要钥匙。","門鎖了。\\. 需要鑰匙。","扉は閉まっている。\\. 鍵が必要だ。"],
        ["R4003",two,"\\. 拿灯。","\\. 拿燈。","ランタンを取ってください。"],
        ["R4004","Please check the window.","查窗","查看窗戶","窓を調べてください。"]];
    const raw=rows.map(r=>r.join("\t")).join("\n")+"\n";
    state.files[path.join(data,"Languages.tsv")]=raw;
    state.files[path.join(data,"System.json")]=JSON.stringify({locale:"zh_CN",startMapId:1});
    const folder=path.join(root,"IA Traductora",".local","Rpg","cache");
    const journal=path.join(folder,"translations-ja-en-es-v2.jsonl");
    state.dirs[folder]=true;
    // Older neural output dropped a complete sentence; it must not win.
    state.files[journal]=JSON.stringify({schema:"ia-traductora-cache-v2",source:"en",original:one,translated:"La puerta está cerrada.",composed:false})+"\n";
    const mapData={events:[null,{pages:[{list:[{code:401,parameters:["\\tl{R4002}"]},{code:401,parameters:["\\tl{R4003}"]}]}]}]};
    const mapJson=JSON.stringify(mapData);state.files[path.join(data,"Map001.json")]=mapJson;
    let locale=1;
    const f=fixture(80,{mz,fsState:state,cacheReadDelay:100,batch:true,nativePaint:true,
        plugins:[{name:"VisuMZ_1_MessageCore",status:true,parameters:{"Localization:struct":JSON.stringify({"Enable:eval":"true","LangFiletype:str":"tsv","TsvFilename:str":"Languages.tsv"})}}],
        responses:{"The door is locked.":"La puerta está cerrada.","You need the key.":"Necesitas la llave.","Please take the lantern.":"Toma la linterna.","Please check the window.":"Revisa la ventana.","扉は閉まっている。":"La puerta está cerrada.","鍵が必要だ。":"Necesitas la llave.","ランタンを取ってください。":"Toma la linterna."},
        configure(c){
            c.$dataMap=mapData;
            function resolve(text){return text.replace(/(?:\\|\x1b)tl\{([^}]+)\}/gi,(token,k)=>{const row=rows.find(r=>r[0]===k);return row?row[locale]:token;});}
            c.Window_Base.prototype.convertEscapeCharacters=resolve;
            c.Window_Message.prototype.convertEscapeCharacters=resolve;
            const base=c.Window_Message.prototype.startMessage;
            c.Window_Message.prototype.startMessage=function(){
                // A custom loader obtains the message directly, *before*
                // it creates or measures the native text state. Its own
                // wrapping path bypasses Window_Base.drawTextEx entirely.
                this.nativeInput=c.$gameMessage.allText();base.apply(this,arguments);
                this._textState.text=resolve(this.nativeInput).replace(/\\/g,"\x1b");
            };
        }});
    const c=f.context,title=new c.Scene_Title();c.SceneManager._scene=title;title.start();title.commandNewGame();
    assert.equal(title.launches,1,"TSV game enters before full translation");
    const map=new c.Scene_Map();c.SceneManager._scene=map;map.createAllWindows();map.update();
    f.$gameMessage._texts=key.split("\n");const first=new c.Window_Message();first.startMessage();first.finishPage();
    const deadline=Date.now()+6500;
    while(Date.now()<deadline&&!first.contents.ops.some(x=>x.text==="Necesitas")){await wait(35);first.update();}
    assert.ok(first.contents.ops.some(x=>x.text==="Necesitas"),"late result restores omitted sentence in original window");
    assert.equal(first.originalStarts,1);assert.equal(first.pages,1);
    assert.equal(f.$gameMessage.allText(),key);
    assert.ok(first.contents.ops.some(x=>x.text==="FACE"));
    const replay=new c.Window_Message();replay.startMessage();
    assert.equal(replay.nativeInput,"La puerta está cerrada. Necesitas la llave.\n\\. Toma la linterna.","native layout receives complete Spanish before drawing, using actual English controls");
    assert.equal(f.$gameMessage.allText(),key);
    while(Date.now()<deadline&&!f.posts.some(v=>v.text==="Please check the window."))await wait(30);
    assert.ok(f.posts.some(v=>v.text==="Please check the window."),"unvisited content still processed in game");
    assert.ok(f.posts.some(v=>v.text==="You need the key."));assert.ok(!f.posts.some(v=>v.text===one),"do not fetch the known incomplete whole sentence again");
    // Switch to Japanese. Do not carry English's extra pause into the
    // Japanese lantern message merely because it is in the same key.
    locale=4;f.$gameMessage._texts=["\\tl{R4003}"];
    let other=null;
    while(Date.now()<deadline){
        other=new c.Window_Message();other.startMessage();
        if(other.nativeInput==="Toma la linterna.")break;
        await wait(40);
    }
    assert.equal(other.nativeInput,"Toma la linterna.","native selected language is revalidated");
    assert.equal(f.$gameMessage.allText(),"\\tl{R4003}");
    const title2=new c.Scene_Title();c.SceneManager._scene=title2;title2.start();title2.commandNewGame();assert.equal(title2.launches,1);
    assert.equal(state.files[path.join(data,"Languages.tsv")],raw);assert.equal(state.files[path.join(data,"Map001.json")],mapJson);
    assert.ok(!f.posts.some(v=>/\\tl\{|R400[1-4]/.test(v.text)));
}


async function testR5DynamicNamesAndAuthoredRepetition(mz,firstView=false){
    const root=path.join("/tmp","servidor-qa-juego-日本語"),content=mz?root:path.join(root,"www"),data=path.join(content,"data");
    const state={files:{},dirs:{[data]:true}};
    const one="\\c[1](Please wait here. \\v[21], I'm sorry...)";
    const two="\\c[1](Judging by \\v[23]'s expression, something happened...)";
    const three="Hahahaha! \\.What a lovely day! \\.What a lovely day!";
    const rows=[["Key","English","Chinese(Simplified)","Chinese(Traditional)","Japanese"],
        ["R5001","Guide","指南","導覽","ガイド"],
        ["R5002",one,"等一下。","等一下。","待ってください。"],
        ["R5003",two,"看表情。","看表情。","表情を見ると。"],
        ["R5004",three,"好天气！","好天氣！","いい天気！"],
        ["R5005","Please check the window.","查窗","查看窗戶","窓を調べてください。"]];
    const raw=rows.map(r=>r.join("\t")).join("\n")+"\n";
    state.files[path.join(data,"Languages.tsv")]=raw;
    state.files[path.join(data,"System.json")]=JSON.stringify({locale:"en_US",startMapId:1});
    const folder=path.join(root,"IA Traductora",".local","Rpg","cache");
    const journal=path.join(folder,"translations-ja-en-es-v2.jsonl");state.dirs[folder]=true;
    const translations={"Please wait here.":"Espera aquí.",", I'm sorry...":"Lo siento...","Judging by":"A juzgar por",
        "the expression":"La expresión","something happened...":"Algo pasó...",
        "Hahahaha!":"¡Jajaja!","What a lovely day!":"¡Qué día maravilloso!","Please check the window.":"Revisa la ventana."};
    state.files[journal]=Object.entries(translations).map(([original,translated])=>JSON.stringify({schema:"ia-traductora-cache-v2",source:"en",original,translated,composed:false})).join("\n")+"\n";
    const values={21:"Alex",23:"小林"};let writes=0;
    const f=fixture(15,{mz,fsState:state,cacheReadDelay:70,batch:true,nativePaint:true,nativeWidth:1000,
        plugins:[{name:"VisuMZ_1_MessageCore",status:true,parameters:{"Localization:struct":JSON.stringify({"Enable:eval":"true","LangFiletype:str":"tsv","TsvFilename:str":"Languages.tsv"})}}],
        responses:translations,configure(c){
            c.$gameVariables={value(i){return values[i]},setValue(){writes++;throw Error("unexpected write")}};
            const expand=t=>t.replace(/(?:\\|\x1b)tl\{([^}]+)\}/gi,(token,k)=>{const r=rows.find(r=>r[0]===k);return r?r[1]:token})
                .replace(/(?:\\|\x1b)v\[(\d+)\]/gi,(_,i)=>values[i]).replace(/\\c\[/gi,"\x1bC[").replace(/\\\./g,"\x1b.");
            c.Window_Base.prototype.convertEscapeCharacters=expand;c.Window_Message.prototype.convertEscapeCharacters=expand;
            if(firstView){
                const p=c.Window_Message.prototype;
                p.updateWait=function(){return false;};
                p.canStart=function(){return c.$gameMessage.hasText()&&!this._textState;};
                p.update=function(){this.updates++;if(!this.updateWait()&&this.canStart())this.startMessage();};
            }
            const base=c.Window_Message.prototype.startMessage;
            c.Window_Message.prototype.startMessage=function(){
                this.nativeInput=c.$gameMessage.allText();base.apply(this,arguments);
                this._textState.text=expand(this.nativeInput);
            };
        }});
    const c=f.context,title=new c.Scene_Title();c.SceneManager._scene=title;title.start();title.commandNewGame();
    assert.equal(title.launches,1);
    const map=new c.Scene_Map();c.SceneManager._scene=map;map.createAllWindows();map.update();
    const key=id=>"\\tl{R500"+id+"}";
    f.$gameMessage._texts=[key(2)];const first=new c.Window_Message();
    if(firstView){
        first.update();assert.equal(first.originalStarts,0,"cold TSV lookup waits for table and cache");
        const deadline=Date.now()+6000;
        while(!first.originalStarts&&Date.now()<deadline){await wait(45);first.update();}
        assert.equal(first.originalStarts,1);
        assert.equal(first.nativeInput,"\\c[1](Espera aquí. \\v[21], Lo siento...)");
        assert.ok(first._textState.text.includes("Alex"));
        assert.equal(f.$gameMessage.allText(),key(2),"raw lookup references remain unchanged");
        assert.equal(writes,0);
        assert.ok(!f.posts.some(v=>/\\tl\{|\\v\[|Alex|小林/.test(v.text)));
        return;
    }
    first.startMessage();first.finishPage();
    const limit=Date.now()+6000;
    while(Date.now()<limit&&!first.contents.ops.some(x=>x.text.includes("Espera"))){await wait(35);first.update();}
    assert.ok(first.contents.ops.some(x=>x.text.includes("Espera")),"late colored template must match expanded variable");
    assert.ok(first.contents.ops.some(x=>x.text.includes("Alex")),"runtime name stays visible");
    assert.equal(first.originalStarts,1);assert.equal(f.$gameMessage.allText(),key(2));
    async function replay(id,expected){
        f.$gameMessage._texts=[key(id)];
        let w;
        while(Date.now()<limit){
            w=new c.Window_Message();w.startMessage();
            if(w.nativeInput===expected)return w;
            await wait(35);
        }
        assert.equal(w.nativeInput,expected,"template not reconstructed "+id);
    }
    const oneExpected="\\c[1](Espera aquí. \\v[21], Lo siento...)";
    await replay(2,oneExpected);
    values[21]="Taylor";const changed=await replay(2,oneExpected);
    assert.ok(changed._textState.text.includes("Taylor"));assert.ok(!changed._textState.text.includes("Alex"));
    const p=await replay(3,"\\c[1](A juzgar por la expresión de \\v[23], Algo pasó...)");
    assert.ok(p._textState.text.includes("小林"));
    await replay(4,"¡Jajaja! \\.¡Qué día maravilloso! \\.¡Qué día maravilloso!");
    assert.equal(writes,0);assert.equal(state.files[path.join(data,"Languages.tsv")],raw);
    assert.ok(!f.posts.some(v=>/\\tl\{|\\v\[|Taylor|小林/.test(v.text)));
}



async function testYEPFormattingCodesDoNotHideWords(){
    const raw="Please remember \\fithat\\fi and \\fball\\fb choices.";
    const f=fixture(45,{responses:{
        "Please remember":"Por favor, recuerda",
        "that":"eso",
        "and":"y",
        "all":"todo",
        "choices.":"opciones."
    },configure:function(c){
        const p=c.Window_Message.prototype;
        p.canStart=function(){return c.$gameMessage.hasText()&&!this._textState;};
        p.startMessage=function(){
            this.originalStarts++;
            this._textState={text:c.$gameMessage.allText(),index:0};
            this.pause=false;
        };
        p.update=function(){
            this.updates++;
            if(this.updateWait())return;
            if(this.canStart())this.startMessage();
        };
    }});
    await wait(25);
    const c=f.context,m=f.$gameMessage;
    c.SceneManager._scene=new c.Scene_Map();
    m.add(raw);
    const w=new c.Window_Message();
    await wait(190);
    w.update();
    assert.equal(w.originalStarts,1,"the formatted first-view message must start after its translation is ready");
    assert.ok(f.posts.some(function(p){return p.text==="that";}),"the word after \\fi must reach the translator");
    assert.ok(f.posts.some(function(p){return p.text==="all";}),"the word after \\fb must reach the translator");
    assert.ok(w._textState.text.includes("\\fi")&&w._textState.text.includes("\\fb"),
        "YEP italic and bold toggles must remain in the displayed message");
    assert.ok(w._textState.text.includes("eso")&&w._textState.text.includes("todo"),
        "the prose adjacent to YEP toggles must be translated");
}
async function testSceneRevisitUsesCompletedTranslation(){
    const raw="Please return to the village.";
    const translated="Por favor, vuelve al pueblo.";
    const f=fixture(140,{responses:{[raw]:translated},configure:function(c){
        const p=c.Window_Message.prototype;
        p.canStart=function(){return c.$gameMessage.hasText()&&!this._textState;};
        p.startMessage=function(){
            this.originalStarts++;
            this._textState={text:c.$gameMessage.allText(),index:0};
            this.pause=false;
        };
        p.update=function(){
            this.updates++;
            if(this.updateWait())return;
            if(this.canStart())this.startMessage();
        };
    }});
    await wait(25);
    const c=f.context,m=f.$gameMessage;
    c.SceneManager._scene=new c.Scene_Map();
    m.add(raw);
    const first=new c.Window_Message();
    first.update();
    assert.equal(first.originalStarts,0,"the first visit waits for the visible translation");
    assert.ok(first._iaFirstGate,"the first visit owns a bounded presentation gate");
    first._iaFirstGate.started-=9000;
    first.update();
    assert.equal(first.originalStarts,1,"the bounded gate eventually releases the original-language message");
    assert.equal(first._textState.text,raw,"the first visit falls back safely if inference is not ready");
    c.SceneManager._scene=new c.Scene_Title();
    m.clear();
    await wait(220);
    assert.ok(f.posts.some(function(p){return p.text===raw;}),"the first visit's translation request completes in the background");
    c.SceneManager._scene=new c.Scene_Map();
    m.add(raw);
    const revisit=new c.Window_Message();
    revisit.update();
    assert.equal(revisit.originalStarts,1,"the next visit does not wait again for a completed translation");
    assert.equal(revisit._textState.text,translated,"the same scene text is Spanish on its next presentation");
    assert.equal(m.allText(),translated,"the cached translation is used without rewriting event data");
}


async function testShortWakeUpLineIsRecognized(){
    const raw="Hey! wake up!";
    const translated="¡Oye, despierta!";
    const f=fixture(35,{responses:{[raw]:translated},configure:function(c){
        const p=c.Window_Message.prototype;
        p.canStart=function(){return c.$gameMessage.hasText()&&!this._textState;};
        p.startMessage=function(){
            this.originalStarts++;
            this._textState={text:c.$gameMessage.allText(),index:0};
            this.pause=false;
        };
        p.update=function(){
            this.updates++;
            if(this.updateWait())return;
            if(this.canStart())this.startMessage();
        };
    }});
    await wait(25);
    const c=f.context,m=f.$gameMessage;
    c.SceneManager._scene=new c.Scene_Map();
    m.add(raw);
    const win=new c.Window_Message();
    win.update();
    assert.equal(win.originalStarts,0,"a short wake-up line with a protected actor code waits for first-view translation");
    for(let i=0;i<24&&win.originalStarts===0;i++){await wait(40);win.update();}
    assert.equal(win.originalStarts,1,"the wake-up message starts after its translation is ready");
    assert.equal(win._textState.text,translated,"the short wake-up line is translated on first view");
    assert.ok(f.posts.some(function(p){return p.text===raw;}),"the short English wake-up line is sent to the translator");
}
async function testShortWakeUpLineWithActorVariableIsRecognized(){
    const raw="Hey! \\n[21] wake up!";
    const translated="¡Oye! \\n[21] ¡despierta!";
    const f=fixture(35,{responses:{"Hey!":"¡Oye!","wake up!":"¡despierta!"},configure:function(c){
        const p=c.Window_Message.prototype;
        p.canStart=function(){return c.$gameMessage.hasText()&&!this._textState;};
        p.startMessage=function(){
            this.originalStarts++;
            this._textState={text:c.$gameMessage.allText(),index:0};
            this.pause=false;
        };
        p.update=function(){
            this.updates++;
            if(this.updateWait())return;
            if(this.canStart())this.startMessage();
        };
    }});
    await wait(25);
    const c=f.context,m=f.$gameMessage;
    c.SceneManager._scene=new c.Scene_Map();
    m.add(raw);
    const win=new c.Window_Message();
    win.update();
    for(let i=0;i<24&&win.originalStarts===0;i++){await wait(40);win.update();}
    assert.equal(win.originalStarts,1,"the actor-variable wake-up line starts after translation");
    assert.equal(win._textState.text,translated,"the actor variable is preserved while both English fragments are translated");
    assert.ok(f.posts.some(function(p){return p.text==="Hey!";}),"the greeting fragment is translated");
    assert.ok(f.posts.some(function(p){return p.text==="wake up!";}),"the wake-up fragment is translated");
    assert.ok(f.posts.every(function(p){return !p.text.includes("\\n[21]");}),"the actor control code is never sent to the translator");
}

async function testUnresolvedIavraReferencesNeverReachTranslatorOrReuseStaleCache(){
    const root=path.join("/tmp","servidor-qa-iavra-unresolved-日本語");
    const cacheDir=path.join(root,"IA Traductora",".local","Rpg","cache");
    const cacheFile=path.join(cacheDir,"translations-ja-en-es-v2.jsonl");
    const raw="#{start.intro_part_one.0}";
    const stale="«start.intro_part_one.0»";
    const record={schema:"ia-traductora-cache-v2",source:"en",original:raw,translated:stale,composed:false};
    const journal=JSON.stringify(record)+"\n";
    const fsState={files:{[cacheFile]:journal},dirs:{[cacheDir]:true}};
    const f=fixture(20,{root,noWww:true,fsState,configure:function(c){
        const p=c.Window_Message.prototype;
        p.canStart=function(){return c.$gameMessage.hasText()&&!this._textState;};
        p.startMessage=function(){
            this.originalStarts++;
            this._textState={text:c.$gameMessage.allText(),index:0};
            this.pause=false;
        };
        p.update=function(){
            this.updates++;
            if(this.updateWait())return;
            if(this.canStart())this.startMessage();
        };
    }});
    await wait(55);
    const c=f.context,m=f.$gameMessage;
    c.SceneManager._scene=new c.Scene_Map();
    m.add(raw);
    const win=new c.Window_Message();
    win.update();
    for(let i=0;i<12&&win.originalStarts===0;i++){await wait(40);win.update();}
    assert.equal(win.originalStarts,1,"an unresolved external key does not block the game");
    assert.equal(win._textState.text,raw,"a stale key-to-key cache result is rejected");
    assert.ok(!f.posts.some(function(p){return p.text===raw||p.text===stale;}),
        "unresolved localization keys are never sent to the neural translator");
    assert.equal(fsState.files[cacheFile],journal,"the old cache journal is not rewritten");
}

async function testIavraExternalJsonCatalogAndKeyFallback(){
    const root=path.join("/tmp","servidor-qa-juego-日本語");
    const content=root;
    const dataDir=path.join(content,"data"),systemDir=path.join(content,"System");
    const enPath=path.join(systemDir,"en.json"),jpPath=path.join(systemDir,"jp.json");
    const japanese="物語は朝日が昇るときに始まります。";
    const englishFallback="The next chapter begins after the storm.";
    const enCatalog={
        start:{intro_part_one:[ "The story begins at dawn." ],extra_line:[englishFallback]},
        names:{"21":"Ryuu","22":"Marin"}
    };
    const jpCatalog={
        start:{intro_part_one:[japanese]},
        names:{"21":"リュウ","22":"マリン"}
    };
    const enRaw=JSON.stringify(enCatalog),jpRaw=JSON.stringify(jpCatalog);
    const fsState={
        files:{
            [path.join(dataDir,"System.json")]:JSON.stringify({startMapId:1}),
            [enPath]:enRaw,
            [jpPath]:jpRaw
        },
        dirs:{[dataDir]:true,[systemDir]:true}
    };
    const plugin={
        name:"Iavra Localization - Core",status:true,description:"<Iavra Localization Core>",
        parameters:{"File Path":"System/{lang}.json","Languages":"en, jp","Escape Code":"#{{key}}"}
    };
    const f=fixture(120,{
        root,noWww:true,fsState,plugins:[plugin],
        responses:{
            [japanese]:"La historia comienza cuando sale el sol.",
            [englishFallback]:"El siguiente capítulo comienza después de la tormenta."
        },
        testHooks:true,
        configure:function(c){
            c.IAVRA={I18N:{language:"jp"}};
            const p=c.Window_Message.prototype;
            p.canStart=function(){return c.$gameMessage.hasText()&&!this._textState;};
            p.startMessage=function(){
                this.originalStarts++;
                this._textState={text:c.$gameMessage.allText(),index:0};
                this.pause=false;
            };
            p.update=function(){
                this.updates++;
                if(this.updateWait())return;
                if(this.canStart())this.startMessage();
            };
        }
    });
    await wait(45);
    const c=f.context,m=f.$gameMessage;
    c.SceneManager._scene=new c.Scene_Map();
    const firstKey="«start.intro_part_one.0»";
    m.add(firstKey);
    const first=new c.Window_Message();
    first.update();
    assert.equal(first.originalStarts,0,"an Iavra fallback key is resolved and gated before the first message is painted");
    for(let i=0;i<30&&first.originalStarts===0;i++){await wait(40);first.update();}
    assert.equal(first.originalStarts,1,"the first Iavra message starts after its external catalog translation is ready");
    assert.equal(first._textState.text,"La historia comienza cuando sale el sol.","the active Japanese catalog entry is translated on first view");
    assert.equal(m.allText(),firstKey,"the source event key remains unchanged after runtime projection");
    m.clear();
    const fallbackKey="#{start.extra_line.0}";
    m.add(fallbackKey);
    const second=new c.Window_Message();
    second.update();
    for(let i=0;i<30&&second.originalStarts===0;i++){await wait(40);second.update();}
    assert.equal(second.originalStarts,1,"an entry missing from the active Japanese file falls back to the configured English catalog");
    assert.equal(second._textState.text,"El siguiente capítulo comienza después de la tormenta.","missing Japanese keys still receive a Spanish display value");
    assert.equal(m.allText(),fallbackKey,"the Iavra escape token remains in the original event message");
    assert.ok(f.posts.some(function(p){return p.text===japanese;}),"Japanese catalog text is inventoried from the external JSON file");
    assert.ok(f.posts.some(function(p){return p.text===englishFallback;}),"English fallback text is inventoried from the external JSON file");
    assert.ok(!f.posts.some(function(p){return ["Ryuu","Marin","リュウ","マリン"].includes(p.text);}),
        "the names subtree is excluded from translation");
    assert.equal(fsState.files[enPath],enRaw,"the English localization catalog is read-only");
    assert.equal(fsState.files[jpPath],jpRaw,"the Japanese localization catalog is read-only");
    m.clear();
    const unknownKey="«missing.external.branch.0»";
    m.add(unknownKey);
    const third=new c.Window_Message();
    third.update();
    for(let i=0;i<30&&third.originalStarts===0;i++){await wait(40);third.update();}
    assert.equal(third.originalStarts,1,"an unknown external key does not hold the message window");
    assert.equal(third._textState.text,unknownKey,"an unknown external key is left untouched");
    assert.ok(!f.posts.some(function(p){return p.text===unknownKey;}),"an unknown external key is not sent to the translator");
}

async function testLargeGamePausesBackgroundPrefetch(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const state={files:{},dirs:{[data]:true}};
    const events=[null];
    for(let i=0;i<1300;i++){
        events.push({id:i+1,name:"Large event "+i,pages:[{trigger:0,list:[
            {code:101,parameters:["",0,0,2]},
            {code:401,parameters:["Please open the main gate now. This is sample message number "+i+"."]}
        ]}]});
    }
    state.files[path.join(data,"System.json")]=JSON.stringify({locale:"en_US",startMapId:1});
    state.files[path.join(data,"Map001.json")]=JSON.stringify({events});
    const f=fixture(1,{fsState:state,batch:true,configure(c){
        const p=c.Window_Message.prototype;
        p.updateWait=function(){return false;};
        p.canStart=function(){return c.$gameMessage.hasText()&&!this._textState;};
    }});
    const title=new f.context.Scene_Title();f.context.SceneManager._scene=title;title.start();
    // The scanner and cache reader run asynchronously. Put the game in its
    // active map before the large inventory reaches the prefetch scheduler.
    f.context.SceneManager._scene=new f.context.Scene_Map();
    await wait(450);
    assert.equal(f.posts.length,0,
        "bulk inventory must pause instead of competing with a large active game");
    f.$gameMessage._texts=["Please open the gate now."];
    const firstView=new f.context.Window_Message();
    assert.equal(firstView.updateWait(),true,
        "the first visible dialogue must wait briefly even while bulk inventory is paused");
    await wait(80);
    assert.ok(f.posts.some(p=>p.text==="Please open the gate now."),
        "the visible dialogue must bypass the paused background inventory queue");
    assert.equal(firstView.updateWait(),false,
        "the first visible dialogue must resume as soon as its translation is cached");
    f.$gameMessage._texts=[];
    f.$gameMessage.add("Please translate this visible sentence.");
    await wait(80);
    assert.ok(f.posts.some(p=>p.text==="Please translate this visible sentence."),
        "foreground visible text still reaches the worker while bulk prefetch is paused");
}

async function testLargeCommonEventsJsonIsParsedIncrementally(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const state={files:{},dirs:{[data]:true}};
    const events=[null],longText=("Please open the extraordinarily complicated wooden gate while the guards carefully watch the northern courtyard and wait for our signal. ").repeat(4);
    for(let i=0;i<1978;i++){
        const list=[];
        for(let j=0;j<10;j++)list.push({code:401,parameters:[longText]});
        events.push({id:i+1,name:"Common event "+i,trigger:0,list});
    }
    const finalText="Please open the hidden gate now.";
    events[events.length-1].list=[{code:401,parameters:[finalText]}];
    const raw=JSON.stringify(events);
    assert.ok(Buffer.byteLength(raw,"utf8")>10*1024*1024,
        "regression fixture must exercise a genuinely large CommonEvents.json");
    state.files[path.join(data,"System.json")]=JSON.stringify({locale:"en_US",startMapId:1});
    state.files[path.join(data,"Map001.json")]=JSON.stringify({events:[null]});
    state.files[path.join(data,"CommonEvents.json")]=raw;
    const f=fixture(1,{fsState:state,batch:true,jsonParseSizes:[],testHooks:true});
    const title=new f.context.Scene_Title();f.context.SceneManager._scene=title;title.start();
    f.context.SceneManager._scene=new f.context.Scene_Map();
    let heartbeats=0;
    const heartbeat=setInterval(()=>heartbeats++,1);
    assert.ok(raw.length<16*1024*1024,
        "large CommonEvents fixture must stay within the per-file safety limit");
    const inspect=f.context.window.__IA_TRADUCTORA_TEST__;
    assert.ok(inspect,"opt-in inventory test probe must be installed");
    const deadline=Date.now()+15000;
    try{
        while(!inspect.done()&&Date.now()<deadline)await wait(10);
    }finally{clearInterval(heartbeat);}
    assert.ok(inspect.done(),"large CommonEvents inventory must finish");
    assert.ok(inspect.has("en",finalText),
        "last CommonEvents entry must be parsed and inventoried even while bulk prefetch is paused");
    assert.ok(f.jsonParseSizes.length>=events.length,
        "CommonEvents entries must be parsed individually, not as one giant array");
    assert.ok(Math.max.apply(null,f.jsonParseSizes)<100000,
        "no synchronous JSON.parse may receive the whole 10+ MB common-event file");
    assert.ok(heartbeats>2,
        "incremental CommonEvents parsing must yield to the render/event loop");
}
async function testInventoryHasNoFortyThousandTextCeiling(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","www","data");
    const state={files:{},dirs:{[data]:true}};
    const events=[null],count=40025;
    let lastText="";
    for(let i=0;i<count;i++){
        const suffix=String(i+1).padStart(5,"0");
        const text="Please open the hidden gate number "+suffix+" now.";
        if(i===count-1)lastText=text;
        events.push({id:i+1,name:"Common event "+(i+1),trigger:0,
            list:[{code:401,parameters:[text]}]});
    }
    const raw=JSON.stringify(events);
    assert.ok(raw.length<16*1024*1024,
        "40,025 distinct texts must fit inside the supported per-file safety limit");
    state.files[path.join(data,"System.json")]=JSON.stringify({locale:"en_US",startMapId:1});
    state.files[path.join(data,"Map001.json")]=JSON.stringify({events:[null]});
    state.files[path.join(data,"CommonEvents.json")]=raw;
    const f=fixture(0,{fsState:state,batch:true,testHooks:true});
    const title=new f.context.Scene_Title();f.context.SceneManager._scene=title;title.start();
    f.context.SceneManager._scene=new f.context.Scene_Map();
    const inspect=f.context.window.__IA_TRADUCTORA_TEST__;
    assert.ok(inspect,"opt-in inventory test probe must be installed");
    const deadline=Date.now()+45000;
    while(!inspect.done()&&Date.now()<deadline)await wait(10);
    assert.ok(inspect.done(),"full inventory must finish without a candidate-count cutoff");
    assert.ok(inspect.inventorySize()>40000,
        "the inventory must exceed the former 40,000-text ceiling");
    assert.ok(inspect.has("en",lastText),
        "the final unique event text must be present after the former cutoff");
    assert.equal(inspect.limited(),false,
        "a large number of valid texts must not be reported as a truncated inventory");
}
async function testR6FirstViewNativeGate(mz){
    const text="Where are you going?";
    const choice="Please open the door.";
    const cold="Please close the window.";
    const f=fixture(110,{mz:mz,nativePaint:true,responses:{
        "Where are you going?":"¿Adónde vas?",
        "Please open the door.":"Por favor, abre la puerta.",
        "Please close the window.":"Por favor, cierra la ventana."
    },configure:function(c){
        c.Window_Message.prototype.canStart=function(){return c.$gameMessage.hasText();};
        c.Window_Message.prototype.startMessage=function(){
            this.originalStarts++;
            this._textState={text:c.$gameMessage.allText(),index:0};
            this.pause=false;
        };
        c.Window_Message.prototype.startInput=function(){
            if(!this._choice)this._choice=new c.Window_ChoiceList(this);
            this._choice.start();
        };
        c.Window_Message.prototype.update=function(){
            this.updates++;
            if(this.updateWait())return;
            if(this.pause){
                if(c.$gameMessage._choices.length&&!this._choice)this.startInput();
                return;
            }
            if(this.canStart())this.startMessage();
            else if(c.$gameMessage._choices.length&&!this._choice)this.startInput();
        };
        function Choice(messageWindow){
            this._messageWindow=messageWindow;this._list=[];this.painted=[];this.started=false;
        }
        Choice.prototype.start=function(){
            this.started=true;
            this._list=c.$gameMessage._choices.map(function(name,index){return {name:name,ext:index,enabled:true};});
            this._list.forEach((_,index)=>this.drawItem(index));
        };
        Choice.prototype.drawItem=function(index){this.painted.push(this._list[index].name);};
        c.Window_ChoiceList=Choice;
    }});
    await wait(25); // let the local status handshake finish before the connected-path test
    const c=f.context,m=f.$gameMessage;
    m.add(text);
    const w=new c.Window_Message();
    w.update();
    assert.equal(w.originalStarts,0,(mz?"MZ":"MV")+" waits before the first message paint");
    await wait(170);
    w.update();
    assert.equal(w.originalStarts,1,(mz?"MZ":"MV")+" starts the message after translation");
    assert.ok(w._textState.text.includes("¿Adónde vas?"),"the first-view dialogue is Spanish in the native window");
    assert.equal(m.allText(),"¿Adónde vas?","the first-view gate uses the validated Spanish runtime message without changing the source event command");
    w.finishPage();
    m.setChoices([choice],0,0);
    w.startInput();
    assert.ok(w._choice&&!w._choice.started,"native choice start is deferred while labels are pending");
    await wait(170);
    assert.ok(w._choice.started,"choice window starts after first-view translations are ready");
    assert.deepEqual(w._choice._list.map(x=>x.name),["Por favor, abre la puerta."]);
    assert.deepEqual(w._choice._list.map(x=>x.ext),[0],"choice branch index is preserved");
    assert.deepEqual(m._choices,[choice],"source choice labels are restored after native start");
    m.clear();
    m.setChoices([cold],0,0);
    const only=new c.Window_Message();
    only.update();
    assert.ok(!only._choice||!only._choice.started,"standalone choices do not paint before translation");
    await wait(170);
    only.update();
    assert.ok(only._choice&&only._choice.started,"standalone choice appears after first-view translation");
    assert.deepEqual(only._choice._list.map(x=>x.name),["Por favor, cierra la ventana."]);
    assert.deepEqual(only._choice._list.map(x=>x.ext),[0]);
    assert.deepEqual(m._choices,[cold]);
}

async function testR9BuiltinNameInputProtected(){
    const f=fixture(5,{nativePaint:true,responses:{
        "What should I call you?":"¿Cómo debería llamarte?"
    },configure:function(c){
        const p=c.Window_Message.prototype;
        p.canStart=function(){return c.$gameMessage.hasText();};
        p.startMessage=function(){
            this.originalStarts++;
            this._textState={text:c.$gameMessage.allText(),index:0};
            this.pause=false;
        };
        p.update=function(){
            this.updates++;
            if(this.updateWait())return;
            if(this.canStart())this.startMessage();
        };
        c.Scene_Name.prototype.start=function(){this.started=true;};
        c.Scene_Name.prototype.terminate=function(){this.terminated=true;};
        function NameEdit(){c.Window_Base.call(this);}
        NameEdit.prototype=Object.create(c.Window_Base.prototype);NameEdit.prototype.constructor=NameEdit;
        function NameInput(){c.Window_Base.call(this);}
        NameInput.prototype=Object.create(c.Window_Base.prototype);NameInput.prototype.constructor=NameInput;
        c.Window_NameEdit=NameEdit;c.Window_NameInput=NameInput;
    }});
    const c=f.context,m=f.$gameMessage;
    const scene=new c.Scene_Name();
    scene._editWindow=new c.Window_NameEdit();
    scene._inputWindow=new c.Window_NameInput();
    c.SceneManager._scene=scene;
    scene.start();
    scene._editWindow.drawText("Player",0,0,120);
    scene._inputWindow.drawText("A",0,0,40);
    scene._inputWindow.drawText("OK",0,0,40);
    await wait(60);
    assert.deepEqual(scene._editWindow.drawn.map(x=>x.text),["Player"],"native name edit is not rewritten");
    assert.deepEqual(scene._inputWindow.drawn.map(x=>x.text),["A","OK"],"native name input grid and commands are not rewritten");
    assert.equal(f.posts.length,0,"native name input text is not sent to translation");
    scene.terminate();
    c.SceneManager._scene=new c.Scene_Map();
    m.add("What should I call you?");
    const message=new c.Window_Message();
    message.update();
    assert.equal(message.originalStarts,0,"the dialogue prompt still waits for translation");
    await wait(80);
    message.update();
    assert.equal(message.originalStarts,1,"normal dialogue resumes after leaving Scene_Name");
    assert.ok(message._textState.text.includes("¿Cómo debería llamarte?"),"the name prompt is translated outside the input screen");
}

async function testR6OfflineDeadlineAndForm(){
    const f=fixture(0,{mz:true,disconnected:true,configure(c){
        const p=c.Window_Message.prototype;p.updateWait=function(){return false;};
        p.canStart=function(){return c.$gameMessage.hasText();};
        const nodes={},events={};let accepted=0,debug=0;
        function node(id,type,value){
            return nodes[id]={type,value,style:{left:"12px",top:"24px"},listeners:{},
                addEventListener(k,fn){(this.listeners[k]||(this.listeners[k]=[])).push(fn);},
                fire(k,key){
                    let stopped=false;const e={key,stopPropagation(){stopped=true;}};
                    (this.listeners[k]||[]).forEach(fn=>fn(e));if(!stopped&&key==="c")debug++;
                }};
        }
        c.document={getElementById:id=>nodes[id]||null};
        function Interpreter(){}
        Interpreter.prototype._inputForm=function(){
            const input=node("_111_input","text","mc");node("_111_submit","submit","決定");
            input.addEventListener("keydown",e=>{if(e.key==="Enter")accepted++;});
            c.Input.form_mode=true;
        };
        c.Game_Interpreter=Interpreter;
        c.__form={nodes,accepted:()=>accepted,debug:()=>debug,close(){delete nodes._111_input;delete nodes._111_submit;c.Input.form_mode=false;}};
    }});
    await wait(25);const c=f.context,m=f.$gameMessage,w=new c.Window_Message();
    m._texts=["Where are you going?"];
    assert.equal(w.updateWait(),true);
    w._iaFirstGate.started-=9000;
    assert.equal(w.updateWait(),false,"offline MZ deadline must release native UI");
    new c.Game_Interpreter()._inputForm();
    const input=c.__form.nodes._111_input,submit=c.__form.nodes._111_submit;
    input.fire("keydown","c");input.fire("keyup","c");input.fire("keypress","c");
    input.fire("keydown","Enter");
    assert.equal(c.__form.debug(),0);assert.equal(c.__form.accepted(),1);
    assert.equal(input.value,"mc");assert.equal(submit.value,"Aceptar");
    assert.equal(input.style.left,"12px");assert.equal(input.style.top,"24px");
    assert.equal(w.updateWait(),false,"name entry must not acquire a translation wait");
    c.__form.close();
    // Key isolation is local to the form; no global game hotkey is changed.
    assert.equal(c.Input.form_mode,false);
}


async function testR7AuthoredScriptAndPicture(){
    const root=path.join("/tmp","servidor-qa-juego-日本語"),dir=path.join(root,"data");
    const variables=[];variables[21]="MESSAGE HOLDER";variables[25]="MESSAGE HOLDER";variables[26]="SYNTAX HOLDER";
    const command=(code,...parameters)=>({code,parameters});
    const parser=[command(355,'var slice = $gameVariables.value(21).indexOf(".");'),
        command(655,"var message = $gameVariables.value(21).slice(slice + 1);"),
        command(655,"var syntax = $gameVariables.value(21).slice(0,slice);"),
        command(655,"$gameVariables.setValue(25, message);"),
        command(655,"$gameVariables.setValue(26, syntax);"),command(401,"\\v[25]\\Wait[5]")];
    const one="Where are you going?",two="Please wait here.",caption="Please check the door.",nameText="1Hero, open the gate.";
    const mapList=[command(355,'$gameVariables.setValue(21, "AAHaOp<<.'+one+'");'),
        command(355,'$gameVariables.setValue(21, "ABFrEx.'+nameText+'");'),
        command(355,'$gameVariables.setValue(48, "VoiceAssetFile");'),
        command(355,'$gameVariables.setValue(21, "Never execute " + secret());'),
        command(357,"TextPicture","set","Set Text Picture",{text:"Guide: "+caption}),
        command(357,"OtherPlugin","set","Not text",{text:"Private script parameter"}),
        command(657,"Text = editor annotation")];
    const fsState={files:{[path.join(dir,"System.json")]:JSON.stringify({locale:"en_US",variables,startMapId:1}),
        [path.join(dir,"CommonEvents.json")]:JSON.stringify([null,{id:1,name:"Message parser",list:parser}]),
        [path.join(dir,"Map001.json")]:JSON.stringify({events:[null,{pages:[{list:mapList}]}]})},dirs:{[dir]:true}};
    const values={21:"AAHaOp<<."+one,25:one};let writes=0,name="PlayerChosen";
    const f=fixture(70,{mz:true,nativePaint:true,batch:true,fsState,plugins:[{name:"TextPicture",status:true,parameters:{}}],
        responses:{[one]:"¿Adónde vas?",[two]:"Espera aquí.",[caption]:"Revisa la puerta.",", open the gate.":", abre la puerta."},
        configure(c){
            c.$gameVariables={value:i=>values[i],setValue(){writes++;throw Error("game write")}};
            c.$gameActors={actor:()=>({name:()=>name})};
            c.$dataSystem={locale:"en_US",variables};c.$dataCommonEvents=[null,{list:parser}];
            const p=c.Window_Message.prototype,base=p.startMessage;
            p.updateWait=function(){return false;};p.canStart=function(){return c.$gameMessage.hasText()&&!this._textState;};
            p.update=function(){this.updates++;if(!this.updateWait()&&this.canStart())this.startMessage();};
            p.startMessage=function(){
                base.apply(this,arguments);
                this._textState.text=this._textState.text.replace(/\\v\[25\]/gi,values[25]).replace(/\\N\[1\]/gi,name);
            };
            function Sprite_Picture(pic){this.pic=pic;this.mzkp_text="";this.paints=[];}
            Sprite_Picture.prototype.picture=function(){return this.pic;};
            Sprite_Picture.prototype.updateBitmap=function(){
                const pic=this.picture();
                if(!pic||pic._name!==""){this.mzkp_text="";return;}
                if(this.mzkp_text!==pic.mzkp_text||pic.mzkp_textChanged){
                    this.mzkp_text=pic.mzkp_text;this.paints.push(this.mzkp_text);
                    this.bitmap={text:this.mzkp_text};pic.mzkp_textChanged=false;
                }
            };
            c.Sprite_Picture=Sprite_Picture;
        }});
    const c=f.context;await wait(20);c.$gameMessage._texts=["\\v[25]\\Wait[5]"];
    const w=new c.Window_Message();w.update();
    assert.equal(w.originalStarts,0);
    const until=async pred=>{const end=Date.now()+5000;while(!pred()&&Date.now()<end)await wait(50);assert.ok(pred());};
    await until(()=>{w.update();return w.originalStarts===1;});
    assert.equal(w._textState.text,"¿Adónde vas?\\Wait[5]");
    assert.equal(c.$gameMessage.allText(),"\\v[25]\\Wait[5]");
    assert.equal(values[21],"AAHaOp<<."+one);assert.equal(values[25],one);
    // Same raw variable reference, different value, no scene replay.
    values[21]="ABHaOp."+two;values[25]=two;
    const next=new c.Window_Message();next.update();
    await until(()=>{next.update();return next.originalStarts===1;});
    assert.equal(next._textState.text,"Espera aquí.\\Wait[5]");
    values[21]="ABFrEx."+nameText;values[25]=nameText.replace("1Hero",name);
    const n=new c.Window_Message();n.update();
    await until(()=>{n.update();return n.originalStarts===1;});
    assert.equal(n._textState.text,name+", abre la puerta.\\Wait[5]");
    const pic={_name:"",mzkp_text:"Guide: "+caption,mzkp_textChanged:true,angle:9};
    const spr=new c.Sprite_Picture(pic);
    await until(()=>{spr.updateBitmap();return spr.bitmap&&spr.bitmap.text==="Guide: Revisa la puerta.";});
    assert.equal(pic.mzkp_text,"Guide: "+caption);assert.equal(pic.angle,9);
    const paintCount=spr.paints.length;for(let i=0;i<8;i++)spr.updateBitmap();
    assert.equal(spr.paints.length,paintCount,"cached picture must not repaint every frame");
    const cold={_name:"",mzkp_text:"Guide: Please open the window.",mzkp_textChanged:true};
    spr.pic=cold;spr.updateBitmap();spr.pic={_name:"real_image.png",mzkp_text:"Guide: "+caption};
    await wait(150);spr.updateBitmap();assert.equal(spr.mzkp_text,"","expired image must not be revived");
    assert.equal(writes,0);
    assert.ok(!f.posts.some(x=>/AAHaOp|ABFrEx|VoiceAssetFile|Private script parameter|Never execute|editor annotation|PlayerChosen|1Hero|\\v\[25\]/.test(x.text)));
    assert.ok(f.posts.some(x=>x.text===caption));
}


async function testR7VerifiedVariableSurfaces(){
    const root=path.join("/tmp","servidor-qa-juego-日本語"),dir=path.join(root,"data");
    const variables=[];Object.entries({21:"MESSAGE HOLDER",25:"MESSAGE HOLDER",26:"SYNTAX HOLDER",
        140:"NPC Name",241:"Quiz Question Line 1",242:"Answer1",243:"Answer2",266:"Blueprint Description",275:"Blueprint Title"}).forEach(([id,label])=>variables[id]=label);
    const command=(code,...parameters)=>({code,parameters});
    const parser=[command(355,'var slice = $gameVariables.value(21).indexOf(".");'),
        command(655,"var message = $gameVariables.value(21).slice(slice + 1);"),
        command(655,"var syntax = $gameVariables.value(21).slice(0,slice);"),
        command(655,"$gameVariables.setValue(25, message);"),command(655,"$gameVariables.setValue(26, syntax);"),
        command(401,"\\v[25]")];
    const question="Where is the library?",answer="Behind the old castle.",item="Open the wooden box.";
    const values={140:"Stranger",241:question,242:answer,243:"Peter",266:item,73:12345,275:"UnverifiedPlayerLabel"};
    const fsState={files:{[path.join(dir,"System.json")]:JSON.stringify({locale:"en_US",variables}),
        [path.join(dir,"CommonEvents.json")]:JSON.stringify([null,{id:1,list:parser}]),
        [path.join(dir,"Map001.json")]:JSON.stringify({events:[null,{pages:[{list:[
            command(122,241,241,0,4,JSON.stringify(question)),command(122,242,242,0,4,JSON.stringify(answer)),
            command(122,243,243,0,4,JSON.stringify("Peter")),command(122,73,73,0,4,"doNotExecute()")
        ]}]}]})},dirs:{[dir]:true}};
    let writes=0;
    const f=fixture(65,{mz:true,nativePaint:true,fsState,batch:true,plugins:[{name:"TextPicture",status:true,parameters:{}}],
        responses:{[question]:"¿Dónde está la biblioteca?",[answer]:"Detrás del castillo antiguo.",[item]:"Abre la caja de madera."},
        configure(c){
            c.$dataSystem={locale:"en_US",variables};c.$dataCommonEvents=[null,{list:parser}];
            c.$dataItems=[null,{name:"Chest",description:item}];
            c.$gameVariables={value:i=>values[i],setValue(){writes++;throw Error("unexpected write")}};
            const p=c.Window_Message.prototype,base=p.startMessage;
            p.updateWait=function(){return false;};p.canStart=function(){return c.$gameMessage.hasText()&&!this._textState;};
            p.update=function(){if(!this.updateWait()&&this.canStart())this.startMessage();};
            p.startMessage=function(){this.nativeInput=c.$gameMessage.allText();base.apply(this,arguments);};
            function Choice(items){this._list=items.map((name,ext)=>({name,ext,symbol:"choice",enabled:true}));this.painted=[];}
            Choice.prototype.drawItem=function(i){this.painted[i]=this._list[i].name;};
            Choice.prototype.update=function(){};
            c.Window_ChoiceList=Choice;
            function Sprite(pic){this.pic=pic;this.mzkp_text="";this.bitmap=null;}
            Sprite.prototype.picture=function(){return this.pic;};
            Sprite.prototype.updateBitmap=function(){if(this.mzkp_text!==this.pic.mzkp_text||this.pic.mzkp_textChanged){this.mzkp_text=this.pic.mzkp_text;this.bitmap={text:this.mzkp_text};this.pic.mzkp_textChanged=false;}};
            c.Sprite_Picture=Sprite;
        }});
    const c=f.context;await wait(15);
    c.$gameMessage._texts=["<center>\\c[4]\\v[241]"];
    c.$gameMessage.setChoices(["<center>\\v[242]","<center>\\v[243]"]);
    const w=new c.Window_Message();w.update();
    assert.equal(w.originalStarts,0);
    const until=async pred=>{const end=Date.now()+5000;while(!pred()&&Date.now()<end)await wait(50);assert.ok(pred());};
    await until(()=>{w.update();return w.originalStarts===1;});
    assert.equal(w.nativeInput,"<center>\\c[4]¿Dónde está la biblioteca?");
    assert.equal(c.$gameMessage.allText(),"<center>\\c[4]\\v[241]");
    const choice=new c.Window_ChoiceList(c.$gameMessage._choices);choice.drawItem(0);choice.drawItem(1);
    assert.equal(choice.painted[0],"<center>Detrás del castillo antiguo.");
    assert.equal(choice.painted[1],"<center>\\v[243]");
    assert.equal(choice._list[0].name,"<center>\\v[242]");assert.equal(choice._list[0].ext,0);
    const npc={_name:"",mzkp_text:"\\c[4]\\v[140]",mzkp_textChanged:true};
    const sp=new c.Sprite_Picture(npc);sp.updateBitmap();
    assert.equal(sp.bitmap.text,"\\c[4]Desconocido");assert.equal(npc.mzkp_text,"\\c[4]\\v[140]");
    values[140]="Peter";sp.updateBitmap();assert.equal(sp.bitmap.text,"\\c[4]\\v[140]");
    const description={_name:"",mzkp_text:"\\c[4]\\v[266]",mzkp_textChanged:true};
    sp.pic=description;await until(()=>{sp.updateBitmap();return sp.bitmap.text==="\\c[4]Abre la caja de madera.";});
    const counters={_name:"",mzkp_text:"\\v[73]",mzkp_textChanged:true};sp.pic=counters;sp.updateBitmap();assert.equal(sp.bitmap.text,"\\v[73]");
    const unknown={_name:"",mzkp_text:"\\v[275]",mzkp_textChanged:true};sp.pic=unknown;sp.updateBitmap();assert.equal(sp.bitmap.text,"\\v[275]");
    assert.equal(writes,0);assert.equal(values[241],question);assert.equal(values[242],answer);
    assert.ok(!f.posts.some(v=>/Peter|12345|doNotExecute|UnverifiedPlayerLabel|\\v\[/.test(v.text)));
}


async function testR16HexChoicesAndChauPopup(){
    const root=path.join("/tmp","servidor-qa-juego-日本語"),data=path.join(root,"www","data"),
        folder=path.join(root,"IA Traductora",".local","Rpg","cache");
    const action="Close the wooden door.",dialogue="We should stay here.",popup="You found a silver key.",
        actionEs="Cierra la puerta de madera.",dialogueEs="Deberíamos quedarnos aquí.",popupEs="Has encontrado una llave de plata.";
    const first="\\hc[ffffff]1: \\hc[5065c3][STRENGTH] \\hc[07e800]<"+action+"> \\hc[7da7bf]\""+dialogue+"\"";
    const second="\\hc[ffffff]2: \\hc[07e800]<Open the old gate.>";
    const expected="\\hc[ffffff]1: \\hc[5065c3][FUERZA] \\hc[07e800]<"+actionEs+"> \\hc[7da7bf]\""+dialogueEs+"\"";
    const raw=[first,second],saved=JSON.stringify(raw);
    const state={files:{},dirs:{[data]:true,[folder]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({locale:"en_US",startMapId:1});
    state.files[path.join(data,"Map001.json")]=JSON.stringify({events:[null,{pages:[{list:[
        {code:102,parameters:[raw,-1,0,1,2]},
        {code:356,parameters:["simple_popup player font_size 20 text_color #858585 "+popup]},
        {code:356,parameters:["simple_popup player font_size 20 text_color #fffb00 +\\v[114] Gold!"]},
        {code:356,parameters:["change_popup_se Bell 90 100 0"]}
    ]}]}]});
    state.files[path.join(folder,"translations-ja-en-es-v2.jsonl")]=JSON.stringify({
        schema:"ia-traductora-cache-v2",source:"en",original:first,
        translated:first.replace(dialogue,dialogueEs),composed:true})+"\n";
    const plugins=["YEP_X_ExtMesPack1","OssraWindowChoiceList","Chau_Simple Popups"].map(name=>({name,status:true,parameters:{}}));
    const f=fixture(100,{fsState:state,plugins,testHooks:true,responses:{
        [action]:actionEs,[dialogue]:dialogueEs,"Open the old gate.":"Abre la puerta antigua.",[popup]:popupEs},configure(c){
        function Choice(){this.active=false;this.openness=0;this._list=[];this.painted=[];this.starts=0;this._index=1;this.redraws=0;}
        Choice.prototype=Object.create(c.Window_Base.prototype);Choice.prototype.constructor=Choice;
        Choice.prototype.start=function(){
            this.starts++;this.active=true;this.openness=255;
            this._list=c.$gameMessage._choices.map((name,i)=>({name,symbol:"choice",enabled:i===0,ext:i+11}));
            this._list.forEach((_,i)=>this.drawItem(i));
        };
        Choice.prototype.drawItem=function(i){this.painted[i]=this._list[i].name;};
        Choice.prototype.redrawItem=function(i){this.redraws++;this.drawItem(i);};
        Choice.prototype.update=function(){};
        Choice.prototype.textWidthEx=function(v){this.measured=v;return v.length*8;};
        Choice.prototype.itemRectForText=function(){return {width:200};};
        Choice.prototype.updatePlacement=function(){throw Error("active list must never be rebuilt");};
        c.Window_ChoiceList=Choice;
        function Character(){this._popupRequests=[];}
        Character.prototype.requestPopup=function(text,fontSize,textColor,oy){this._popupRequests.push({text,fontSize,textColor,oy});};
        function Popup(raw,font,color){this.setText(raw,font,color);}
        Popup.prototype.setText=function(raw,font,color){
            this.raw=raw;this.font=font;this.color=color;
            this.visibleText=raw.replace(/\\v\[114\]/gi,"14");this.bitmap=new c.Bitmap(500,50);
            for(const ch of this.visibleText)this.bitmap.drawText(ch,0,0,20,20);
        };
        function Sprite(character){this._character=character;this.created=[];}
        Sprite.prototype.addPopupSprite=function(){const x=this._character._popupRequests.shift();if(x)this.created.push(new c.Sprite_Popup(x.text,x.fontSize,x.textColor));};
        c.Game_Character=Character;c.Sprite_Character=Sprite;c.Sprite_Popup=Popup;
    }});
    const c=f.context;c.SceneManager._scene=new c.Scene_Map();new c.Scene_Title().start();
    c.$gameMessage.setChoices(raw);
    const win=new c.Window_ChoiceList();win.start();
    assert.equal(win.starts,1);assert.equal(JSON.stringify(c.$gameMessage._choices),saved);
    assert.equal(win._list[0].name,first,"do not rewrite native choice labels");
    assert.equal(win.painted[0],first,"old partial composite never replaces the complete original");
    const ch=new c.Game_Character(),sprite=new c.Sprite_Character(ch);
    ch.requestPopup(popup,20,"#858585",7);
    const originalRequest=ch._popupRequests[0];
    const deadline=Date.now()+3500;
    while(Date.now()<deadline&&(win.painted[0]!==expected||!sprite.created.length)){
        win.update();if(ch._popupRequests.length)sprite.addPopupSprite();await wait(30);
    }
    assert.equal(win.painted[0],expected);assert.equal(win.painted[1],"\\hc[ffffff]2: \\hc[07e800]<Abre la puerta antigua.>");
    assert.equal(win.starts,1);assert.equal(win._index,1);assert.equal(win._list[1].enabled,false);assert.equal(win._list[1].ext,12);
    assert.equal(win._list[0].name,first);assert.equal(JSON.stringify(c.$gameMessage._choices),saved);
    win.textWidthEx(first);assert.equal(win.measured,expected);
    assert.equal(sprite.created.length,1);assert.equal(sprite.created[0].raw,popupEs);
    assert.equal(sprite.created[0].font,20);assert.equal(sprite.created[0].color,"#858585");
    assert.equal(originalRequest.text,popup);assert.equal(originalRequest.oy,7);
    ch.requestPopup("+\\v[114] Gold!",20,"#fffb00",0);sprite.addPopupSprite();
    assert.equal(sprite.created[1].visibleText,"+14 de oro!");
    assert.ok(f.posts.some(p=>p.text===action)&&f.posts.some(p=>p.text===dialogue)&&f.posts.some(p=>p.text===popup));
    assert.ok(!f.posts.some(p=>/\\hc|simple_popup|#858585|change_popup_se|\\v\[114\]|^STRENGTH$/.test(p.text)));
    // A reused window cannot receive an expired row's translation.
    const next="\\hc[ffffff]1: \\hc[07e800]<Wait by the river.>";
    c.$gameMessage.setChoices([next]);win.start();win.active=false;
    const painted=win.painted[0];await wait(140);for(let i=0;i<8;i++)win.update();
    assert.equal(win.painted[0],painted);assert.equal(win._list[0].name,next);
}
async function testR15NativeLocaleAndFallback(){
    const root=path.join("/tmp","servidor-qa-juego-日本語"),base=path.join(root,"www"),
        loc=path.join(base,"loc"),pics=path.join(base,"img","pictures"),data=path.join(base,"data");
    const fileState={files:{},dirs:{[loc]:true,[pics]:true,[data]:true}};
    const key="sample_event_1",missing="sample_event_2",original="We will meet in the garden.",
        spanish="Nos veremos en el jardin.",fallback="Please wait near the fountain.",
        esFallback="Espera cerca de la fuente.",desc="The blue lantern.",esDesc="La linterna azul.";
    const enMap={[key]:{text:[original]},[missing]:{text:[fallback]}},
        spMap={[key]:{text:[spanish]},[missing]:{text:[fallback]}};
    const enDesc={sample_desc:{text:[desc]}},spDesc={sample_desc:{text:[esDesc]}};
    const enLines={sample_line:{en:["Good morning, friend."],jp:["おはよう。"]}},
        spLines={sample_line:{en:["Buenos días, amigo."],jp:["おはよう。"]}};
    const catalog={"RemMap_EN.json":enMap,"RemMap_SP.json":spMap,"RemDesc_EN.json":enDesc,
        "RemDesc_SP.json":spDesc,"RemLines.json":enLines,"RemLines_SP.json":spLines};
    for(const [name,doc] of Object.entries(catalog))fileState.files[path.join(loc,name)]=JSON.stringify(doc);
    fileState.files[path.join(data,"System.json")]=JSON.stringify({locale:"en_US",startMapId:1});
    const ref="\\REM_MAP["+key+"]",missingRef="\\REM_MAP["+missing+"]",choiceRef="\\REM_DESC[sample_desc]";
    fileState.files[path.join(data,"Map001.json")]=JSON.stringify({events:[null,{pages:[{list:[
        {code:401,parameters:[ref]},{code:401,parameters:[missingRef]},
        {code:102,parameters:[[choiceRef],0,0,2,0]}]}]}]});
    for(const mode of ["easy","normal","hard"])for(const i of [1,2])
        fileState.files[path.join(pics,"difficulty_"+mode+i+"_SP.png")]="synthetic picture";
    const plugins=["RemtairyTextManager","RemtairyTextManager_SP","RemtairyConfigManager","RemtairyMisc","RemtairyLines"]
        .map(name=>({name,status:true,parameters:{}}));
    const originalCatalog=JSON.stringify(catalog);
    function configure(c){
        c.RemLanguageEN=1;c.RemLanguageSP=6;
        c.ConfigManager={remLanguage:1,remVoiceLanguage:0,saves:0,
            applyData(config){this.remLanguage=config.remLanguage;this.remVoiceLanguage=config.remVoiceLanguage;},
            save(){this.saves++;}};
        const maps=new Map([[1,()=>enMap],[6,()=>spMap]]),descs=new Map([[1,()=>enDesc],[6,()=>spDesc]]);
        c.TextManager={getLocalizedMapMappings(){return maps;},getLocalizedDescriptionMappings(){return descs;},
            getLocalizedText(m,id){const table=m.get(c.ConfigManager.remLanguage)();return table[id].text.join("\n");},
            remMiscMapText(id){return this.getLocalizedText(maps,id);},
            remMiscDescriptionText(id){return this.getLocalizedText(descs,id);}};
        Object.defineProperty(c.TextManager,"isSpanish",{get(){return c.ConfigManager.remLanguage===6;}});
        c.Window_Base.prototype.convertEscapeCharacters=function(raw){
            return raw.replace(/\\REM_(MAP|DESC)\[([A-Za-z0-9_]+)\]/g,(_,type,id)=>
                type==="MAP"?c.TextManager.remMiscMapText(id):c.TextManager.remMiscDescriptionText(id));
        };
    }
    const f=fixture(75,{fsState:fileState,plugins,responses:{[fallback]:esFallback},configure,testHooks:true});
    const c=f.context;c.ConfigManager.applyData({remLanguage:1,remVoiceLanguage:0});
    assert.equal(c.ConfigManager.remLanguage,6,"the detected native Spanish locale is preferred at boot");
    assert.equal(c.ConfigManager.remVoiceLanguage,0,"voice language remains the player's original selection");
    assert.equal(c.ConfigManager.saves,0,"never save configuration directly");
    const w=new c.Window_Base();w.initialize(0,0,600,200);
    assert.equal(w.convertEscapeCharacters(ref),spanish);
    assert.equal(w.convertEscapeCharacters(choiceRef),esDesc);
    new c.Scene_Title().start();
    await wait(45);
    assert.equal(c.TextManager.remMiscMapText(key),spanish);
    assert.equal(w.convertEscapeCharacters(missingRef),fallback,"only genuinely untranslated prose uses the worker");
    const end=Date.now()+3000;
    while(Date.now()<end&&c.TextManager.remMiscMapText(missing)!==esFallback)await wait(30);
    assert.equal(c.TextManager.remMiscMapText(missing),esFallback);
    assert.ok(f.posts.some(p=>p.text===fallback));
    assert.ok(!f.posts.some(p=>p.text===original||p.text===spanish||p.text===desc||p.text===esDesc||/REM_(?:MAP|DESC)\[/.test(p.text)),
        "native translated catalog entries and executable lookup keys must not be sent to the model");
    assert.equal(JSON.stringify(catalog),originalCatalog);
    assert.ok(c.TextManager.isSpanish);
    c.ConfigManager.remLanguage=1;
    new c.Scene_Title().start();
    assert.equal(c.ConfigManager.remLanguage,1,"an explicit later language choice is not reset in the same session");
    const partial={files:Object.assign({},fileState.files),dirs:Object.assign({},fileState.dirs)};
    delete partial.files[path.join(pics,"difficulty_hard2_SP.png")];
    const g=fixture(1,{fsState:partial,plugins,configure,disconnected:true});
    g.context.ConfigManager.applyData({remLanguage:1,remVoiceLanguage:0});
    assert.equal(g.context.ConfigManager.remLanguage,1,"missing native picture prevents automatic language switch");
    const h=fixture(1,{fsState:{files:Object.assign({},fileState.files),dirs:Object.assign({},fileState.dirs)},plugins:[],configure,disconnected:true});
    h.context.ConfigManager.applyData({remLanguage:1,remVoiceLanguage:0});
    assert.equal(h.context.ConfigManager.remLanguage,1,"unrelated games never use this adapter");
}
async function testR14VisuQuestAndStatusMetadata(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","data");
    const folder=path.join("/tmp","servidor-qa-juego-日本語","IA Traductora",".local","Rpg","cache");
    const hud=path.join(data,"plugin");
    const state={files:{},dirs:{[data]:true,[folder]:true,[hud]:true}};
    const bio="Alice studies plants and teaches the local children.";
    const esBio="Alice estudia plantas y enseña a los niños del lugar.";
    const desc="Get through the start of the new festival.";
    const esDesc="Supera el comienzo del nuevo festival.";
    const objective="Speak to Alice",other="Look at the old fountain.",esOther="Mira la fuente antigua.";
    const gab="The garden is open.",esGab="El jardín está abierto.";
    const hudText="The flowers are ready.",esHud="Las flores están listas.";
    const variable="The library is closed.",esVariable="La biblioteca está cerrada.";
    const note="<Menu Portrait: portraitA>\n<StatusImageVariable: 37, imageA>\n<StatusText: "+bio+">\n<StatusTextVariable: 42>";
    const actors=[null,{id:1,name:"Alice",nickname:"",profile:"",note,meta:{StatusText:" "+bio,StatusTextVariable:" 42"}}];
    const quest={ "Key:str":"QuestKeyInternal","Title:str":"\\i[87]Prologue","Difficulty:str":"Easy","From:str":"Alice","Location:str":"",
        "Description:arrayjson":JSON.stringify([JSON.stringify(desc)]),
        "Objectives:arrayjson":JSON.stringify([JSON.stringify(objective),JSON.stringify(other)]),
        "VisibleObjectives:arraynum":"[1,2]","OnLoadQuestJS:func":"\"Do not translate this executable field.\"",
        "Rewards:arrayjson":"[]","Subtext:arrayjson":"[]","Quotes:arrayjson":"[]" };
    const qparams={"General:struct":JSON.stringify({"KnownQuests:arraystr":"[\"QuestKeyInternal\"]","TrackedQuest:str":"QuestKeyInternal",
        "LogFmt:json":JSON.stringify("[[Title]]\nDescription:\n[[Description]]"),"ButtonAssistPageUpDown:str":"Scroll Up/Down"}),
        "Categories:arraystruct":JSON.stringify([JSON.stringify({"CategoryName:str":"Character Quests",
            "Quests:arraystruct":JSON.stringify([JSON.stringify(quest)])})])};
    const plugins=[{name:"VisuMZ_2_QuestSystem",status:true,parameters:qparams},
        {name:"StatusMenuTesting3",status:true,parameters:{}},
        {name:"VisuMZ_4_GabWindow",status:true,parameters:{}},
        {name:"SRD_HUDMakerUltra",status:true,parameters:{}}];
    const cmd=["VisuMZ_4_GabWindow","GabTextOnly","",{ "Text:json":JSON.stringify(gab),"ForceGab:eval":"false","Override:struct":"{}" }];
    const originalPlugins=JSON.stringify(plugins),originalActors=JSON.stringify(actors),originalCmd=JSON.stringify(cmd);
    state.files[path.join(data,"System.json")]=JSON.stringify({locale:"en_US",startMapId:1});
    state.files[path.join(data,"Actors.json")]=JSON.stringify(actors);
    state.files[path.join(data,"Map001.json")]=JSON.stringify({events:[null,{pages:[{list:[
        {code:122,parameters:[42,42,0,4,JSON.stringify(variable)]},{code:357,parameters:cmd}]}]}]});
    state.files[path.join(hud,"UltraHUD.json")]=JSON.stringify({Data:[{HUD:[{Children:[
        {TextData:{Text:{Type:0,Text:hudText}},Children:[]},
        {TextData:{Text:{Type:5,Text:"Do not send dynamic code."}},Children:[]}
    ]}]}]});
    state.files[path.join(folder,"translations-ja-en-es-v2.jsonl")]=JSON.stringify({
        schema:"ia-traductora-cache-v2",source:"en",original:"start",translated:"iniciar",composed:false})+"\n";
    const f=fixture(80,{mz:true,fsState:state,plugins,testHooks:true,responses:{
        [bio]:esBio,[desc]:esDesc,[other]:esOther,[gab]:esGab,[hudText]:esHud,[variable]:esVariable},configure(c){
            c.$dataActors=actors;c.$dataSystem={locale:"en_US"};
            function Vars(){this.values={42:variable};}
            Vars.prototype.value=function(id){return this.values[id];};
            c.Game_Variables=Vars;c.$gameVariables=new Vars();
            function Scene_Status(){this.calls=0;}
            Scene_Status.prototype.create=function(){
                this.calls++;this.note=c.$dataActors[1].note;
                this.meta=c.$dataActors[1].meta.StatusText;
                this.variable=c.$gameVariables.value(42);
                this.bitmap=new c.Bitmap(800,450);this.bitmap.drawText("Age: 27",0,0,400,30);
                this.bitmap.drawText("Alice",0,40,400,30);
            };
            c.Scene_Status=Scene_Status;
            c.SceneManager.changeScene=function(){this._scene=this._nextScene;this._nextScene=null;this._scene.create();};
            function Interpreter(){this.calls=[];}
            Interpreter.prototype.command357=function(params){this.calls.push(params);return true;};
            c.Game_Interpreter=Interpreter;
        }});
    const c=f.context;
    new c.Scene_Title().start();
    const until=async predicate=>{const deadline=Date.now()+5000;while(Date.now()<deadline){if(predicate())return;await wait(30);}assert.fail("R14: timed out waiting for native presentation");};
    await until(()=>c.window.__IA_TRADUCTORA_TEST__.done());
    const required=[bio,desc,other,gab,hudText,variable];
    const deadline=Date.now()+5000;
    while(Date.now()<deadline&&!required.every(raw=>f.posts.some(p=>p.text===raw)))await wait(30);
    assert.deepEqual(required.filter(raw=>!f.posts.some(p=>p.text===raw)),[],
        "R14: every proven status, quest, HUD and gab field is inventoried, including initial-map assignments before Actors.json");
    await wait(180);
    const status=new c.Scene_Status();c.SceneManager._nextScene=status;
    await until(()=>{if(c.SceneManager._nextScene)c.SceneManager.changeScene();return status.calls===1;});
    assert.ok(status.note.includes("<StatusText: "+esBio+">"));
    assert.equal(status.meta," "+esBio);
    assert.equal(status.variable,esVariable);
    assert.equal(status.bitmap.ops[0].text,"Edad: 27");assert.equal(status.bitmap.ops[1].text,"Alice");
    assert.equal(c.$dataActors,actors);assert.equal(JSON.stringify(actors),originalActors);
    assert.equal(c.$gameVariables.value(42),variable,"game variable never rewritten");
    function Scene_Quest(){}
    c.SceneManager._scene=new Scene_Quest();
    function Window_QuestLog(){this.initialize(new c.Rectangle(0,0,600,500));this.parent=c.SceneManager._scene;}
    Window_QuestLog.prototype=Object.create(c.Window_Base.prototype);
    Window_QuestLog.prototype.constructor=Window_QuestLog;
    const win=new Window_QuestLog();
    const raw="\\i[87]Prologue\n\\c[4]From:\\c[0] Alice\n\\c[4]Description:\\c[0]\n"+desc+
        "\n\\c[4]Objectives:\\c[0]\n◎"+objective+"\n◎"+other+"\n\\c[4]Rewards:\\c[0]";
    await until(()=>{win.drawTextEx(raw,0,0);return win.lastTextEx.includes(esDesc)&&win.lastTextEx.includes(esOther);});
    assert.ok(win.lastTextEx.includes("\\i[87]Prólogo"));
    assert.ok(win.lastTextEx.includes("◎Habla con Alice"));
    assert.ok(win.lastTextEx.includes("\\c[4]De:\\c[0] Alice"));
    assert.ok(win.lastTextEx.includes("\\c[4]Objetivos:\\c[0]"));
    win.drawText("Z/X:Scroll Up/Down",0,0,300);assert.equal(win.lastText,"Z/X:Desplazar arriba/abajo");
    const bitmap=new c.Bitmap(500,100);bitmap.drawText("start",0,0,400,30);
    assert.equal(bitmap.lastText,"start","the cached isolated word must not corrupt a quest sentence");
    const it=new c.Game_Interpreter();
    await until(()=>it.command357(cmd)===true);
    assert.equal(it.calls.length,1);assert.equal(JSON.parse(it.calls[0][3]["Text:json"]),esGab);
    assert.equal(it.calls[0][3]["ForceGab:eval"],"false");assert.equal(JSON.stringify(cmd),originalCmd);
    c.SceneManager._scene=new c.Scene_Map();
    const drawHud=(v)=>vm.runInNewContext("b.drawText(v,0,0,400,30)",{b:bitmap,v},{filename:"SRD_HUDMakerUltra.js"});
    drawHud("Day 3");assert.equal(bitmap.lastText,"Día 3");
    drawHud(hudText);assert.equal(bitmap.lastText,esHud);
    assert.ok(!f.posts.some(p=>/QuestKeyInternal|Do not translate this executable field|Do not send dynamic code|^Alice$/.test(p.text)));
    assert.equal(JSON.stringify(plugins),originalPlugins);
}
async function testR13PhonePrivateInterpreterAndPictureText(){
    const speech="I will meet you at the station.",answer="That is a lovely photograph.",
        choice="Cute profile photo",notice="Look at the clock in the upper left corner.";
    const expectedSpeech="Te encontraré en la estación.",expectedAnswer="Es una fotografía preciosa.",
        expectedChoice="Foto de perfil bonita",expectedNotice="Mira el reloj de la esquina superior izquierda.";
    const list=[
        {code:101,parameters:["",0,0,2,"Alice"]},{code:401,parameters:[speech]},
        {code:355,parameters:['this.setAnswerForChoice(3, "'+answer+'");']},
        {code:102,parameters:[[choice],0,0,2,0]},
        {code:101,parameters:["",0,0,2,"Alice"]},{code:401,parameters:["Hehe"]},
        {code:355,parameters:["this.phoneSetWaitFor('Alice');"]},
        {code:355,parameters:['Phone.AddMessage("IconA", "Alice", 4, true);']},{code:0,parameters:[]}
    ];
    const picture=["Hendrix_Pictures_UI_Creator","ShowText","Show Text Window",
        {id:"Tutorial",text:notice,sizePosition:"300,200,0,0",textSettings:'{"align":"center"}',update:"false",textVocabulary:""}];
    const data=path.join("/tmp","servidor-qa-juego-日本語","data");
    const state={files:{},dirs:{[data]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1,locale:"en_US"});
    state.files[path.join(data,"Map001.json")]=JSON.stringify({events:[null,{pages:[{list:list.concat([{code:357,parameters:picture}])}]}]});
    const saved=JSON.stringify(list),pictureSaved=JSON.stringify(picture);
    const f=fixture(90,{mz:true,fsState:state,responses:{[speech]:expectedSpeech,[answer]:expectedAnswer,[choice]:expectedChoice,[notice]:expectedNotice},
        plugins:[{name:"PKD_PhoneMenu",status:true,parameters:{}},{name:"Hendrix_Pictures_UI_Creator",status:true,parameters:{}}],configure(c){
            function Base(){this.calls=[];this._index=0;}
            Base.prototype.setup=function(list){this._list=list;this._index=0;};
            Base.prototype.command357=function(params){this.calls.push(params);return true;};
            Base.prototype.executeCommand=function(){
                const cmd=this._list[this._index];this._params=cmd.parameters;
                if(cmd.code===357){if(!this.command357(cmd.parameters))return false;}
                else if(cmd.code===101)this.command101();
                else if(cmd.code===102)this.calls.push({choices:cmd.parameters[0].slice(),branch:cmd.parameters[1]});
                else this.calls.push(cmd.parameters[0]);
                this._index++;return true;
            };
            function PhoneInterpreter(){Base.call(this);}
            PhoneInterpreter.prototype=Object.create(Base.prototype);
            PhoneInterpreter.prototype.constructor=PhoneInterpreter;
            PhoneInterpreter.prototype.phoneSetWaitFor=function(){};
            PhoneInterpreter.prototype.setAnswerForChoice=function(){};
            PhoneInterpreter.prototype.command101=function(){
                const speaker=this._params[4],text=[];
                while(this._list[this._index+1]&&this._list[this._index+1].code===401)
                    text.push(this._list[++this._index].parameters[0]);
                this.calls.push({speaker,text:text.join("\n")});
            };
            c.Game_Interpreter=Base;c.PhoneInterpreter=PhoneInterpreter;c.$dataSystem={locale:"en_US"};
        }});
    await wait(30);const c=f.context;c.SceneManager._scene=new c.Scene_Map();
    const it=new c.PhoneInterpreter();it.setup(list);
    assert.equal(it.executeCommand(),false,"cold phone message waits before private native dispatch");
    assert.equal(it.calls.length,0);
    const run=async expectedIndex=>{
        const end=Date.now()+3500;
        while(it._index<expectedIndex&&Date.now()<end){it.executeCommand();await wait(20);}
        assert.equal(it._index,expectedIndex);
    };
    await run(2);
    assert.equal(it.calls[0].speaker,"Alice");
    assert.equal(it.calls[0].text,expectedSpeech,"private phone first paint uses Spanish even without Game_Message");
    await run(3);assert.equal(it.calls[1],'this.setAnswerForChoice(3, "'+expectedAnswer+'");');
    await run(4);assert.equal(it.calls[2].choices[0],expectedChoice);assert.equal(it.calls[2].branch,0);
    await run(6);assert.equal(it.calls[3].text,"Jeje");
    await run(8);assert.equal(it.calls[4],"this.phoneSetWaitFor('Alice');");
    assert.equal(it.calls[5],'Phone.AddMessage("IconA", "Alice", 4, true);');
    assert.equal(it._list,list);assert.equal(JSON.stringify(list),saved);
    assert.ok(!f.posts.some(p=>p.text==="Alice"||/Phone\.AddMessage|setAnswerForChoice|IconA/.test(p.text)));
    const native=new c.Game_Interpreter();native.setup([{code:357,parameters:picture}]);
    const end=Date.now()+3500;while(!native.calls.length&&Date.now()<end){native.executeCommand();await wait(30);}
    assert.equal(native.calls.length,1);assert.equal(native.calls[0][3].text,expectedNotice);
    for(const k of Object.keys(picture[3]))if(k!=="text")assert.equal(native.calls[0][3][k],picture[3][k]);
    assert.equal(JSON.stringify(picture),pictureSaved);
    const dynamic=picture.slice();dynamic[3]=Object.assign({},picture[3],{text:"v[0142]"});
    native.setup([{code:357,parameters:dynamic}]);native.executeCommand();
    assert.equal(native.calls[1][3].text,"v[0142]");
    assert.ok(!f.posts.some(p=>p.text==="v[0142]"));
}
async function testR12NotificationFirstAppearance(){
    const raw="\\C[2]新しい鍵を入手しました。\\C[0]",plain="新しい鍵を入手しました。";
    const es="Has obtenido una llave nueva.",expected="\\C[2]"+es+"\\C[0]";
    const params=["LL_InfoPopupWIndow","showMessage","",{messageText:raw,showCount:"180",windowX:"auto",windowY:"20",windowBackground:"0"}];
    const data=path.join("/tmp","servidor-qa-juego-日本語","data");
    const state={files:{},dirs:{[data]:true}};
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1,locale:"ja_JP"});
    state.files[path.join(data,"Map001.json")]=JSON.stringify({events:[null,{pages:[{list:[{code:357,parameters:params}]}]}]});
    const untouched=JSON.stringify(params);
    const f=fixture(90,{mz:true,fsState:state,responses:{[plain]:es},
        plugins:[{name:"LL_InfoPopupWIndow",status:true,parameters:{}}],configure(c){
            function Interpreter(){this._list=[{code:357,parameters:params}];this._index=0;this.calls=[];}
            Interpreter.prototype.setup=function(){};
            Interpreter.prototype.command357=function(p){this.calls.push(p);return true;};
            c.Game_Interpreter=Interpreter;
        }});
    await wait(25);const c=f.context;c.SceneManager._scene=new c.Scene_Map();
    const it=new c.Game_Interpreter();
    assert.equal(it.command357(params),false,"the original notification command must not execute before translation");
    assert.equal(it.calls.length,0);
    const end=Date.now()+3000;
    while(!it.calls.length&&Date.now()<end){await wait(30);it.command357(params);}
    assert.equal(it.calls.length,1,"native popup command executes once, not repeated");
    assert.equal(it.calls[0][3].messageText,expected);
    for(const k of Object.keys(params[3]))if(k!=="messageText")assert.equal(it.calls[0][3][k],params[3][k]);
    assert.equal(JSON.stringify(params),untouched);
    const hide=["LL_InfoPopupWIndow","hideMessage","",{}];assert.equal(it.command357(hide),true);
    assert.equal(it.calls[1],hide);
}
async function testR12NativeSpeakerPresentation(){
    const data=path.join("/tmp","servidor-qa-juego-日本語","data");
    const state={files:{},dirs:{[data]:true}};
    const role="お母さん",name="春香",reading="春香（はるか）です。";
    state.files[path.join(data,"System.json")]=JSON.stringify({startMapId:1,locale:"ja_JP"});
    state.files[path.join(data,"Map001.json")]=JSON.stringify({events:[null,{pages:[{list:[
        {code:101,parameters:["",0,0,2,role]},{code:401,parameters:[reading]},
        {code:101,parameters:["",0,0,2,name]},{code:401,parameters:["こんにちは。"]}
    ]}]}]});
    const f=fixture(5,{mz:true,fsState:state,testHooks:true,configure(c){
        function NameBox(){this.initialize(new c.Rectangle(0,0,300,60));}
        NameBox.prototype=Object.create(c.Window_Base.prototype);
        NameBox.prototype.setName=function(v){this._name=v;this.refresh();};
        NameBox.prototype.refresh=function(){this.drawText(this._name,0,0,200);};
        NameBox.prototype.windowWidth=function(){return this._name.length*10;};
        c.Window_NameBox=NameBox;
        c.Game_Message.prototype.setSpeakerName=function(v){this._speakerName=v;};
    }});
    const c=f.context;
    new c.Scene_Title().start();
    const end=Date.now()+4000;
    while(!c.window.__IA_TRADUCTORA_TEST__.done()&&Date.now()<end)await wait(30);
    await wait(60);
    const box=new c.Window_NameBox();
    c.$gameMessage.setSpeakerName(role);box.setName(role);
    assert.equal(box.lastText,"Mamá");assert.equal(box._name,role);
    assert.equal(c.$gameMessage._speakerName,role);
    box.setName(name);assert.equal(box.lastText,"Haruka");assert.equal(box._name,name);
    assert.equal(box.windowWidth(),60);
    box.setName("\\N[1]");assert.equal(box.lastText,"\\N[1]");
    box.setName("未確認");assert.equal(box.lastText,"未確認","unknown name is not guessed");
}
async function testR11NevDialogUiAlignmentLateRedraw(){
    for(const [code,mode] of [["\\AC","center"],["\\AR","right"],["\\AL","left"],["\\ALIGN[center]","center"]]){
        const body="We are ready to open the gate.";
        const spanish="Estamos listos para abrir la puerta.";
        const raw=code+" "+body;
        const f=fixture(55,{mz:true,responses:{[body]:spanish},nativeWait:true,nativePaint:true,
            configure:function(c){c.Window_Message.prototype._textAlignment=mode;}});
        await wait(30);
        const c=f.context;c.SceneManager._scene=new c.Scene_Map();
        const m=new c.Window_Message();f.$gameMessage._texts=[raw];m.startMessage();
        assert.equal(m.contents._iaOwnerWindow,m,"the native message owns its Bitmap without a fixture workaround");
        assert.equal(m.originalStarts,1);
        m.finishPage();
        const deadline=Date.now()+3000;
        while(Date.now()<deadline&&!m.contents.ops.some(op=>op.text==="Estamos")){await wait(40);m.update();}
        assert.ok(f.posts.some(p=>p.text===body),"only prose must be sent; alignment is protected");
        const lines=m.contents.ops.filter(op=>op.text!=="FACE");
        assert.equal(lines.map(op=>op.text).join(" "),spanish,"the complete Spanish message is drawn in native word runs");
        assert.ok(!lines.some(op=>op.text.includes(body)||op.text.includes(code)));
        assert.equal(m.originalStarts,1,"no repeated scene or message start");
        assert.equal(f.$gameMessage.allText(),raw,"game message remains original during late repaint");
        assert.ok(m.contents.ops.some(op=>op.text==="FACE"),"portrait is preserved");
        const natural=spanish.length*12;
        const expected=168+(mode==="left"?0:Math.floor((m.contents.width-168-natural)/(mode==="center"?2:1)));
        assert.equal(lines[0].x,expected,"Spanish is aligned using its own measured width");
    }
}

async function testR11QteBitmapFirstPaint(){
    const responses={
        "POPUP":"AVISO",
        "Click each target before its ring closes in. A wrong click":"Haz clic en cada objetivo antes de que se cierre su anillo. Un clic incorrecto",
        "means instant fail.":"significa un fallo inmediato.",
        "Press any key or click to start":"Pulsa cualquier tecla o haz clic para comenzar.",
        "Shop":"Tienda"
    };
    const originals=Object.keys(responses);
    const expected=Object.keys(responses).map(function(k){return responses[k];});
    const f=fixture(35,{responses:responses});
    await wait(30);
    const c=f.context;c.SceneManager._scene=new c.Scene_Map();
    const b=new c.Bitmap(800,220);
    b.drawText("POPUP",20,0,760,36,"center");
    b.drawText("Click each target before its ring closes in. A wrong click",20,45,760,36,"center");
    b.drawText("means instant fail.",20,85,760,36,"center");
    b.drawText("Press any key or click to start",20,150,760,36,"center");
    const cleared=new c.Bitmap(200,40);
    cleared.drawText("Shop",0,0,200,40);
    cleared.clearRect(0,0,200,40);
    const deadline=Date.now()+4500;
    while(Date.now()<deadline&&!expected.slice(0,4).every(function(v){return b.ops.some(function(op){return op.text===v;});}))
        await wait(25);
    assert.ok(expected.slice(0,4).every(function(v){return b.ops.some(function(op){return op.text===v;});}),
        "one-shot QTE Bitmap text must repaint in the first tutorial screen without reopening it");
    assert.ok(!b.ops.some(function(op){return originals.slice(0,4).indexOf(op.text)>=0;}),
        "the original QTE English labels and instructions must be replaced");
    await wait(120);
    assert.ok(!cleared.ops.some(function(op){return op.text==="Tienda";}),
        "clearing a custom bitmap must cancel its pending translation repaint");
}


async function testR11DirectCanvasAtomicFirstView(){
    const responses={"Press any key to start":"Pulsa una tecla para empezar.","Click to continue":"Haz clic para continuar."};
    function install(c){
        Object.defineProperty(c.Bitmap.prototype,"context",{configurable:true,get:function(){
            if(this._context)return this._context;
            const b=this,w=b.width,h=b.height;
            let pixels=new Uint8ClampedArray(w*h*4);
            const ctx={font:"12px GameFont",textAlign:"left",textBaseline:"top",
                fillStyle:"#ffffff",strokeStyle:"#000000",globalCompositeOperation:"source-over",
                globalAlpha:1,save(){},restore(){},getTransform(){return {a:1,b:0,c:0,d:1,e:0,f:0};},
                measureText(s){return {width:String(s).length*2};},
                getImageData(){return {width:w,height:h,data:new Uint8ClampedArray(pixels)};},
                putImageData(im){pixels=new Uint8ClampedArray(im.data);},
                clearRect(){pixels.fill(0);},
                mark(x,y){pixels[(y*w+x)*4]=231;pixels[(y*w+x)*4+3]=255;}};
            function paint(t,x,y,stroke){
                Array.from(String(t)).forEach((ch,i)=>{
                    const px=x+i,py=y+(stroke?0:1);if(px>=w||py>=h)return;
                    const at=(py*w+px)*4;pixels[at]=ch.charCodeAt(0)%251;pixels[at+1]=stroke?20:40;pixels[at+3]=255;
                });
            }
            ctx.strokeText=(t,x,y)=>paint(t,x,y,true);
            ctx.fillText=(t,x,y)=>paint(t,x,y,false);
            b._context=ctx;return ctx;
        }});
    }
    const f=fixture(55,{mz:true,responses,plugins:[{name:"NEV_GameHub",status:true,parameters:{}}],configure:install});
    await wait(35);
    const c=f.context;c.SceneManager._scene=new c.Scene_Map();
    const draw=(b,text,y)=>vm.runInNewContext("b.context.strokeText(text,3,y,90);b.context.fillText(text,3,y,90);",{b,text,y},{filename:"NEV_GameHub.js"});
    const b=new c.Bitmap(120,50);b.context.mark(1,1);
    draw(b,"Press any key to start",5);draw(b,"Click to continue",20);
    const expected=new c.Bitmap(120,50);expected.context.mark(1,1);
    draw(expected,responses["Press any key to start"],5);draw(expected,responses["Click to continue"],20);
    const until=async pred=>{const end=Date.now()+3500;while(!pred()&&Date.now()<end)await wait(40);assert.ok(pred());};
    const bytes=x=>Buffer.from(x.context.getImageData().data);
    await until(()=>bytes(b).equals(bytes(expected)));
    assert.ok(f.posts.some(p=>p.text==="Press any key to start")&&f.posts.some(p=>p.text==="Click to continue"));
    assert.ok(bytes(b).equals(bytes(expected)),"both outline and fill are replaced on the original bitmap; background remains");
    const stale=fixture(80,{mz:true,responses,plugins:[{name:"NEV_GameHub",status:true,parameters:{}}],configure:install});
    await wait(30);const sc=stale.context;sc.SceneManager._scene=new sc.Scene_Map();
    const removed=new sc.Bitmap(120,50);draw(removed,"Press any key to start",5);removed.context.clearRect();
    const reused=new sc.Bitmap(120,50);draw(reused,"Click to continue",5);reused.context.mark(110,40);
    const old=bytes(reused);
    await wait(350);
    assert.ok(bytes(removed).every(x=>x===0),"a cleared canvas never gets old text back");
    assert.ok(bytes(reused).equals(old),"any intervening paint prevents stale pixel replacement");
    const unchanged=new c.Bitmap(120,50);draw(unchanged,"12345",5);draw(unchanged,"Aldren",20);
    assert.ok(!f.posts.some(p=>p.text==="12345"||p.text==="Aldren"),"numbers and arbitrary names are not translated");
}

async function testR8GeneralDisplaySurfaces(){
    const root=path.join("/tmp","servidor-qa-juego-日本語"),dir=path.join(root,"data");
    const profile="Sophia is my \\N[7], a woman of breathtaking beauty and elegance.\nShe has always been incredibly kind, She holds herself to an impossibly high standard, always perfectly composed.";
    const ben="Ben is the steady one in Sophia's life. He's caring, playful, and a little too proud of how good his Sophia looks. Sometimes he pushes the fun further than he realizes. He trusts Sophia completely. Whether that trust is a safety net or a blind spot depends on her choices.";
    const floating="Shopia: Okay, okay! Stop before my head gets too big to fit through the door♡\\pop[-1]";
    const choices=[
        "Accept \\b[2]","Let me Out!! \\b[4]","Shop","Read Me","Change Relationship",
        "Change \"Sophia\" Name","Text Skip Speed setting","Tell Me About Yourself \\b[2]",
        "Never Mind","Romantic Idea <If Love Capped> \\b[2]",
        "Naughty Idea <If Corrupt Capped> \\b[2]","Exposing Idea <If Exhibitions Capped> \\b[2]",
        "Dar un cumplido","¿Qué piensas de mí?"
    ];
    const command=(code,...parameters)=>({code,parameters});
    const system={locale:"en_US",startMapId:1,variables:[]};
    const actors=[null,{id:1,name:"Sophia",profile:profile},{id:2,name:"Ben",profile:ben}];
    const list=[command(102,choices),command(401,"One year earlier."),
        command(401,"City Courthouse, Courtroom 4."),command(401,floating)];
    const map={events:[null,{id:1,name:"Test",pages:[{list:list}]}]};
    const common=[null,{id:1,name:"Menu",list:list}];
    const fsState={files:{
        [path.join(dir,"System.json")]:JSON.stringify(system),
        [path.join(dir,"Actors.json")]:JSON.stringify(actors),
        [path.join(dir,"CommonEvents.json")]:JSON.stringify(common),
        [path.join(dir,"Map001.json")]:JSON.stringify(map)
    },dirs:{[dir]:true}};
    const responses={
        "Accept":"Aceptar","Let me Out!!":"¡Déjame salir!","Shop":"Tienda","Read Me":"Léeme",
        "Change Relationship":"Cambiar relación","Change \"Sophia\" Name":"Cambiar nombre de \"Sophia\"",
        "Text Skip Speed setting":"Ajuste de velocidad de omisión de texto",
        "Tell Me About Yourself":"Cuéntame sobre ti","Never Mind":"No importa",
        "Romantic Idea":"Idea romántica","If Love Capped":"Si el amor está al máximo",
        "Naughty Idea":"Idea traviesa","If Corrupt Capped":"Si la corrupción está al máximo",
        "Exposing Idea":"Idea de exhibicionismo","If Exhibitions Capped":"Si el exhibicionismo está al máximo",
        "One year earlier.":"Un año antes.",
        "City Courthouse, Courtroom 4.":"Palacio de justicia de la ciudad, sala 4.",
        "Shopia: Okay, okay! Stop before my head gets too big to fit through the door♡":
            "Shopia: Está bien, está bien. No sigas o mi cabeza no pasará por la puerta♡",
        "Sophia is my":"Sophia es mi",
        ", a woman of breathtaking beauty and elegance.":", una mujer de belleza y elegancia impresionantes.",
        "She has always been incredibly kind, She holds herself to an impossibly high standard, always perfectly composed.":
            "Siempre ha sido increíblemente amable y mantiene un estándar extraordinariamente alto, siempre perfectamente serena.",
        [ben]:"Ben es la persona estable en la vida de Sophia. Es cariñoso, juguetón y está un poco demasiado orgulloso de lo bien que se ve Sophia. A veces lleva las bromas más lejos de lo que imagina. Confía completamente en Sophia. Si esa confianza es una red de seguridad o un punto ciego depende de sus decisiones.",
        "Profile":"Perfil"
    };
    const f=fixture(1,{mz:true,fsState,batch:true,responses,configure(c){
        c.$dataSystem=system;c.$dataActors=actors;c.$dataCommonEvents=common;
        c.$gameActors={actor:id=>({name:()=>id===7?"Stepmom":(actors[id]&&actors[id].name)||"Actor"})};
        const base=c.Window_Base.prototype;
        base.createContents=function(){this.contents=new c.Bitmap(900,400);};
        base.refresh=function(){this.refreshes=(this.refreshes||0)+1;if(this._iaRefreshText)this.drawText(this._iaRefreshText,0,0,700,"left");};
        function ChoiceList(items){
            this._list=items.map((name,ext)=>({name:name,ext:ext,symbol:"choice",enabled:true}));
            this.active=true;this.openness=255;this.painted=[];
        }
        ChoiceList.prototype.drawItem=function(i){this.painted[i]=this._list[i].name;};
        ChoiceList.prototype.redrawItem=function(i){this.drawItem(i);};
        ChoiceList.prototype.update=function(){};
        ChoiceList.prototype.itemRectForText=function(){return {width:900};};
        ChoiceList.prototype.textSizeEx=function(t){return {width:String(t).length*8};};
        c.Window_ChoiceList=ChoiceList;
    }});
    const c=f.context;
    const until=async pred=>{const end=Date.now()+7000;while(!pred()&&Date.now()<end)await wait(25);assert.ok(pred(),"R8 display translation did not become ready");};
    await wait(40);
    await until(()=>["Shop","Read Me","Change Relationship","Text Skip Speed setting",
        "One year earlier.","City Courthouse, Courtroom 4.","Shopia: Okay, okay! Stop before my head gets too big to fit through the door♡"]
        .every(s=>f.posts.some(p=>p.text===s)));
    const messageBody=floating.replace("\\pop[-1]","");
    assert.ok(f.posts.some(p=>p.text===messageBody),"heart punctuation must not suppress English detection");
    assert.ok(!f.posts.some(p=>p.text.indexOf("\\pop[-1]")>=0),"popup positioning control must never reach the model");

    f.$gameMessage.setChoices(choices);
    const choice=new c.Window_ChoiceList(choices);
    const expectedChoices=[
        "Aceptar \\b[2]","¡Déjame salir! \\b[4]","Tienda","Léeme","Cambiar relación",
        "Cambiar nombre de \"Sophia\"","Ajuste de velocidad de omisión de texto",
        "Cuéntame sobre ti \\b[2]","No importa",
        "Idea romántica <Si el amor está al máximo> \\b[2]",
        "Idea traviesa <Si la corrupción está al máximo> \\b[2]",
        "Idea de exhibicionismo <Si el exhibicionismo está al máximo> \\b[2]",
        "Dar un cumplido","¿Qué piensas de mí?"
    ];
    const choiceDeadline=Date.now()+15000;
    let choiceReady=false;
    while(Date.now()<choiceDeadline){
        choices.forEach((_,i)=>choice.drawItem(i));
        if(choice.painted.length===expectedChoices.length&&
           choice.painted.every((value,index)=>value===expectedChoices[index])){
            choiceReady=true;break;
        }
        await wait(25);
    }
    assert.ok(choiceReady,"R8 display translation did not become ready: "+
        JSON.stringify({painted:choice.painted,requests:f.posts.map(p=>p.text)}));
    assert.deepEqual(choice._list.map(item=>item.name),choices,
        "all original choice labels must remain untouched");
    assert.deepEqual(choice._list.map(item=>item.ext),choices.map((_,index)=>index),
        "choice branch indices must remain untouched");

    const profileExpanded=profile.replace("\\N[7]","Stepmom");
    const profileBitmap=new c.Bitmap(900,400);
    await until(()=>{profileBitmap.drawText(profileExpanded,0,0,900,400);return profileBitmap.lastText.indexOf("Sophia es mi Stepmom")===0;});
    const benBitmap=new c.Bitmap(900,400);
    await until(()=>{benBitmap.drawText(ben,0,0,900,400);return benBitmap.lastText.indexOf("Ben es la persona estable")===0;});

    const owner=new c.Window_Base();owner.initialize(new c.Rectangle(0,0,500,100));owner.createContents();
    owner._iaRefreshText="Profile";owner.refresh();
    await until(()=>owner.refreshes>=2&&owner.lastText==="Perfil");

    const mv=fixture(1,{responses:{"Shop":"Tienda"}});
    await wait(30);
    const mvBitmap=new mv.context.Bitmap(200,40);
    mvBitmap.drawText("Shop",0,0,200,40);
    await until(()=>mvBitmap.lastText==="Tienda");
}

(async()=>{
    await testR8GeneralDisplaySurfaces();
    await testR16HexChoicesAndChauPopup();
    await testR15NativeLocaleAndFallback();
    await testR14VisuQuestAndStatusMetadata();
    await testR13PhonePrivateInterpreterAndPictureText();
    await testR12NotificationFirstAppearance();
    await testR12NativeSpeakerPresentation();
    await testR11NevDialogUiAlignmentLateRedraw();
    await testR11QteBitmapFirstPaint();
    await testR11DirectCanvasAtomicFirstView();
    await testR7AuthoredScriptAndPicture();
    await testR7VerifiedVariableSurfaces();
    await testR6FirstViewNativeGate(false);
    await testR6FirstViewNativeGate(true);
    await testR6OfflineDeadlineAndForm();
    await testR9BuiltinNameInputProtected();
    await testR5DynamicNamesAndAuthoredRepetition(false);
    await testR5DynamicNamesAndAuthoredRepetition(true);
    await testR5DynamicNamesAndAuthoredRepetition(false,true);
    await testR5DynamicNamesAndAuthoredRepetition(true,true);
    await testR4NativeTsvMixedControlsAndCoverage(false);
    await testR4NativeTsvMixedControlsAndCoverage(true);
    await testR3TsvStartWithoutWaitingAndWrappedComposite(false);
    await testR3TsvStartWithoutWaitingAndWrappedComposite(true);
    await testExternalTsvLookupAndLatePresentation(false);
    await testExternalTsvLookupAndLatePresentation(true);
    await testMZNativeContractsAndControls();
    await testNameIdentityMigrationAndNameSetupFirstPaint();
    await testPreloadUnvisitedMapsAndBatchesWithoutReadingScripts();
    await testYEPFormattingCodesDoNotHideWords();
    await testSceneRevisitUsesCompletedTranslation();
    await testShortWakeUpLineIsRecognized();
    await testShortWakeUpLineWithActorVariableIsRecognized();
    await testUnresolvedIavraReferencesNeverReachTranslatorOrReuseStaleCache();
    await testIavraExternalJsonCatalogAndKeyFallback();
    await testLargeGamePausesBackgroundPrefetch();
    await testLargeCommonEventsJsonIsParsedIncrementally();
    await testInventoryHasNoFortyThousandTextCeiling();
    await testR3PatchRepairsStandardNoticeAndKeepsColor();
    await testR3P2NoticeVariantsOnFirstNativeDraw();
    await testR4EnglishFormatContextAndStaleCache();
    await testR4InkAndCsvReadOnlyPreload();
    await testR4P2NoStaleLateOverlayAndNoArtificialWait();
    await testR4P2QuestMetadataAndVisibleRefresh();
    await testR4P2PriorityCommonAndInkChoice();
    await testR4P3NativeSafetyAndNames();
    await testR4P3PageAndChoiceSafety();
    await testR4P4ShortTextAndMacroAlias();
    await testR4P4LateIconAndAmount();
    await testR4P4FullQuestTemplateAndAccents();
    await testR4P4AmbientNativeCaption();
    await testR4P5QuestOverrideAndCaptionAlias();
    await testR4P5DynamicNativeCaptionConversion();
    await testR4P5BFormattedMessageBodyReplay();
    await testR4P6GalvRealFactoryContract();
    await testR4P7ExternalSheetPreparesBeforeFirstGame();
    await testR4P7JapanesePrimaryAndLiveChoice();
    await testR4P8CsvVariablesAndPresentation();
    await testR4P9ContinueInventoryAndRestore();
    await testR4P9LateCsvNamedMessage();
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
    await testDirectStartFallbackDoesNotOverwriteNextScene();
    await testOriginalNWJSWithoutBufferFromOrNumberIsInteger();
    await testOldNWJSAndPathFallback();
    await testJapaneseDialogAndF10();
    await testEnglishAndSpanish();
    await testRPGControlsAndNoLateRewrite();
    await testChoiceCacheOnlyAndNoOverwrite();
    await testBoundedMapPrefetchAndPressure();
    console.log("SERVIDOR_V2_MV_NATIVE_FAIL_OPEN_CACHE_PREFETCH_AND_F10_PASS");
})().catch(e=>{console.error(e.stack);process.exitCode=1});
