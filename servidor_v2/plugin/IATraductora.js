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
// A missing Node module must never prevent the game itself from booting.
var fs,path,crypto,http,spawn;
try{
    fs=require("fs");path=require("path");crypto=require("crypto");
    http=require("http");spawn=require("child_process").spawn;
}catch(_){return;}
if(typeof Map!=="function"||typeof Promise!=="function")return;
var game="",content="",sidecar="",worker="",descriptorFile="",startupFile="";
var state={connected:false,status:"Comprobando instalación",phase:"INICIO",requested:0,received:0,shown:0,errors:0};
var token="",port=0,starting=false,lastAttempt=0,proc=null;
var runtimeActivated=false;
var cache=new Map(),pending=new Map(),maxWait=45000,messageWait=4500;
var cacheDir="",cacheFile="",diskReady=false,diskBusy=false,diskQueue=[];
var diskStats={loaded:0,saved:0,rejected:0,errors:0};
// A cache never includes game assets or saves. The schema is versioned to
// quarantine old, unverified outputs from previous releases.
var CACHE_SCHEMA="ia-traductora-cache-v2",CACHE_LIMIT=12*1024*1024;
// NW.js versions resolve index.html and Game.exe differently. Detect only an
// actual MV root by checking its original files; never trust a guessed path.
function resolveMVGame(){
    var candidates=[],seen={};
    function add(value){
        if(typeof value!=="string"||!value||value.length>4096)return;
        try{
            var name=value;
            if(/^file:\/\//i.test(name)){
                name=name.replace(/^file:\/\//i,"");
                if(!/^[\\/]/.test(name)&&!/^[A-Za-z]:[\\/]/.test(name))
                    name="//"+name; // file://server/share/ (UNC)
            }
            name=decodeURIComponent(name);
            if(/^\/[A-Za-z]:[\\/]/.test(name))name=name.slice(1);
            if(!path.isAbsolute(name))return; // do not search unrelated folders
            var loc=path.normalize(name);
            if(/\.(?:js|html?)$/i.test(path.basename(loc)))loc=path.dirname(loc);
            if(path.basename(loc).toLowerCase()==="plugins")
                loc=path.dirname(path.dirname(loc));
            else if(path.basename(loc).toLowerCase()==="js")
                loc=path.dirname(loc);
            if(path.basename(loc).toLowerCase()==="www")loc=path.dirname(loc);
            if(!seen[loc]){seen[loc]=true;candidates.push(loc);}
        }catch(_){}
    }
    try{add(path.dirname(process.execPath));}catch(_){}
    try{
        if(typeof document!=="undefined"&&document.currentScript)
            add(document.currentScript.src);
    }catch(_){}
    try{add(window.location.pathname);}catch(_){}
    try{add(window.location.href);}catch(_){}
    try{add(process.cwd());}catch(_){}
    for(var i=0;i<candidates.length;i++){
        var base=candidates[i];
        for(var j=0;j<2;j++){
            var folder=j===0?path.join(base,"www"):base;
            if(!ordinary(path.join(folder,"js","rpg_core.js"))||
               !ordinary(path.join(folder,"js","plugins.js")))continue;
            try{
                var root=fs.realpathSync(base);
                // The chosen JS folder must remain associated with this game.
                if(ordinary(path.join(root,j===0?"www":".","js","rpg_core.js")))
                    return {root:root,content:j===0?path.join(root,"www"):root};
            }catch(_){}
        }
    }
    throw Error("IA_RUTA_MV_NO_RECONOCIDA");
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
    var found=resolveMVGame();
    game=found.root;content=found.content;
    sidecar=path.join(game,"IA Traductora");
    worker=path.join(sidecar,".local","Rpg","engine","IATraductora.exe");
    descriptorFile=path.join(content,"data","IATraductora","bridge.json");
    startupFile=path.join(sidecar,".local","Rpg","startup-status.json");
}
function integer(v){
    return typeof v==="number"&&isFinite(v)&&Math.floor(v)===v;
}
function descriptor(){
    if(!ordinary(descriptorFile))return null;
    try{
        var d=JSON.parse(fs.readFileSync(descriptorFile,"utf8"));
        if(d.schema!=="ia-traductora-bridge-v1"||!integer(d.port)||
           d.port<1024||d.port>65535||!/^[0-9a-f]{64}$/.test(d.token)||!(d.pid>0))return null;
        return d;
    }catch(_){return null;}
}
function startupCode(){
    if(!startupFile||!ordinary(startupFile))return "";
    try{
        var raw=fs.readFileSync(startupFile,"utf8");
        if(raw.length>512)return "";
        var doc=JSON.parse(raw);
        var code=doc&&doc.schema==="ia-traductora-startup-v1"?doc.code:"";
        return typeof code==="string"&&/^IA_[A-Z0-9_]{4,90}$/.test(code)?code:"";
    }catch(_){return "";}
}
function request(route,body,timeout){
    return new Promise(function(resolve,reject){
        var d=descriptor();
        if(!d){reject(Error("Sin conexión local"));return;}
        // Buffer.from was added after many deployed RPG Maker MV NW.js versions.
        var payload=body?(typeof Buffer.from==="function"?
            Buffer.from(JSON.stringify(body),"utf8"):
            new Buffer(JSON.stringify(body),"utf8")):null;
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
    // Loading two large models during the title/boot scene can starve MV.
    // Start ONLY after the first Scene_Map.update, never during boot.
    if(!runtimeActivated){state.status="IA espera entrar al mapa";return;}
    // CTranslate2 can take time to load genuine neural weights on Windows.
    // Never start a second model process while our OWN worker is alive.
    if(proc && integer(proc.pid) && proc.pid>0 &&
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
                var env={};
                for(var name in process.env){
                    if(Object.prototype.hasOwnProperty.call(process.env,name))
                        env[name]=process.env[name];
                }
                var local=path.join(sidecar,".local"),tmp=path.join(local,"tmp");
                // Older RPG Maker MV NW.js builds do not support recursive mkdir.
                try{fs.mkdirSync(tmp);}catch(e){
                    if(!e||e.code!=="EEXIST")throw e;
                }
                var tempInfo=fs.lstatSync(tmp);
                if(!tempInfo.isDirectory()||tempInfo.isSymbolicLink())
                    throw Error("IA_TEMP_NO_SEGURO");
                env.LOCALAPPDATA=local;env.TEMP=tmp;env.TMP=tmp;env.TMPDIR=tmp;
                proc=spawn(worker,["--game-root",game,"--parent-pid",String(process.pid),
                    "--diagnostic-file",startupFile],
                    {cwd:game,env:env,windowsHide:true,detached:false,shell:false,stdio:"ignore"});
                proc.on("error",function(){state.status="IA no pudo iniciarse";state.errors++;starting=false;proc=null;});
                proc.on("exit",function(){state.connected=false;state.status=startupCode()||"Motor detenido";starting=false;proc=null;});
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
        state.status=startupCode()||"Esperando IA local";
        startWorker();
    });
}
function translate(source,text){
    if(cache.has(source+"\u0000"+text))return Promise.resolve(cache.get(source+"\u0000"+text));
    if(pending.has(source+"\u0000"+text))return pending.get(source+"\u0000"+text);
    state.requested++;
    var raw=new Promise(function(resolve){
        var beginning=Date.now(),done=false;
        function attempt(){
            if(done)return;
            if(Date.now()-beginning>maxWait){done=true;state.errors++;resolve(null);return;}
            if(!state.connected){setTimeout(attempt,600);return;}
            request("/translate",{source:source,target:"es",text:text},30000).then(function(r){
                if(r && acceptCache(source,text,r.translated,false,true)){
                    state.received++;done=true;resolve(r.translated);
                }else{done=true;state.errors++;resolve(null);}
            }).catch(function(){setTimeout(attempt,1200);});
        }
        attempt();
    });
    // Promise.finally is absent on many original RPG Maker MV NW.js builds.
    var key=source+"\u0000"+text;
    var call=raw.then(function(value){
        pending.delete(key);return value;
    },function(error){
        pending.delete(key);throw error;
    });
    pending.set(key,call);
    return call;
}

function numbersIn(text){
    var n=String(text).match(/[0-9０-９]+/g)||[];
    return n.map(function(v){return v.replace(/[０-９]/g,function(c){
        return String(c.charCodeAt(0)-65296);
    });}).sort().join("|");
}
function validTranslation(source,original,result,composed){
    if(typeof original!=="string"||typeof result!=="string"||
       !original||!result.trim()||result===original||
       result.length>Math.max(100,Math.min(5400,original.length*5+80))||
       /\uFFFD|\u0000/.test(result)||numbersIn(original)!==numbersIn(result))
        return false;
    if(source==="ja"){
        var withoutHeader=result;
        if(composed){
            var prefix=speakerHeader(original);
            if(prefix){
                var name=nameInSpanish(prefix.name)||prefix.name;
                var start=name+prefix.separator;
                if(withoutHeader.indexOf(start)===0){
                    withoutHeader=withoutHeader.slice(start.length);
                }
            }
        }
        var visible=protectedParts(withoutHeader).filter(function(c){
            return !c.locked;
        }).map(function(c){return c.value;}).join("");
        if(isJapanese(visible))return false;
    }
    // A replayed cache is data, not code. Reject generated RPG escapes that
    // weren't in the original. Also protect carriage returns and line count.
    if((result.match(/\n/g)||[]).length!==(original.match(/\n/g)||[]).length)
        return false;
    if((result.match(/\r/g)||[]).length!==(original.match(/\r/g)||[]).length)
        return false;
    var before=protectedParts(original).filter(function(c){return c.locked;})
        .map(function(c){return c.value;}).join("\u0002");
    var after=protectedParts(result).filter(function(c){return c.locked;})
        .map(function(c){return c.value;}).join("\u0002");
    if(before!==after)return false;
    var words=result.toLowerCase().match(/[a-záéíóúñ]{2,}/g)||[];
    for(var i=5;i<words.length;i++){
        if(words[i]===words[i-3]&&words[i-1]===words[i-4]&&
           words[i-2]===words[i-5])return false;
    }
    return true;
}
function acceptCache(source,original,result,composed,persist){
    if(!validTranslation(source,original,result,!!composed)){
        diskStats.rejected++;return false;
    }
    var key=source+"\u0000"+original;
    if(cache.has(key)&&cache.get(key)===result)return true;
    cache.set(key,result);
    if(cache.size>9000){cache.delete(cache.keys().next().value);}
    if(persist)enqueuePersistentCache({
        schema:CACHE_SCHEMA,source:source,original:original,
        translated:result,composed:!!composed
    });
    return true;
}
function safeCachePath(){
    if(!cacheDir||!cacheFile)return false;
    try{
        var d=fs.lstatSync(cacheDir);
        if(!d.isDirectory()||d.isSymbolicLink())return false;
        var f;
        try{f=fs.lstatSync(cacheFile);}
        catch(e){if(e&&e.code==="ENOENT")return true;return false;}
        return f.isFile()&&!f.isSymbolicLink()&&f.size<=CACHE_LIMIT;
    }catch(_){return false;}
}
function queueFlush(){
    if(!diskReady||diskBusy||!diskQueue.length)return;
    if(!safeCachePath()){diskStats.errors++;diskQueue=[];return;}
    var item=diskQueue.shift(),line=JSON.stringify(item)+"\n";
    if(line.length>6000){diskStats.rejected++;queueFlush();return;}
    diskBusy=true;
    fs.appendFile(cacheFile,line,{encoding:"utf8",mode:0o600},function(err){
        diskBusy=false;
        if(err)diskStats.errors++;
        else diskStats.saved++;
        queueFlush();
    });
}
function enqueuePersistentCache(record){
    if(diskQueue.length>=400){
        diskStats.errors++;return;
    }
    diskQueue.push(record);
    queueFlush();
}
function startPersistentCache(){
    cacheDir=path.join(sidecar,".local","Rpg","cache");
    cacheFile=path.join(cacheDir,"translations-ja-en-es-v2.jsonl");
    function onReady(){
        if(!safeCachePath()){diskStats.errors++;return;}
        loadNameGlossary();
        fs.readFile(cacheFile,"utf8",function(err,data){
            if(err&&err.code!=="ENOENT"){diskStats.errors++;return;}
            if(!err&&typeof data==="string"){
                if(Buffer.byteLength(data,"utf8")>CACHE_LIMIT){
                    diskStats.errors++;return;
                }
                var lines=data.split("\n");
                // A partially-written final line is not a trusted entry.
                for(var i=0;i<lines.length-1&&i<30000;i++){
                    if(!lines[i]||lines[i].length>6000)continue;
                    try{
                        var r=JSON.parse(lines[i]);
                        if(r.schema!==CACHE_SCHEMA||!/^(ja|en)$/.test(r.source)||
                           !validTranslation(r.source,r.original,r.translated,
                               r.composed))continue;
                        var key=r.source+"\u0000"+r.original;
                        if(!cache.has(key)){
                            cache.set(key,r.translated);diskStats.loaded++;
                        }
                    }catch(_){diskStats.rejected++;}
                }
            }
            diskReady=true;queueFlush();
        });
    }
    try{
        var d;
        try{d=fs.lstatSync(cacheDir);}catch(e){
            if(!e||e.code!=="ENOENT")throw e;
        }
        if(d){
            if(!d.isDirectory()||d.isSymbolicLink())throw Error("IA_CACHE_DIR_UNSAFE");
            onReady();
        }else{
            fs.mkdir(cacheDir,0o700,function(e){
                if(e&&e.code!=="EEXIST"){diskStats.errors++;return;}
                onReady();
            });
        }
    }catch(_){diskStats.errors++;}
}

function isJapanese(s){return /[\u3040-\u30ff\u3400-\u9fff]/.test(s||"");}
function languageFor(s){
    if(typeof s!=="string" || s.length===0 || s.length>1800)return null;
    if(isJapanese(s))return "ja";
    // English detection must be conservative: never send player names,
    // numerical menus, short labels, or Spanish text to an English model.
    if(/[áéíóúñ¿¡]/i.test(s) || /[^\x09\x0a\x0d\x20-\x7e]/.test(s))return null;
    var words=s.match(/[A-Za-z']+/g)||[];
    if(words.length<3 || s.trim().length<12)return null;
    if(/\b(?:the|you|are|have|this|that|with|your|where|please|hello|sorry|why|what|when|would|could|should|really|don't|doesn't|isn't|won't|i'm|you're|we're|can't|thank|good|morning)\b/i.test(s))return "en";
    return null;
}
// Never send game control sequences (including character names) to OPUS.
var controlRE=/\\(?:[A-Za-z]{1,12}\[[^\]\r\n]{0,120}\]|[A-Za-z]{1,12}<[^>\r\n]{1,120}>|[A-Za-z]{1,12}\b|[{}!.,|^<>$\\])|\r?\n/g;
function protectedParts(text){
    var chunks=[],position=0,match;
    controlRE.lastIndex=0;
    while((match=controlRE.exec(text))!==null){
        if(match.index>position)chunks.push({value:text.slice(position,match.index),locked:false});
        chunks.push({value:match[0],locked:true});
        position=controlRE.lastIndex;
    }
    if(position<text.length)chunks.push({value:text.slice(position),locked:false});
    return chunks;
}
function translatePreservingControls(source,text){
    var key=source+"\u0000"+text;
    if(cache.has(key))return Promise.resolve(cache.get(key));
    // Separate a native speaker header before OPUS sees any dialogue body.
    // No variable codes, name-entry values or event state are rewritten.
    var speaker=source==="ja"?speakerHeader(text):null;
    if(speaker){
        return translatePreservingControls(source,speaker.body).then(function(out){
            if(!out)return null;
            var name=nameInSpanish(speaker.name)||speaker.name;
            var joint=name+speaker.separator+out;
            return acceptCache(source,text,joint,true,true)?joint:null;
        });
    }
    var chunks=protectedParts(text);
    if(chunks.length===0)return Promise.resolve(null);
    // Reject malformed/unrecognized escapes instead of letting the model change them.
    var rest=chunks.filter(function(c){return !c.locked;}).map(function(c){return c.value;}).join("");
    if(/\\[A-Za-z]/.test(rest))return Promise.resolve(null);
    if(chunks.length===1 && !chunks[0].locked)return translate(source,text);
    return Promise.all(chunks.map(function(chunk){
        if(chunk.locked)return Promise.resolve(chunk.value);
        var before=(chunk.value.match(/^\s*/)||[""])[0];
        var after=(chunk.value.match(/\s*$/)||[""])[0];
        var body=chunk.value.slice(before.length,chunk.value.length-after.length);
        var eligible=source==="ja"?isJapanese(body):
            /[A-Za-z]{2}/.test(body)&&body.length>=8;
        if(!eligible)return Promise.resolve(chunk.value);
        return translate(source,body).then(function(out){
            return out?before+out+after:chunk.value;
        });
    })).then(function(parts){
        var updated=parts.join("");
        if(updated===text)return null;
        if(!acceptCache(source,text,updated,true,true))return null;
        return updated;
    });
}
// Native, cache-first bridge. Never block or restart a message event.
// Short, deterministic RPG UI labels should not require neural inference.
// Game-specific actor readings can be overridden in cache/nombres_es.json;
// do not modify the game's actor database or player-entered name.
var knownUi={
    "持ち物":"Objetos","オプション":"Opciones","セーブ":"Guardar",
    "ゲーム終了":"Salir del juego","キャンセル":"Cancelar",
    "決定":"Aceptar","大事なもの":"Objetos importantes",
    "ニューゲーム":"Nueva partida","コンティニュー":"Continuar",
    "戻る":"Volver","はい":"Sí","いいえ":"No",
    // Exact labels observed in the current MV pilot, never game scripts.
    "商店街へ行こう":"Ir a la zona comercial",
    "タスク手帳":"Agenda de tareas",
    "各キャラのタスクレベルと夏実の心情が確認出来ます。":
        "Consulta las tareas de cada personaje y el estado de ánimo de Natsumi."
};
var knownNames={"夏実":"Natsumi","隼人":"Hayato",
    // Provisional reading for the nameplate in this MV test. Game-local
    // nombres_es.json overrides it without changing a player's save.
    "保林 隼人":"Hobayashi Hayato"};
function nameInSpanish(name){
    return Object.prototype.hasOwnProperty.call(knownNames,name)?
        knownNames[name]:null;
}
function loadNameGlossary(){
    var namesFile=path.join(cacheDir,"nombres_es.json");
    try{
        var info=fs.lstatSync(namesFile);
        if(!info.isFile()||info.isSymbolicLink()||info.size>65536)return;
    }catch(_){return;}
    fs.readFile(namesFile,"utf8",function(err,body){
        if(err||!body||body.length>65536)return;
        try{
            var values=JSON.parse(body);
            if(!values||typeof values!=="object"||Array.isArray(values))return;
            Object.keys(values).forEach(function(k){
                var v=values[k];
                if(k.length>=2&&k.length<=36&&isJapanese(k)&&
                   typeof v==="string"&&v.length>=2&&v.length<=64&&
                   !isJapanese(v)&&!/[\r\n\\<>]/.test(v)){
                    knownNames[k]=v;
                }
            });
        }catch(_){diskStats.errors++;}
    });
}
function speakerHeader(text){
    if(typeof text!=="string"||text.length<5)return null;
    var m=/^([\u3400-\u9fff々\u30a0-\u30ff・ー ]{2,20})(\r?\n)([\s\S]+)$/.exec(text);
    if(m&&isJapanese(m[1])&&isJapanese(m[3]))
        return {name:m[1],separator:m[2],body:m[3]};
    m=/^([\u3400-\u9fff々\u30a0-\u30ff・ー ]{2,20})([「『])([\s\S]+)$/.exec(text);
    if(m&&isJapanese(m[1])&&isJapanese(m[3]))
        return {name:m[1],separator:" "+m[2],body:m[3],
                oldSeparator:m[2]};
    return null;
}
function localizeDate(text){
    var dayNames={月:"lun.",火:"mar.",水:"mié.",木:"jue.",
        金:"vie.",土:"sáb.",日:"dom."};
    var m=/^\s*([0-9０-９]{1,2})月\s*([0-9０-９]{1,2})日\s*[（(]([月火水木金土日])[）)]\s*$/.exec(text);
    var normal=function(v){return v.replace(/[０-９]/g,function(c){
        return String(c.charCodeAt(0)-65296);
    });};
    var pad=function(v){return ("0"+Number(normal(v))).slice(-2);};
    if(m)return pad(m[2])+"/"+pad(m[1])+" ("+dayNames[m[3]]+")";
    m=/^\s*(午前|午後)\s*([0-9０-９]{1,2})時\s*([0-9０-９]{1,2})分\s*$/.exec(text);
    if(m)return pad(m[2])+":"+pad(m[3])+(m[1]==="午前"?" a. m.":" p. m.");
    return null;
}
function translatedNativeLabel(text){
    if(typeof text!=="string"||text.length>450||text.length<2||
       !isJapanese(text))return text;
    if(typeof SceneManager!=="undefined"&&SceneManager._scene){
        var current=SceneManager._scene;
        // Name entry edits the player's save data: never localize that value.
        if(typeof Scene_Name!=="undefined"&&current instanceof Scene_Name)
            return text;
    }
    if(Object.prototype.hasOwnProperty.call(knownUi,text))
        return knownUi[text];
    var time=localizeDate(text);
    if(time)return time;
    var name=nameInSpanish(text);
    if(name)return name;
    var source=languageFor(text);
    if(!source)return text;
    var found=cache.get(source+"\u0000"+text);
    if(typeof found==="string")return found;
    if(state.connected&&pending.size<18){
        translatePreservingControls(source,text).catch(function(){
            state.errors++;
        });
    }
    return text;
}
function hookNativeSurface(){
    if(typeof Window_Base!=="undefined"&&Window_Base.prototype){
        var originalDraw=Window_Base.prototype.drawText;
        if(typeof originalDraw==="function"){
            Window_Base.prototype.drawText=function(){
                var args=Array.prototype.slice.call(arguments);
                if(typeof args[0]==="string")args[0]=translatedNativeLabel(args[0]);
                return originalDraw.apply(this,args);
            };
        }
        var originalEx=Window_Base.prototype.drawTextEx;
        if(typeof originalEx==="function"){
            Window_Base.prototype.drawTextEx=function(){
                var args=Array.prototype.slice.call(arguments);
                if(typeof args[0]==="string")args[0]=translatedNativeLabel(args[0]);
                return originalEx.apply(this,args);
            };
        }
    }
    // Custom windows often bypass Window_Base and draw directly on a Bitmap.
    // Ignore single glyphs from MV's typewriter and never repaint an active UI.
    if(typeof Bitmap!=="undefined"&&Bitmap.prototype&&
       typeof Bitmap.prototype.drawText==="function"){
        var bitmapDraw=Bitmap.prototype.drawText;
        Bitmap.prototype.drawText=function(){
            var args=Array.prototype.slice.call(arguments);
            if(typeof args[0]==="string"&&args[0].length>=2)
                args[0]=translatedNativeLabel(args[0]);
            return bitmapDraw.apply(this,args);
        };
    }
}

function hookMessages(){
    if(typeof Window_Message==="undefined"||!Window_Message.prototype)return;
    var original=Window_Message.prototype.startMessage;
    if(typeof original!=="function")return;
    Window_Message.prototype.startMessage=function(){
        try{
            if(typeof $gameMessage!=="undefined"&&$gameMessage&&
               $gameMessage.hasText&&$gameMessage.hasText()){
                var text=$gameMessage.allText(),source=languageFor(text);
                if(source){
                    var old=cache.get(source+"\u0000"+text);
                    if(typeof old==="string"&&old!==text){
                        $gameMessage._texts=old.split("\n");
                        state.shown++;
                    }else if(state.connected){
                        translatePreservingControls(source,text).catch(function(){
                            state.errors++;
                        });
                    }
                }
            }
        }catch(_){state.errors++;}
        return original.apply(this,arguments);
    };
}
function hookChoices(){
    if(typeof Game_Message==="undefined"||!Game_Message.prototype||
       typeof Game_Message.prototype.setChoices!=="function")return;
    var original=Game_Message.prototype.setChoices;
    Game_Message.prototype.setChoices=function(choices){
        if(!Array.isArray(choices)||!choices.length||choices.length>12)
            return original.apply(this,arguments);
        var translated=choices.slice(),changed=false;
        try{
            for(var i=0;i<choices.length;i++){
                var source=languageFor(choices[i]);
                if(!source)continue;
                var cached=cache.get(source+"\u0000"+choices[i]);
                if(typeof cached==="string"&&cached!==choices[i]){
                    translated[i]=cached;changed=true;
                }else if(state.connected){
                    // A live choice belongs to the author's native UI.
                    translatePreservingControls(source,choices[i]).catch(function(){
                        state.errors++;
                    });
                }
            }
        }catch(_){state.errors++;}
        var args=Array.prototype.slice.call(arguments);
        if(changed){args[0]=translated;state.shown++;}
        return original.apply(this,args);
    };
}
// Read-only, bounded text discovery. Never run game events or parse maps
// synchronously from disk; $dataMap is already loaded by the original engine.
var prefetchedMap=null,prefetchQueue=[],prefetchBusy=false;
function addPrefetch(text){
    var source=languageFor(text);
    if(!source||prefetchQueue.length>=320||
       cache.has(source+"\u0000"+text))return;
    prefetchQueue.push({source:source,text:text});
}
function collectMapText(){
    if(typeof $dataMap==="undefined"||!$dataMap||
       prefetchedMap===$dataMap)return;
    prefetchedMap=$dataMap;prefetchQueue=[];
    var events=$dataMap.events;
    if(!Array.isArray(events))return;
    var count=0;
    for(var i=0;i<events.length&&count<320;i++){
        var event=events[i];
        if(!event||!Array.isArray(event.pages))continue;
        for(var j=0;j<event.pages.length&&count<320;j++){
            var list=event.pages[j].list;
            if(!Array.isArray(list))continue;
            for(var k=0;k<list.length&&count<320;k++){
                var cmd=list[k];
                if(!cmd||!Array.isArray(cmd.parameters))continue;
                if(cmd.code===401){
                    var parts=[String(cmd.parameters[0]||"")];
                    while(k+1<list.length&&list[k+1]&&
                          list[k+1].code===401&&parts.length<4){
                        k++;parts.push(String((list[k].parameters||[])[0]||""));
                    }
                    addPrefetch(parts.join("\n"));count++;
                }else if(cmd.code===102&&Array.isArray(cmd.parameters[0])){
                    var options=cmd.parameters[0];
                    for(var n=0;n<options.length&&count<320;n++){
                        addPrefetch(options[n]);count++;
                    }
                }
            }
        }
    }
    nextPrefetch();
}
function nextPrefetch(){
    if(prefetchBusy||!state.connected||!prefetchQueue.length)return;
    prefetchBusy=true;
    setTimeout(function(){
        if(!state.connected||!prefetchQueue.length){
            prefetchBusy=false;return;
        }
        var item=prefetchQueue.shift();
        translatePreservingControls(item.source,item.text).then(function(){
            prefetchBusy=false;setTimeout(nextPrefetch,45);
        },function(){
            state.errors++;prefetchBusy=false;setTimeout(nextPrefetch,150);
        });
    },30);
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
    IAPanel.prototype.standardPadding=function(){return 14;};
    IAPanel.prototype.lineHeight=function(){return 38;};
    IAPanel.prototype.initialize=function(){
        var w=Math.min(540,Math.max(310,Graphics.boxWidth-22));
        var h=Math.min(428,Math.max(380,(Graphics.boxHeight||720)-20));
        Window_Base.prototype.initialize.call(this,
            Math.max(5,Graphics.boxWidth-w-10),8,w,h);
        this.opacity=228;this.visible=false;this._tick=0;
        this.contents.fontSize=18;this.contents.outlineWidth=2;
        this.refresh();
    };
    IAPanel.prototype.refresh=function(){
        this.contents.clear();
        this.contents.fontSize=18;
        var lines=[
            "IA Traductora · RPG Maker MV",
            "Idioma: Español",
            "Fase: "+state.phase,
            "Motor:",
            state.status,
            "Solicitudes: "+state.requested,
            "Recibidas: "+state.received+"   Mostradas: "+state.shown,
            "Caché cargada: "+diskStats.loaded+"   Guardada: "+diskStats.saved,
            "Errores: "+state.errors+"   Caché: "+diskStats.errors,
            "Cerrar panel: F10"
        ];
        for(var i=0;i<lines.length;i++){
            if(i===4&&lines[i].length>32)this.contents.fontSize=16;
            this.drawText(lines[i],0,i*38,this.contentsWidth(),"left");
            this.contents.fontSize=18;
        }
    };
    var create=Scene_Map.prototype.createAllWindows;
    Scene_Map.prototype.createAllWindows=function(){
        create.apply(this,arguments);
        // Never prevent map startup when a custom UI plugin rejects our HUD.
        try{
            this._iaMini=new IAMini();this.addWindow(this._iaMini);
            this._iaPanel=new IAPanel();this.addWindow(this._iaPanel);
        }catch(_){
            state.errors++;state.status="IA_PANEL_OPCIONAL_INCOMPATIBLE";
            this._iaMini=null;this._iaPanel=null;
        }
    };
    var updateScene=Scene_Map.prototype.update;
    Scene_Map.prototype.update=function(){
        updateScene.apply(this,arguments);
        if(!runtimeActivated){
            runtimeActivated=true;
            try{refreshConnection();}catch(_){state.errors++;}
        }
        if(state.connected){
            try{collectMapText();}catch(_){state.errors++;}
        }
        if(Input.isTriggered("ia-traductora")&&this._iaPanel){
            this._iaPanel.visible=!this._iaPanel.visible;
            this._iaMini.visible=!this._iaPanel.visible;
        }
        if(this._iaPanel && ++this._iaPanel._tick%30===0&&this._iaPanel.visible)this._iaPanel.refresh();
    };
    Input.keyMapper[121]="ia-traductora";
}
try{
    // Keep F10 accessible even if detection or worker startup fails.
    state.phase="F10";setupHud();
    state.phase="RUTA";initPaths();
    // Load verified translations asynchronously before map boot; never
    // hold the game's event loop waiting for a cache or neural result.
    startPersistentCache();
    state.phase="NUCLEO";
    if(!ordinary(path.join(content,"js","rpg_core.js")))
        throw Error("IA_NUCLEO_MV_NO_ENCONTRADO");
    state.phase="MENSAJES";hookMessages();
    state.phase="OPCIONES";hookChoices();
    state.phase="INTERFAZ";hookNativeSurface();
    state.phase="CONEXION";refreshConnection();setInterval(refreshConnection,4500);
    state.phase="ACTIVO";
}catch(_){
    // Show a safe *stage* code instead of a generic exception or private path.
    state.status="IA_INICIO_"+state.phase+"_FALLIDO";
    state.errors++;
}
})();
