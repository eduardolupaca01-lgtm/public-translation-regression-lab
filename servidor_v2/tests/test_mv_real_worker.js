"use strict";
// Release gate: installed MV plugin -> real local worker -> native UI state.
// Synthetic game and authored text only; no credentials or model output in logs.
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const cp=require("node:child_process");
const r42Notice=require("./r42_notice_contract.js");

const game=path.resolve(process.argv[2]||"");
const wrapped=path.join(game,"www");
const content=["rpg_core.js","rmmz_core.js"].some(n=>fs.existsSync(path.join(wrapped,"js",n)))?wrapped:game;
const isMZ=fs.existsSync(path.join(content,"js","rmmz_core.js"));
const plugin=path.join(content,"js","plugins","IATraductora.js");
const source=fs.readFileSync(plugin,"utf8");
const intervals=[],children=[];

function Rectangle(x,y,width,height){Object.assign(this,{x,y,width,height});}
function Window_Base(rect){if(isMZ&&rect)this.initialize(rect);}
Window_Base.prototype.initialize=function(x,y,width,height){
    if(isMZ){assert.ok(x instanceof Rectangle,"IA_MZ_RECTANGLE_MISSING");[x,y,width,height]=[x.x,x.y,x.width,x.height];}
    this.x=x;this.y=y;this.width=width;this.height=height;
    this.drawn=[];
    const self=this;
    this.contents={fontSize:12,outlineWidth:1,clear(){self.drawn=[];}};
};
Window_Base.prototype.contentsWidth=function(){return this.width-24;};
Window_Base.prototype.drawText=function(value){this.drawn.push(String(value));};
function Window_NameBox(rect){this.initialize(rect);}
Window_NameBox.prototype=Object.create(Window_Base.prototype);
Window_NameBox.prototype.constructor=Window_NameBox;
Window_NameBox.prototype.setName=function(v){this._name=v;this.refresh();};
Window_NameBox.prototype.refresh=function(){this.drawText(this._name);};
function Window_Message(){this.starts=0;}
Window_Message.prototype.startMessage=function(){this.starts++;this.paintedText=gameMessage.allText();};
Window_Message.prototype.updateWait=function(){return false;};
Window_Message.prototype.canStart=function(){return this.starts===0&&gameMessage.hasText();};
Window_Message.prototype.update=function(){
    if(this.updateWait())return;
    if(this.canStart())this.startMessage();
    else if(!gameMessage.hasText()&&gameMessage._choices.length&&!this.choiceWindow){
        const w=new Window_ChoiceList();
        w._list=gameMessage._choices.map((name,ext)=>({name,symbol:"choice",enabled:true,ext}));
        w._list.forEach((_,i)=>w.drawItem(i));this.choiceWindow=w;
    }
};
function Game_Message(){this._texts=[];this._choices=[];}
Game_Message.prototype.setSpeakerName=function(v){this._speakerName=v;};
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
function Game_Interpreter(){this._list=[];this._index=0;this.calls=[];}
Game_Interpreter.prototype.setup=function(list){this._list=list;this._index=0;};
Game_Interpreter.prototype.command357=function(params){this.calls.push(params);return true;};
const gameMessage=new Game_Message();
const choiceValues=Object.create(null);
function Window_ChoiceList(){
    this.active=true;this.openness=255;this._index=0;
    this._list=[{name:"\\v[61]",symbol:"choice",enabled:true,ext:61}];this.painted=[];
}
Window_ChoiceList.prototype=Object.create(Window_Base.prototype);
Window_ChoiceList.prototype.constructor=Window_ChoiceList;
Window_ChoiceList.prototype.convertEscapeCharacters=function(text){
    return text.replace(/\\v\[(\d+)\]/gi,(_,id)=>choiceValues[id]);
};
Window_ChoiceList.prototype.textWidthEx=function(text){return this.convertEscapeCharacters(text).length*10;};
Window_ChoiceList.prototype.textSizeEx=function(text){return {width:this.convertEscapeCharacters(text).length*10,height:32};};
Window_ChoiceList.prototype.itemLineRect=function(){return {width:800};};
Window_ChoiceList.prototype.drawItem=function(i){this.painted[i]=this.convertEscapeCharacters(this._list[i].name);};
Window_ChoiceList.prototype.redrawItem=function(i){this.drawItem(i);};
Window_ChoiceList.prototype.itemRectForText=function(){return {width:800};};
Window_ChoiceList.prototype.update=function(){};
let keyPressed=false;
const ctx={
    window:{location:{pathname:"/"+path.join(content,"index.html").replace(/\\/g,"/")}},
    Utils:{isNwjs:()=>true,RPGMAKER_NAME:isMZ?"MZ":"MV"},Rectangle,ColorManager:{textColor:i=>"color-"+i},
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
    Window_Base,Window_Message,Game_Message,Game_Interpreter,Scene_Map,Window_ChoiceList,Window_NameBox,
    $gameVariables:{value(id){return choiceValues[id];},setValue(){throw Error("IA_UNEXPECTED_GAME_WRITE");}},
    Graphics:{boxWidth:1280},
    Input:{keyMapper:{},isTriggered(){return keyPressed;}},
    SceneManager:{_scene:null},
    $gameMessage:gameMessage,
    $plugins:[{name:"GALV_TimedMessagePopups",status:true,parameters:{}},{name:"KNS_CsvReader",status:true,parameters:{}},{name:"LL_InfoPopupWIndow",status:isMZ,parameters:{}}]
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
async function runCompressedMZ(){
    assert.ok(isMZ,"IA_R18_COMPRESSED_MZ_REQUIRED");
    const data=path.join(content,"data"),plain=path.join(data,"System.json");
    assert.ok(!fs.existsSync(plain),"IA_R18_PLAINTEXT_FIXTURE_FORBIDDEN");
    const lz=require(path.resolve(process.argv[4])),originals=new Map();
    const registry=fs.readFileSync(path.join(content,"js","plugins.js"),"utf8");
    ctx.$plugins=JSON.parse(registry.slice(registry.indexOf("["),registry.lastIndexOf("]")+1));
    const catalogs={en:{},jp:{}};
    for(const name of fs.readdirSync(data).filter(n=>n.endsWith(".jsono"))){
        const file=path.join(data,name),raw=fs.readFileSync(file,"utf8");
        originals.set(file,raw);
        const match=/^lang_\w+_(en|jp)\.jsono$/.exec(name);
        if(match)Object.assign(catalogs[match[1]],JSON.parse(lz.decompressFromBase64(raw)));
    }
    ctx.LZString=lz;
    ctx.IAVRA={MasterLocalization:{I18N:{language:"en"}}};
    Window_Base.prototype.convertEscapeCharacters=function(raw){
        const table=catalogs[ctx.IAVRA.MasterLocalization.I18N.language]||catalogs.en;
        return raw.replace(/\{([\w.]+)\}/g,(token,key)=>Object.prototype.hasOwnProperty.call(table,key)?table[key]:token);
    };
    Window_ChoiceList.prototype.convertEscapeCharacters=function(raw){
        return Window_Base.prototype.convertEscapeCharacters.call(this,raw);
    };
    Window_Message.prototype.startMessage=function(){
        this.starts++;this.painted=gameMessage.allText();
    };
    vm.runInNewContext(source,ctx,{filename:"IATraductora.js"});
    const scene=new Scene_Map();ctx.SceneManager._scene=scene;scene.createAllWindows();
    keyPressed=true;scene.update();keyPressed=false;
    assert.equal(scene.windows.length,2,"IA_R18_F10_MISSING");
    await until(()=>{
        scene.update();scene.windows[1].refresh();
        return scene.windows[1].drawn.some(v=>v.includes("IA local conectada"));
    },120000,"IA_R18_COMPRESSED_WORKER_NOT_CONNECTED");
    const window=new Window_Base(new Rectangle(0,0,600,200));
    const has=(key,regex)=>regex.test(window.convertEscapeCharacters(key));
    // Prefetch the actual compressed catalog through the installed plugin
    // and the packaged neural worker. No mock translation responses.
    await until(()=>{
        scene.update();return has("{line1}",/linterna|farol|lámpara/i)&&
            has("{choice1}",/abr/i)&&has("{notice1}",/gracias|agradezco|agradecemos|ayuda|asistencia/i);
    },120000,"IA_R18_COMPRESSED_PREFETCH_NO_SPANISH");
    gameMessage._texts=["{line1}"];
    const msg=new Window_Message();msg.update();
    await until(()=>{msg.update();return msg.starts===1;},35000,"IA_R18_COMPRESSED_FIRST_DIALOG_TIMEOUT");
    assert.ok(/linterna|farol|lámpara/i.test(msg.painted)&&/mesa/i.test(msg.painted),"IA_R18_COMPRESSED_DIALOG_EN_FAIL");
    assert.equal(gameMessage.allText(),"{line1}","IA_R18_NATIVE_KEY_CHANGED");
    gameMessage._texts=[];gameMessage.setChoices(["{choice1}"]);
    const choice=new Window_ChoiceList();choice._list=[{name:"{choice1}",symbol:"choice",enabled:true,ext:0}];
    choice.drawItem(0);
    assert.ok(/abr/i.test(choice.painted[0])&&/madera/i.test(choice.painted[0]),"IA_R18_COMPRESSED_CHOICE_FAIL");
    assert.equal(choice._list[0].name,"{choice1}");
    assert.equal(choice._list[0].ext,0);
    const popup=["TSR_MapPopups","text","",{text:"{notice1}",duration:"60",target:"0",color:"2"}];
    const it=new Game_Interpreter(),before=JSON.stringify(popup);it.setup([{code:357,parameters:popup}]);
    await until(()=>it.command357(popup)===true,10000,"IA_R18_COMPRESSED_POPUP_TIMEOUT");
    assert.equal(it.calls.length,1);
    assert.ok(/gracias|agradezco|agradecemos|ayuda|asistencia/i.test(it.calls[0][3].text),"IA_R18_COMPRESSED_POPUP_FAIL");
    assert.equal(JSON.stringify(popup),before);
    for(const k of Object.keys(popup[3]))if(k!=="text")assert.equal(it.calls[0][3][k],popup[3][k]);
    ctx.IAVRA.MasterLocalization.I18N.language="jp";
    await until(()=>{scene.update();return has("{line1}",/puente/i);},120000,"IA_R18_COMPRESSED_JP_PREFETCH_FAIL");
    gameMessage.setChoices([]);gameMessage._texts=["{line1}"];
    const jp=new Window_Message();
    await until(()=>{jp.update();return jp.starts===1;},35000,"IA_R18_COMPRESSED_JP_DIALOG_TIMEOUT");
    assert.ok(/puente/i.test(jp.painted)&&!japanese(jp.painted),"IA_R18_COMPRESSED_JP_DIALOG_FAIL");
    assert.equal(gameMessage.allText(),"{line1}");
    assert.ok(!fs.existsSync(plain),"IA_R18_PLAINTEXT_WAS_CREATED");
    for(const [file,raw] of originals)assert.equal(fs.readFileSync(file,"utf8"),raw,"IA_R18_COMPRESSED_ORIGINAL_CHANGED");
    console.log("SERVIDOR_V2_R18_REAL_OPUS_COMPRESSED_MZ_IAVRA_DIALOG_CHOICE_POPUP_PASS");
}
async function runCteMZ(){
    assert.ok(isMZ,"IA_R20_CTE_MZ_REQUIRED");
    const registry=fs.readFileSync(path.join(content,"js","plugins.js"),"utf8");
    ctx.$plugins=JSON.parse(registry.slice(registry.indexOf("["),registry.lastIndexOf("]")+1));
    ctx.Input.keyMapper={121:"debug",90:"ok"};
    let physicalKey=null;
    ctx.window.addEventListener=(type,cb,capture)=>{if(type==="keydown"&&capture)physicalKey=cb;};
    ctx.window.__IA_TRADUCTORA_TEST_HOOKS__=true;
    Window_Base.prototype.convertEscapeCharacters=function(raw){return raw.replace(/\\/g,"\x1b");};
    Window_ChoiceList.prototype.convertEscapeCharacters=function(raw){return Window_Base.prototype.convertEscapeCharacters.call(this,raw);};
    Window_Message.prototype.startMessage=function(){this.starts++;this.painted=Window_Base.prototype.convertEscapeCharacters.call(this,gameMessage.allText());};
    const scene=new Scene_Map();ctx.SceneManager._scene=scene;
    vm.runInNewContext(source,ctx,{filename:"IATraductora.js"});
    scene.createAllWindows();
    assert.equal(ctx.Input.keyMapper[121],"debug","IA_R20_ORIGINAL_F10_MAPPING_CHANGED");
    ctx.Input.keyMapper={121:"debug",90:"ok"};
    assert.equal(typeof physicalKey,"function");
    physicalKey({key:"F10",preventDefault(){},stopImmediatePropagation(){}});
    assert.ok(scene._iaPanel.visible,"IA_R20_PHYSICAL_F10_NOT_OPEN");
    await until(()=>{
        scene.update();scene._iaPanel.refresh();
        return scene._iaPanel.drawn.some(v=>v.includes("IA local conectada"))&&ctx.window.__IA_TRADUCTORA_TEST__.done();
    },120000,"IA_R20_CTE_WORKER_NOT_CONNECTED");
    assert.ok(ctx.window.__IA_TRADUCTORA_TEST__.inventorySize()>=1200,"IA_R20_CTE_LARGE_INVENTORY_MISSING");
    // No draw call before this assertion. The worker must process missing
    // priority catalog text while the active scene is a real map fixture.
    await until(()=>{
        scene.update();scene._iaPanel.refresh();
        return scene._iaPanel.drawn.some(v=>/Recibidas: [1-9]\d*/.test(v));
    },120000,"IA_R20_CTE_PREFETCH_STARVED");
    const win=new Window_Base(new Rectangle(0,0,600,200));
    const raw="The lantern is on the table.";
    await until(()=>/linterna|farol|lámpara/i.test(win.convertEscapeCharacters(raw)),120000,"IA_R20_CTE_NEURAL_TEXT_MISSING");
    gameMessage._texts=[raw];const msg=new Window_Message();
    msg.update();await until(()=>{msg.update();return msg.starts===1;},15000,"IA_R20_CTE_DIALOG_TIMEOUT");
    assert.ok(/linterna|farol|lámpara/i.test(msg.painted)&&/mesa/i.test(msg.painted),"IA_R20_CTE_DIALOG_NOT_SPANISH");
    assert.equal(gameMessage.allText(),raw);
    gameMessage.setChoices(["Open the wooden gate.","Wait here."]);
    const choice=new Window_ChoiceList();
    choice._list=gameMessage._choices.map((name,i)=>({name,ext:i,symbol:"choice",enabled:i===0}));
    choice._list.forEach((_,i)=>choice.drawItem(i));
    assert.equal(choice.painted[0],"Abre la puerta de madera.");
    assert.equal(choice.painted[1],"Espera aquí.");
    assert.equal(choice._list[1].ext,1);assert.equal(choice._list[1].enabled,false);
    assert.equal(choice._list[0].name,"Open the wooden gate.");
    assert.equal(win.convertEscapeCharacters("NEW [A lost lantern] OBJECTIVE"),"NUEVO OBJETIVO DE [Un farol perdido]");
    assert.equal(win.convertEscapeCharacters("Find the lost key."),"Encuentra la llave perdida.");
    physicalKey({key:"F10",preventDefault(){},stopImmediatePropagation(){}});
    assert.equal(scene._iaPanel.visible,false);
    console.log("SERVIDOR_V2_R20_REAL_OPUS_CTE_F10_LARGE_INVENTORY_DIALOG_CHOICE_QUEST_PASS");
}
async function runSolData(){
    const sol=require("./soldata_fixture.js"),data=path.join(content,"data"),calls=[];
    assert.ok(!isMZ&&!fs.existsSync(path.join(data,"System.json")),"IA_SOL_EXPECT_OPAQUE_MV");
    const originals=new Map();
    for(const n of fs.readdirSync(data).filter(n=>n.endsWith(".soldata")||n==="message_data.json"))
        originals.set(n,fs.readFileSync(path.join(data,n)));
    ctx.XMLHttpRequest=sol.loader(calls,new Set());
    ctx.window.__IA_TRADUCTORA_TEST_HOOKS__=true;
    vm.runInNewContext(source,ctx,{filename:"IATraductora.js"});
    const scene=new Scene_Map();ctx.SceneManager._scene=scene;scene.createAllWindows();
    const qa=ctx.window.__IA_TRADUCTORA_TEST__;
    await until(()=>{scene.update();return qa.done();},30000,"IA_SOL_INVENTORY_TIMEOUT");
    assert.ok(qa.soldata().detected&&qa.soldata().read===qa.soldata().total&&qa.soldata().unavailable===0,"IA_SOL_INVENTORY_INCOMPLETE");
    assert.ok(calls.includes("Map369.json")&&calls.includes("Quests.json")&&calls.includes("Achievements.json"),"IA_SOL_REMOTE_MAP_OR_TYPED_FIELDS_MISSING");
    const win=new Window_Base();win.initialize(0,0,600,200);
    // Native window draw uses the same OPUS/cache as dialogue. Require
    // actual Spanish from the installed frozen worker, not the loader shim.
    await until(()=>{
        scene.update();win.drawText("Please open the window.",0,0,600,"left");
        return /ventana/i.test(win.drawn[win.drawn.length-1]);
    },120000,"IA_SOL_REAL_QUEST_TIMEOUT");
    await until(()=>{
        win.drawText("Thank you for your help.",0,0,600,"left");
        return /gracias|ayuda|agradez/i.test(win.drawn[win.drawn.length-1])&&win.drawn[win.drawn.length-1]!=="Thank you for your help.";
    },120000,"IA_SOL_REAL_PHONE_TIMEOUT");
    await until(()=>{
        gameMessage._texts=["橋を渡ってください。"];new Window_Message().startMessage();
        return /puente/i.test(gameMessage.allText())&&!japanese(gameMessage.allText());
    },120000,"IA_SOL_REAL_UNVISITED_MAP_TIMEOUT");
    for(const [n,before] of originals)assert.deepEqual(fs.readFileSync(path.join(data,n)),before,"IA_SOL_ORIGINAL_CHANGED");
    assert.ok(!fs.existsSync(path.join(data,"System.json")),"IA_SOL_PLAINTEXT_CREATED");
    console.log("IA_SOLDATA_SIMULATED_NATIVE_LOADER_REAL_OPUS_QUEST_PHONE_MAP_PASS");
}
async function run(){
    if(process.argv[3]==="--soldata")return runSolData();
    if(process.argv[3]==="--cte")return runCteMZ();
    if(process.argv[3]==="--por")return runCompressedMZ();
    // This is the CI-created synthetic acceptance game, not a user's game.
    const root=path.join(content,"csv"),sheet=path.join(root,"sheet.csv");
    const csvMessage="\\c[2]The lantern is on the table.\\I[17]",csvChoice="Open the wooden gate";
    const csvJa="橋を渡ってください。";
    const cells=[["","Script","日本語","英語","スペイン語","",""],["$map99","","","","","",""],["$event1","","","","","",""],["$page1","","","","","",""],
        ["$text1","","",csvMessage,"","",""],["$text2","","",csvChoice,"","",""],["$text3","",csvJa,"","","",""],
        ["$text4","$v[5] = 9","","if(s[10]) Internal event condition","","",""]];
    const csvRaw=cells.map(row=>row.map(v=>'"'+v.replace(/"/g,'""')+'"').join(",")).join("\r\n")+"\r\n";
    fs.mkdirSync(root,{recursive:true});fs.writeFileSync(sheet,csvRaw,"utf8");
    const questDir=path.join(content,"quest"),questFile=path.join(questDir,"fixture.txt");
    const questRaw="Title: Find the missing key.\n- Please open the window.\n";
    fs.mkdirSync(questDir,{recursive:true});fs.writeFileSync(questFile,questRaw,"utf8");
    fs.writeFileSync(path.join(content,"data","System.json"),JSON.stringify({locale:"en_US",startMapId:1}),"utf8");
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

    // No dialogue/choice from this external file has been visited.
    // Require its real neural prefetch to finish before first native paint.
    await until(()=>{
        scene.windows[1].refresh();
        const labels=scene.windows[1].drawn;
        return labels.some(v=>/Inventario terminado/.test(v))&&labels.some(v=>{
            const m=/Textos listos:\s*(\d+)\/(\d+)/.exec(v);
            return m&&Number(m[2])>=3&&m[1]===m[2];
        });
    },120000,"IA_EXTERNAL_CSV_PREFETCH_TIMEOUT");
    const journal="\\c[2]Affection: \\c[0]12|Progress: 0\nStage 1(2): Find the missing key.\n- \\c[6]Please open the window.\\I[17]\\c[0] (6 AM, 20 AP)";
    const questMessage=new Window_Message();
    gameMessage._texts=journal.split("\n");
    const beforeQuest=JSON.stringify(gameMessage._texts);
    questMessage.startMessage();
    assert.ok(/Afinidad/.test(questMessage.paintedText)&&/Progreso/.test(questMessage.paintedText)&&/Etapa 1\(2\)/.test(questMessage.paintedText),"IA_QUEST_TXT_HEADER_FAIL");
    assert.ok(/llave/i.test(questMessage.paintedText)&&/ventana/i.test(questMessage.paintedText),"IA_QUEST_TXT_REAL_OPUS_FAIL");
    assert.ok(questMessage.paintedText.includes("\\c[6]")&&questMessage.paintedText.includes("\\I[17]\\c[0] (6 AM, 20 AP)"),"IA_QUEST_TXT_CONTROLS_FAIL");
    assert.equal(JSON.stringify(gameMessage._texts),beforeQuest,"IA_QUEST_TXT_STATE_CHANGED");
    assert.equal(fs.readFileSync(questFile,"utf8"),questRaw,"IA_QUEST_TXT_SOURCE_CHANGED");
    console.log("IA_R41_REAL_OPUS_QUEST_TXT_NATIVE_JOURNAL_PASS "+(isMZ?"MZ":"MV"));
    // Fresh native quote/hotkey route. The worker must translate the
    // inner prose, while the original formatting and _texts survive.
    const formattedNotice=r42Notice.RAW;
    const beforeNoticeWindows=scene.windows.length;
    let noticeResult=r42Notice.inspect("",formattedNotice);
    // Keep the existing readiness budget. Stop waiting once the native
    // renderer has actually changed the sentence; evaluate semantics and
    // exact envelope separately instead of disguising a failed predicate
    // as a connection timeout.
    try{
        await until(()=>{
            gameMessage._texts=[formattedNotice];
            const w=new Window_Message();w.startMessage();
            noticeResult=r42Notice.inspect(w.paintedText,gameMessage._texts[0]);
            assert.equal(gameMessage._texts[0],formattedNotice,"IA_R42_NOTICE_NATIVE_SOURCE_CHANGED");
            assert.equal(w.starts,1,"IA_R42_NOTICE_NATIVE_RESTARTED");
            assert.equal(scene.windows.length,beforeNoticeWindows,"IA_R42_NOTICE_EXTRA_WINDOW");
            return typeof w.paintedText==="string"&&w.paintedText!==formattedNotice;
        },120000,"IA_R42_REAL_OPUS_NOTICE_UNCHANGED_TIMEOUT");
    }catch(error){
        console.log("IA_R42_NOTICE_CHECK "+JSON.stringify(noticeResult));throw error;
    }
    console.log("IA_R42_NOTICE_CHECK "+JSON.stringify(noticeResult));
    assert.ok(noticeResult.envelope,"IA_R42_NOTICE_NATIVE_FORMAT_CHANGED");
    assert.ok(noticeResult.semantic,"IA_R42_NOTICE_REAL_OPUS_SEMANTIC_FAIL");
    assert.ok(noticeResult.ok,"IA_R42_NOTICE_CONTRACT_FAIL");
    console.log("IA_R42_REAL_OPUS_NOTICE_QUOTES_HOTKEY_PASS "+(isMZ?"MZ":"MV"));
    const preloaded=new Window_Message();
    gameMessage._texts=[csvMessage];preloaded.startMessage();
    assert.equal(preloaded.starts,1,"IA_EXTERNAL_CSV_FIRST_PAINT_RESTARTED");
    assert.ok(/^\\c\[2\]/.test(gameMessage.allText())&&/\\I\[17\]$/.test(gameMessage.allText())&&/linterna|farol|lámpara/i.test(gameMessage.allText())&&/mesa/i.test(gameMessage.allText()),"IA_EXTERNAL_CSV_EN_DIALOG_FAIL");
    gameMessage.setChoices([csvChoice],0,1);
    if(isMZ){
        assert.equal(gameMessage._choices[0],csvChoice,"IA_MZ_CHOICE_ORIGINAL_CHANGED");
        const nativeChoice=new Window_ChoiceList();nativeChoice._list[0].name=csvChoice;
        nativeChoice.drawItem(0);
        assert.ok(/abr/i.test(nativeChoice.painted[0])&&/madera/i.test(nativeChoice.painted[0]),"IA_MZ_NATIVE_CHOICE_FAIL");
        assert.equal(nativeChoice._list[0].name,csvChoice);
    }else assert.ok(/abr/i.test(gameMessage._choices[0])&&/madera/i.test(gameMessage._choices[0]),"IA_EXTERNAL_CSV_EN_CHOICE_FAIL");
    choiceValues[61]=csvChoice;
    const choice=new Window_ChoiceList(),originalChoice=JSON.stringify(choice._list);
    gameMessage.setChoices(["\\v[61]"],0,1);
    assert.equal(gameMessage._choices[0],"\\v[61]","IA_CSV_VARIABLE_REFERENCE_CHANGED");
    choice.drawItem(0);
    assert.ok(/abr/i.test(choice.painted[0])&&/madera/i.test(choice.painted[0]),"IA_CSV_VARIABLE_CHOICE_NOT_TRANSLATED");
    assert.equal(JSON.stringify(choice._list),originalChoice,"IA_CSV_CHOICE_LOGIC_CHANGED");
    assert.equal(choiceValues[61],csvChoice,"IA_CSV_GAME_VARIABLE_CHANGED");
    console.log("SERVIDOR_V2_REAL_OPUS_CSV_VARIABLE_CHOICE_PASS");
    gameMessage._texts=[csvJa];new Window_Message().startMessage();
    assert.ok(!japanese(gameMessage.allText())&&/puente/i.test(gameMessage.allText()),"IA_EXTERNAL_CSV_JA_DIALOG_FAIL");
    assert.equal(fs.readFileSync(sheet,"utf8"),csvRaw,"IA_EXTERNAL_CSV_SOURCE_CHANGED");
    console.log("SERVIDOR_V2_REAL_OPUS_EXTERNAL_CSV_PREPARED_FIRST_PAINT_PASS");

    const sourceText="\\N[2] おはようございます。";
    gameMessage._texts=[sourceText];
    const first=new Window_Message();
    first.update();
    assert.equal(first.starts,0,"IA_R6_COLD_DIALOG_PAINTED_BEFORE_TRANSLATION");
    assert.equal(gameMessage.allText(),sourceText,"IA_R6_WAIT_MUTATED_NATIVE_MESSAGE");
    await until(()=>{first.update();return first.starts===1;},35000,"IA_R6_FIRST_DIALOG_TIMEOUT");
    const displayed=gameMessage.allText();
    assert.ok(displayed.startsWith("\\N[2] "),
        "IA_GAME_CONTROL_CODE_CHANGED");
    assert.ok(!japanese(displayed)&&displayed!==sourceText,
        "IA_DIALOG_NOT_TRANSLATED");

    const sourceChoices=["はい、お願いします。","いいえ、けっこうです。"];
    gameMessage._texts=[];
    gameMessage.setChoices(sourceChoices,0,1);
    assert.ok(gameMessage._choices.every(japanese),"IA_UNCACHED_CHOICES_CHANGED");
    const prompt=new Window_Message();
    prompt.update();
    assert.equal(prompt.choiceWindow,undefined,"IA_R6_COLD_CHOICE_OPENED_TOO_EARLY");
    await until(()=>{prompt.update();return !!prompt.choiceWindow;},35000,"IA_R6_FIRST_CHOICE_TIMEOUT");
    assert.ok(prompt.choiceWindow.painted.length===2&&prompt.choiceWindow.painted.every(v=>!japanese(v)),"IA_R6_FIRST_CHOICE_NOT_SPANISH");
    assert.deepEqual(prompt.choiceWindow._list.map(v=>v.name),sourceChoices);
    assert.deepEqual(prompt.choiceWindow._list.map(v=>v.ext),[0,1]);
    console.log("SERVIDOR_V2_R6_REAL_OPUS_FIRST_DIALOG_AND_CHOICES_NO_REPLAY_PASS");
    assert.equal(gameMessage._choices.length,2,"IA_CHOICE_COUNT_CHANGED");
    assert.ok(gameMessage._choices.every(v=>typeof v==="string"&&v.trim()),"IA_NATIVE_CHOICES_EMPTY");
    // R12: use newly written neutral Japanese dialogues containing the
    // same structural risks as the report: fullwidth numerals, clock
    // punctuation and a second line. Never accept partial Japanese.
    gameMessage.setChoices([]);
    const numericLines=["私たちは５年前に会いました。","今は５時です。駅はどこですか？"];
    for(const raw of numericLines){
        const dialogue=new Window_Message();gameMessage._texts=[raw];
        await until(()=>{dialogue.update();return dialogue.starts===1;},35000,"IA_R12_NUMBER_FIRST_VIEW_TIMEOUT");
        assert.ok(!japanese(gameMessage.allText())&&/\b5\b/.test(gameMessage.allText()),"IA_R12_NUMBER_OR_JAPANESE_RESIDUAL");
        assert.equal(dialogue.starts,1);
    }
    console.log("SERVIDOR_V2_R12_REAL_OPUS_JA_NUMBER_FIRST_VIEW_PASS");
    if(isMZ){
        const popup=["LL_InfoPopupWIndow","showMessage","",{messageText:"\\C[2]新しい鍵を入手しました。\\C[0]",showCount:"180",windowX:"auto",windowY:"20",windowBackground:"0"}];
        const saved=JSON.stringify(popup),interpreter=new Game_Interpreter();
        interpreter.setup([{code:357,parameters:popup}]);
        await until(()=>interpreter.command357(popup)===true,35000,"IA_R12_NOTIFICATION_TIMEOUT");
        assert.equal(interpreter.calls.length,1,"IA_R12_NOTIFICATION_REPEATED");
        const visible=interpreter.calls[0][3].messageText;
        assert.ok(!japanese(visible)&&/^\\C\[2\]/.test(visible)&&/\\C\[0\]$/.test(visible),"IA_R12_NOTIFICATION_NOT_TRANSLATED");
        assert.equal(JSON.stringify(popup),saved,"IA_R12_NOTIFICATION_DATA_CHANGED");
        for(const k of Object.keys(popup[3]))if(k!=="messageText")assert.equal(interpreter.calls[0][3][k],popup[3][k]);
        console.log("SERVIDOR_V2_R12_REAL_OPUS_MZ_NOTIFICATION_PASS");
        const name=new Window_NameBox(new Rectangle(0,0,250,52));
        gameMessage.setSpeakerName("Haruka");name.setName("Haruka");
        assert.equal(gameMessage._speakerName,"Haruka");
        assert.equal(name.drawn[0],"Haruka");
        const formatted="\\FS[24]\\PX[12]\\PY[8]Please open the wooden gate.";
        await until(()=>{
            gameMessage._texts=[formatted];new Window_Message().startMessage();
            return gameMessage.allText()!==formatted;
        },120000,"IA_MZ_FORMATTED_DIALOG_TIMEOUT");
        assert.ok(/^\\FS\[24\]\\PX\[12\]\\PY\[8\]/.test(gameMessage.allText()),"IA_MZ_CONTROL_CODES_CHANGED");
        assert.ok(/abr/i.test(gameMessage.allText())&&/madera/i.test(gameMessage.allText()),"IA_MZ_FORMATTED_DIALOG_FAIL");
        assert.equal(scene.windows.length,2,"IA_MZ_EXTRA_WINDOW");
        console.log("SERVIDOR_V2_REAL_OPUS_MZ_RECTANGLE_NAME_CHOICES_CONTROLS_PASS");
        return;
    }
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
