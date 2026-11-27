/* Authored laboratory MV interface contract, run as a browser script in
 * real NW.js. No third-party game assets or protection code are included.
 * This is not the commercial MV engine: the original renderer here is an
 * actual Canvas2D draw of the text supplied by the synthetic window. */
// RPG Maker MV declares these bindings in classic browser scripts.
// Use the same global environment instead of merely adding properties
// from a closure; keep NW.js's default separate Node/browser contexts.
var Utils, Window_Base, Window_Message, Game_Message, Scene_Map;
var $gameMessage, SceneManager, Graphics, Input;
(function(){
"use strict";
var fs=require("fs"),path=require("path"),http=require("http");
var root=nw.App.startPath;
var resultFile=path.join(root,"r44-real-result.json");
var enBody="Please close the wooden door.";
var enRaw='※"'+enBody+'" 【M】';
var jaRaw="橋を渡ってください。";
var dialog=new Game_Message();
var errors=[];
window.__IA_TRADUCTORA_TEST_HOOKS__=true;
window.addEventListener("error",function(event){
    var file=String(event.filename||"");
    if(/(?:^|[\\/])IATraductora\.js(?:$|\?)/i.test(file)){
        var name=event.error&&event.error.name;
        if(!/^(?:Error|TypeError|ReferenceError|SyntaxError|RangeError)$/.test(String(name)))name="Error";
        if(errors.length<8)errors.push({name:name,line:Number(event.lineno)||0,column:Number(event.colno)||0});
    }
},true);
function bootDiagnostic(){
    var p=window.__IA_TRADUCTORA_TEST_BOOT__||{};
    var safe=function(v){return typeof v==="string"&&/^[A-Z0-9_]+$/.test(v)?v:"UNKNOWN";};
    return {checkpoint:safe(p.checkpoint),phase:safe(p.phase),hud:safe(p.hud),
        error:safe(p.error),hudError:safe(p.hudError),browserErrors:errors.slice(),
        testHooks:!!window.__IA_TRADUCTORA_TEST__,globals:typeof Utils==="object"&&
        typeof Window_Base==="function"&&typeof Window_Message==="function"&&
        typeof Scene_Map==="function"&&typeof Graphics==="object"&&typeof Input==="object"};
}
function check(value,code){if(!value)throw new Error(code);}
function wait(ms){return new Promise(function(resolve){setTimeout(resolve,ms);});}
async function until(fn,limit,code){
    var end=Date.now()+limit;
    do{if(fn())return;await wait(100);}while(Date.now()<end);
    throw Error(code);
}
function Window_Base(){this.initialize.apply(this,arguments);}
Window_Base.prototype.initialize=function(x,y,w,h){
    this.x=x;this.y=y;this.width=w;this.height=h;
    this.visible=true;this.drawn=[];
    this.canvas=document.createElement("canvas");
    this.canvas.width=w;this.canvas.height=h;
    document.body.appendChild(this.canvas);
    var self=this;
    this.contents={fontSize:18,outlineWidth:1,clear:function(){
        self.drawn=[];self.canvas.getContext("2d").clearRect(0,0,w,h);
    }};
};
Window_Base.prototype.contentsWidth=function(){return this.width-24;};
Window_Base.prototype.drawText=function(text,x,y,maxWidth,align){
    text=String(text);this.drawn.push(text);
    var ctx=this.canvas.getContext("2d");
    ctx.font=this.contents.fontSize+"px Arial";ctx.fillStyle="#fff";
    ctx.textAlign=align==="center"?"center":"left";
    var left=(Number(x)||0)+(align==="center"?(Number(maxWidth)||this.width)/2:0);
    ctx.fillText(text,left, (Number(y)||0)+this.contents.fontSize,Number(maxWidth)||this.width);
};
Window_Base.prototype.hasPixels=function(){
    var data=this.canvas.getContext("2d").getImageData(0,0,this.canvas.width,this.canvas.height).data;
    for(var i=3;i<data.length;i+=4)if(data[i]>0)return true;
    return false;
};
Window_Base.prototype.show=function(){this.visible=true;};
Window_Base.prototype.hide=function(){this.visible=false;};
function Game_Message(){this._texts=[];this._choices=[];}
Game_Message.prototype.hasText=function(){return this._texts.length>0;};
Game_Message.prototype.allText=function(){return this._texts.join("\n");};
Game_Message.prototype.setChoices=function(values){this._choices=values.slice();};
Game_Message.prototype.choices=function(){return this._choices;};
function Window_Message(){
    Window_Base.prototype.initialize.call(this,0,0,760,70);
    this.starts=0;this.paintedText="";
}
Window_Message.prototype=Object.create(Window_Base.prototype);
Window_Message.prototype.constructor=Window_Message;
Window_Message.prototype.startMessage=function(){
    this.starts++;
    this.paintedText=dialog.allText();
    var ctx=this.canvas.getContext("2d");
    ctx.clearRect(0,0,760,70);
    ctx.font="22px Arial";ctx.fillStyle="#ffffff";
    ctx.fillText(this.paintedText,8,35);
};
Window_Message.prototype.updateWait=function(){return false;};
Window_Message.prototype.canStart=function(){return this.starts===0&&dialog.hasText();};
Window_Message.prototype.update=function(){
    if(this.updateWait())return;
    if(this.canStart())this.startMessage();
};
function Scene_Map(){this.windows=[];}
Scene_Map.prototype.createAllWindows=function(){};
Scene_Map.prototype.update=function(){};
Scene_Map.prototype.addWindow=function(w){this.windows.push(w);};
Object.assign(window,{
    Utils:{isNwjs:function(){return true;},RPGMAKER_NAME:"MV"},
    Window_Base:Window_Base,Window_Message:Window_Message,Game_Message:Game_Message,Scene_Map:Scene_Map,
    $gameMessage:dialog,SceneManager:{_scene:null},
    Graphics:{boxWidth:816,boxHeight:624},Input:{keyMapper:{121:"debug"},isTriggered:function(){return false;}}
});
function status(){
    var descriptor=JSON.parse(fs.readFileSync(path.join(root,"www","data","IATraductora","bridge.json"),"utf8"));
    check(descriptor.schema==="ia-traductora-bridge-v1"&&/^[a-f0-9]{64}$/.test(descriptor.token)&&
          Number.isInteger(descriptor.port)&&descriptor.port>=1024&&descriptor.port<=65535,
          "IA_R44_DESCRIPTOR_INVALID");
    return new Promise(function(resolve,reject){
        var req=http.get({hostname:"127.0.0.1",port:descriptor.port,path:"/status",headers:{"X-IA-Token":descriptor.token}},function(res){
            var body="";res.setEncoding("utf8");
            res.on("data",function(chunk){body+=chunk;if(body.length>16384)req.destroy(Error("IA_R44_STATUS_SIZE"));});
            res.on("end",function(){
                try{
                    check(res.statusCode===200,"IA_R44_STATUS_HTTP");
                    var value=JSON.parse(body);
                    check(value.schema==="ia-traductora-bridge-v1"&&value.active===true&&Number.isInteger(value.translated),
                        "IA_R44_STATUS_INVALID");
                    resolve(value);
                }catch(e){reject(e);}
            });
        });
        req.setTimeout(4000,function(){req.destroy(Error("IA_R44_STATUS_TIMEOUT"));});
        req.on("error",reject);
    });
}
async function drawOne(scene,raw,code){
    dialog._texts=[raw];dialog._choices=[];
    var message=new Window_Message();
    await until(function(){scene.update();message.update();return message.starts===1;},40000,code+"_TIMEOUT");
    check(message.starts===1&&message.hasPixels(),code+"_PAINT");
    message.update();
    check(message.starts===1,code+"_RESTART");
    return message;
}
function f10(){
    window.dispatchEvent(new KeyboardEvent("keydown",{key:"F10",code:"F10",bubbles:true,cancelable:true}));
}
function openScene(){
    check(process.versions.nw==="0.48.4","IA_R44_WRONG_RUNTIME");
    check(window.coreReady&&window.originalGuardRan&&window.originalPluginsRan,"IA_R44_BINARY_ORDER");
    check(window.$plugins.filter(function(p){return p.name==="IATraductora"&&p.status===true;}).length===1,"IA_R44_REGISTRY");
    var boot=bootDiagnostic();
    check(boot.globals,"IA_R44_GLOBALS_MISSING");
    check(boot.checkpoint==="COMPLETE"&&boot.phase==="ACTIVO"&&boot.testHooks&&!boot.browserErrors.length,
        "IA_R44_PLUGIN_BOOT_INCOMPLETE");
    var scene=new Scene_Map();SceneManager._scene=scene;
    scene.createAllWindows();
    check(scene.windows.length===2&&scene._iaPanel&&scene._iaMini,"IA_R44_HUD_MISSING");
    check(scene._iaMini.hasPixels()&&scene._iaMini.drawn.some(function(t){return t.indexOf("IA Traductora")>=0;}),
        "IA_R44_HUD_NATIVE_PAINT_MISSING");
    return scene;
}
function verifyF10(expectConnected){
    f10();
    var panels=Array.from(document.querySelectorAll("pre"));
    var panel=panels.filter(function(el){return el.textContent.indexOf("IA Traductora")>=0;})[0];
    check(panel&&panel.style.display==="block","IA_R44_F10_OPEN");
    if(expectConnected)check(panel.textContent.indexOf("IA local conectada")>=0,"IA_R44_F10_STATUS");
    f10();
    check(panel.style.display==="none"&&Input.keyMapper[121]==="debug","IA_R44_F10_CLOSE");
}
async function run(){
    var scene=openScene();scene.update();
    await until(function(){
        scene.update();scene._iaPanel.refresh();
        return scene._iaPanel.drawn.some(function(t){return t.indexOf("IA local conectada")>=0;});
    },120000,"IA_R44_WORKER_CONNECTION");
    verifyF10(true);
    var en=await drawOne(scene,enRaw,"IA_R44_EN");
    var match=/^※"([^"\r\n]+)" 【M】$/.exec(en.paintedText);
    check(match&&/^(?:por favor,?\s+)?(?:cierra|cierre|cierren|cerrad|cerrar)(?:,?\s+por favor,?)?\s+la\s+puerta\s+de\s+madera(?:,?\s+por favor)?[.!]?$/i.test(match[1].trim()),
        "IA_R44_EN_FORMAT_SEMANTICS");
    check(dialog.allText()===enRaw,"IA_R44_EN_SOURCE_CHANGED");
    var ja=await drawOne(scene,jaRaw,"IA_R44_JA");
    check(/puente/i.test(ja.paintedText)&&!/[\u3040-\u30ff\u3400-\u9fff]/.test(ja.paintedText)&&ja.paintedText!==jaRaw,
        "IA_R44_JA_SEMANTICS");
    check(scene.windows.length===2&&window.originalGuardRan&&window.originalPluginsRan,"IA_R44_EXTRA_WINDOWS_OR_BINARY_STATE");
    var stats=await status();
    return {ok:true,kind:"real",nw:process.versions.nw,en:match[1],ja:ja.paintedText,translated:stats.translated};
}
function finish(value){
    value.boot=bootDiagnostic();
    fs.writeFileSync(resultFile,JSON.stringify(value),"utf8");
    nw.App.quit();
}
window.r44RunUIOnly=function(){
    try{
        openScene();verifyF10(false);
        // Do not activate the map or spawn a test worker. This check is
        // solely a UI/boot preflight of the actual packaged JS source.
        check(!fs.existsSync(path.join(root,"www","data","IATraductora","bridge.json")),"IA_R44_PREFLIGHT_WORKER_STARTED");
        finish({ok:true,kind:"ui",nw:process.versions.nw});
    }catch(e){
        finish({ok:false,code:e&&/^IA_R44_[A-Z0-9_]+$/.test(e.message)?e.message:"IA_R44_PREFLIGHT_FAILED"});
    }
};
window.r44Run=function(){
    if(window.r44Started)return;
    window.r44Started=true;
    run().then(finish,function(error){
        var code=error&&/^IA_R44_[A-Z0-9_]+$/.test(error.message)?error.message:"IA_R44_RENDERER_FAILED";
        finish({ok:false,code:code});
    });
};
window.r44LoadFailed=function(){finish({ok:false,code:"IA_R44_PLUGIN_LOAD_FAILED"});};
})();
