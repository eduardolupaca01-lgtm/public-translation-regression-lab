/*:
 * @plugindesc IA Traductora RPG Maker MV — motor local propio, sin cuentas ni nube.
 * @author Servidor
 * @help El instalador Servidor configura el motor local. F10 muestra el estado.
 * No necesita parámetros ni acceso a Internet.
 */
(function () {
"use strict";
var BRAND="IA Traductora";
if(typeof Utils==="undefined" || !Utils.isNwjs || !Utils.isNwjs()) return;
var fs=require("fs"),path=require("path"),crypto=require("crypto");
var http=require("http"),spawn=require("child_process").spawn;
var game="",content="",sidecar="",worker="",descriptorFile="";
var state={connected:false,status:"Comprobando instalación",requested:0,received:0,shown:0,errors:0};
var token="",port=0,starting=false,lastAttempt=0,proc=null;
var cache=new Map(),pending=new Map(),maxWait=24000;
function rootFromURL(){
    var name=decodeURIComponent(window.location.pathname);
    if(/^\/[A-Za-z]:/.test(name)) name=name.slice(1);
    var dir=fs.realpathSync(path.dirname(name));
    return path.basename(dir).toLowerCase()==="www"?path.dirname(dir):dir;
}
function ordinary(file){
    try{var st=fs.lstatSync(file);return st.isFile()&&!st.isSymbolicLink();}
    catch(_){return false;}
}
function owner(){
    var file=path.join(sidecar,"owner-v1.json");
    if(!ordinary(file)) throw Error("Falta registro de instalación");
    var data=JSON.parse(fs.readFileSync(file,"utf8"));
    if(data.schema!=="ia-traductora-owner-v1"||
       typeof data.worker_sha256!=="string"||!/^[0-9a-f]{64}$/.test(data.worker_sha256))
        throw Error("Registro de instalación inválido");
    return data;
}
function initPaths(){
    game=rootFromURL();
    content=ordinary(path.join(game,"www","js","rpg_core.js"))?path.join(game,"www"):game;
    sidecar=path.join(game,"IA Traductora");
    worker=path.join(sidecar,".local","Rpg","engine","IATraductora.exe");
    descriptorFile=path.join(content,"data","IATraductora","bridge.json");
}
function descriptor(){
    if(!ordinary(descriptorFile))return null;
    try{
        var d=JSON.parse(fs.readFileSync(descriptorFile,"utf8"));
        if(d.schema!=="ia-traductora-bridge-v1"||!Number.isInteger(d.port)||
           d.port<1024||d.port>65535||!/^[0-9a-f]{64}$/.test(d.token)||!(d.pid>0))return null;
        return d;
    }catch(_){return null;}
}
function request(route,body,timeout){
    return new Promise(function(resolve,reject){
        var d=descriptor();
        if(!d){reject(Error("Sin conexión local"));return;}
        var payload=body?Buffer.from(JSON.stringify(body),"utf8"):null;
        var headers={"X-IA-Token":d.token,"Accept":"application/json"};
        if(payload)headers["Content-Type"]="application/json; charset=utf-8";
        var req=http.request({hostname:"127.0.0.1",port:d.port,path:route,
            method:payload?"POST":"GET",headers:headers,timeout:timeout||20000},
            function(res){
                if(res.statusCode!==200){res.resume();reject(Error("IA HTTP "+res.statusCode));return;}
                var buffer="",size=0;
                res.on("data",function(chunk){
                    size+=chunk.length;
                    if(size>16384){req.destroy(Error("Respuesta demasiado grande"));return;}
                    buffer+=chunk.toString("utf8");
                });
                res.on("end",function(){
                    try{resolve(JSON.parse(buffer));}catch(_){reject(Error("Respuesta IA inválida"));}
                });
            });
        req.on("timeout",function(){req.destroy(Error("Tiempo agotado"));});
        req.on("error",reject);
        req.end(payload||undefined);
    });
}
function startWorker(){
    // CTranslate2 can take time to load genuine neural weights on Windows.
    // Never start a second model process while our OWN worker is alive.
    if(proc && Number.isInteger(proc.pid) && proc.pid>0 &&
       proc.exitCode===null && !proc.killed){
        state.status="IA cargando modelos";
        return;
    }
    if(starting||Date.now()-lastAttempt<15000)return;
    starting=true;lastAttempt=Date.now();state.status="Verificando motor local";
    try {
        var marker=owner();
        if(!ordinary(worker))throw Error("No existe IATraductora.exe");
        var sha=crypto.createHash("sha256"),stream=fs.createReadStream(worker);
        stream.on("data",function(chunk){sha.update(chunk);});
        stream.on("error",function(){starting=false;state.status="Motor inaccesible";state.errors++;});
        stream.on("end",function(){
            try{
                if(sha.digest("hex")!==marker.worker_sha256)throw Error("Firma incorrecta");
                var env=Object.assign({},process.env);
                var local=path.join(sidecar,".local"),tmp=path.join(local,"tmp");
                fs.mkdirSync(tmp,{recursive:true});
                env.LOCALAPPDATA=local;env.TEMP=tmp;env.TMP=tmp;env.TMPDIR=tmp;
                proc=spawn(worker,["--game-root",game,"--parent-pid",String(process.pid)],
                    {cwd:game,env:env,windowsHide:true,detached:false,shell:false,stdio:"ignore"});
                proc.on("error",function(){state.status="Error al abrir IA";state.errors++;starting=false;proc=null;});
                proc.on("exit",function(){state.connected=false;state.status="Motor detenido";starting=false;proc=null;});
                state.status="Iniciando IA local";
                starting=false;
            }catch(_){state.status="Motor sin firma válida";state.errors++;starting=false;}
        });
    }catch(_){state.status="Instalación incompleta";state.errors++;starting=false;}
}
function refreshConnection(){
    request("/status",null,2500).then(function(d){
        if(d.schema!=="ia-traductora-bridge-v1"||d.active!==true)throw Error("Motor no autenticado");
        state.connected=true;state.status="IA local conectada";
    }).catch(function(){
        state.connected=false;
        state.status="Esperando IA local";
        startWorker();
    });
}
function translate(text){
    if(cache.has(text))return Promise.resolve(cache.get(text));
    if(pending.has(text))return pending.get(text);
    state.requested++;
    var call=new Promise(function(resolve){
        var beginning=Date.now(),done=false;
        function attempt(){
            if(done)return;
            if(Date.now()-beginning>maxWait){done=true;state.errors++;resolve(null);return;}
            if(!state.connected){setTimeout(attempt,600);return;}
            request("/translate",{source:"ja",target:"es",text:text},12000).then(function(r){
                if(r && typeof r.translated==="string"&&r.translated.trim()&&r.translated!==text){
                    cache.set(text,r.translated);state.received++;done=true;resolve(r.translated);
                }else{done=true;state.errors++;resolve(null);}
            }).catch(function(){setTimeout(attempt,1200);});
        }
        attempt();
    }).finally(function(){pending.delete(text);});
    pending.set(text,call);
    return call;
}
function isJapanese(s){return /[\u3040-\u30ff\u3400-\u9fff]/.test(s||"");}
function isProtected(s){
    // Control sequences are retained byte-for-byte; until proper masking,
    // never send unbalanced game commands into the neural model.
    return /\\(?:V|N|P|G|C|I|FS|PX|PY)\s*\[/i.test(s||"");
}
function hookMessages(){
    if(typeof Window_Message==="undefined"||!Window_Message.prototype)return;
    var original=Window_Message.prototype.startMessage;
    Window_Message.prototype.startMessage=function(){
        if(this._iaWaiting)return;
        if(!$gameMessage||!$gameMessage.hasText())return original.apply(this,arguments);
        var text=$gameMessage.allText();
        if(!isJapanese(text)||isProtected(text))return original.apply(this,arguments);
        if(cache.has(text)){
            $gameMessage._texts=cache.get(text).split("\n");state.shown++;
            return original.apply(this,arguments);
        }
        var instance=this;
        instance._iaWaiting={text:text,at:Date.now(),done:false,translated:null};
        translate(text).then(function(out){
            if(!instance._iaWaiting||instance._iaWaiting.text!==text)return;
            instance._iaWaiting.done=true;
            instance._iaWaiting.translated=out;
        });
    };
    var update=Window_Message.prototype.update;
    Window_Message.prototype.update=function(){
        if(this._iaWaiting){
            var w=this._iaWaiting;
            if(!w.done&&Date.now()-w.at<maxWait+1500)return;
            this._iaWaiting=null;
            if(w.translated){$gameMessage._texts=w.translated.split("\n");state.shown++;}
            original.call(this);
        }
        return update.apply(this,arguments);
    };
}
function setupHud(){
    if(typeof Window_Base==="undefined"||typeof Scene_Map==="undefined")return;
    function IAMini(){this.initialize.apply(this,arguments);}
    IAMini.prototype=Object.create(Window_Base.prototype);
    IAMini.prototype.constructor=IAMini;
    IAMini.prototype.standardPadding=function(){return 6;};
    IAMini.prototype.lineHeight=function(){return 26;};
    IAMini.prototype.initialize=function(){
        Window_Base.prototype.initialize.call(this,Graphics.boxWidth-218,7,208,44);
        this.opacity=190;
        this.contents.fontSize=14;this.contents.outlineWidth=3;
        this.drawText("◆ IA Traductora · F10",0,0,this.contentsWidth(),"center");
    };
    function IAPanel(){this.initialize.apply(this,arguments);}
    IAPanel.prototype=Object.create(Window_Base.prototype);
    IAPanel.prototype.constructor=IAPanel;
    IAPanel.prototype.standardPadding=function(){return 12;};
    IAPanel.prototype.lineHeight=function(){return 27;};
    IAPanel.prototype.initialize=function(){
        Window_Base.prototype.initialize.call(this,Graphics.boxWidth-345,7,335,225);
        this.opacity=205;this.visible=false;this._tick=0;this.refresh();
    };
    IAPanel.prototype.refresh=function(){
        this.contents.clear();
        var lines=["IA Traductora · RPG","Idioma: Español","Origen: Auto",
            "Motor: "+state.status,"Solicitados: "+state.requested,
            "Recibidos: "+state.received+" · Mostrados: "+state.shown,
            "Errores: "+state.errors,"Cerrar (F10)"];
        for(var i=0;i<lines.length;i++){
            this.drawText(lines[i],0,i*24,this.contentsWidth(),"left");
        }
    };
    var create=Scene_Map.prototype.createAllWindows;
    Scene_Map.prototype.createAllWindows=function(){
        create.apply(this,arguments);
        this._iaMini=new IAMini();this.addWindow(this._iaMini);
        this._iaPanel=new IAPanel();this.addWindow(this._iaPanel);
    };
    var updateScene=Scene_Map.prototype.update;
    Scene_Map.prototype.update=function(){
        updateScene.apply(this,arguments);
        if(Input.isTriggered("ia-traductora")&&this._iaPanel){
            this._iaPanel.visible=!this._iaPanel.visible;
            this._iaMini.visible=!this._iaPanel.visible;
        }
        if(this._iaPanel && ++this._iaPanel._tick%30===0&&this._iaPanel.visible)this._iaPanel.refresh();
    };
    Input.keyMapper[121]="ia-traductora";
}
try{
    initPaths();
    if(!ordinary(path.join(content,"js","rpg_core.js")))throw Error("Sólo RPG Maker MV");
    hookMessages();setupHud();
    refreshConnection();setInterval(refreshConnection,4500);
}catch(_){state.status="Instalación no reconocida";state.errors++;}
})();
