/* Authored laboratory MV interface contract, run as a browser script in
 * real NW.js. No third-party game assets or protection code are included.
 * This is not the commercial MV engine: the original renderer here is an
 * actual Canvas2D draw of the text supplied by the synthetic window. */
(function(){
"use strict";
var fs=require("fs"),path=require("path"),http=require("http");
var root=nw.App.startPath;
var resultFile=path.join(root,"r44-real-result.json");
var enBody="Please close the wooden door.";
var enRaw='※"'+enBody+'" 【M】';
var jaRaw="橋を渡ってください。";
var dialog=new Game_Message();
function check(value,code){if(!value)throw new Error(code);}
function wait(ms){return new Promise(function(resolve){setTimeout(resolve,ms);});}
async function until(fn,limit,code){
    var end=Date.now()+limit;
    do{if(fn())return;await wait(100);}while(Date.now()<end);
    throw Error(code);
}
function Window_Base(){}
Window_Base.prototype.initialize=function(x,y,w,h){
    this.x=x;this.y=y;this.width=w;this.height=h;
    this.visible=true;this.drawn=[];
    var self=this;
    this.contents={fontSize:18,outlineWidth:1,clear:function(){self.drawn=[];}};
};
Window_Base.prototype.contentsWidth=function(){return this.width-24;};
Window_Base.prototype.drawText=function(text){this.drawn.push(String(text));};
Window_Base.prototype.show=function(){this.visible=true;};
Window_Base.prototype.hide=function(){this.visible=false;};
function Game_Message(){this._texts=[];this._choices=[];}
Game_Message.prototype.hasText=function(){return this._texts.length>0;};
Game_Message.prototype.allText=function(){return this._texts.join("\n");};
Game_Message.prototype.setChoices=function(values){this._choices=values.slice();};
Game_Message.prototype.choices=function(){return this._choices;};
function Window_Message(){
    this.starts=0;this.paintedText="";
    this.canvas=document.createElement("canvas");
    this.canvas.width=760;this.canvas.height=70;
    document.body.appendChild(this.canvas);
}
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
Window_Message.prototype.hasPixels=function(){
    var data=this.canvas.getContext("2d").getImageData(0,0,760,70).data;
    for(var i=3;i<data.length;i+=4)if(data[i]>0)return true;
    return false;
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
async function run(){
    check(process.versions.nw==="0.48.4","IA_R44_WRONG_RUNTIME");
    check(window.coreReady&&window.originalGuardRan&&window.originalPluginsRan,"IA_R44_BINARY_ORDER");
    check(window.$plugins.filter(function(p){return p.name==="IATraductora"&&p.status===true;}).length===1,"IA_R44_REGISTRY");
    var scene=new Scene_Map();SceneManager._scene=scene;
    scene.createAllWindows();scene.update();
    check(scene.windows.length===2&&scene._iaPanel&&scene._iaMini,"IA_R44_HUD_MISSING");
    await until(function(){
        scene.update();scene._iaPanel.refresh();
        return scene._iaPanel.drawn.some(function(t){return t.indexOf("IA local conectada")>=0;});
    },120000,"IA_R44_WORKER_CONNECTION");
    f10();
    var panels=Array.from(document.querySelectorAll("pre"));
    var panel=panels.filter(function(el){return el.textContent.indexOf("IA Traductora")>=0;})[0];
    check(panel&&panel.style.display==="block"&&panel.textContent.indexOf("IA local conectada")>=0,"IA_R44_F10_OPEN");
    f10();
    check(panel.style.display==="none"&&Input.keyMapper[121]==="debug","IA_R44_F10_CLOSE");
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
    return {ok:true,nw:process.versions.nw,en:match[1],ja:ja.paintedText,translated:stats.translated};
}
function finish(value){
    fs.writeFileSync(resultFile,JSON.stringify(value),"utf8");
    nw.App.quit();
}
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
