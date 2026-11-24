/*:
 * @plugindesc IA Traductora RPG Maker MV — motor local propio, sin cuentas ni nube.
 * @author Servidor
 * @help El instalador Servidor configura el motor local. F10 muestra el estado.
 * No necesita parámetros ni acceso a Internet.
 */
(function () {
"use strict";
var BRAND="IA Traductora";
var BUILD_ID="MV-R4P4-20261123"; // also checked against the installed package SHA
if(typeof Utils==="undefined" || !Utils.isNwjs || !Utils.isNwjs()) return;
// A missing Node module must never prevent the game itself from booting.
var fs,path,crypto,http,spawn;
try{
    fs=require("fs");path=require("path");crypto=require("crypto");
    http=require("http");spawn=require("child_process").spawn;
}catch(_){return;}
if(typeof Map!=="function"||typeof Promise!=="function")return;
var game="",content="",sidecar="",worker="",descriptorFile="",startupFile="";
var state={connected:false,status:"Comprobando instalación",phase:"INICIO",requested:0,received:0,shown:0,errors:0,qualityRejected:0};
var token="",port=0,starting=false,lastAttempt=0,proc=null;
var runtimeActivated=false,connectionProbe=false,lastStatusProbe=0;
var cache=new Map(),approvedKeys=new Map(),pending=new Map(),rejectedKeys=new Map(),maxWait=45000;
var cacheReadDone=false,identityDrawDepth=0;
var displayMacros=Object.create(null),personColors=Object.create(null);
var cacheDir="",cacheFile="",diskReady=false,diskBusy=false,diskQueue=[];
var diskStats={loaded:0,saved:0,rejected:0,errors:0};
// A cache never includes game assets or saves. The schema is versioned to
// quarantine old, unverified outputs from previous releases.
var CACHE_SCHEMA="ia-traductora-cache-v2",CACHE_LIMIT=64*1024*1024,MAX_CACHE_ENTRIES=50000;
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
        if(payload){headers["Content-Type"]="application/json; charset=utf-8";headers["Content-Length"]=payload.length;}
        var req=http.request({hostname:"127.0.0.1",port:d.port,path:route,
            method:payload?"POST":"GET",headers:headers,timeout:timeout||20000},
            function(res){
                if(res.statusCode!==200){res.resume();var e=Error("IA HTTP "+res.statusCode);e.permanent=res.statusCode===400||res.statusCode===422;reject(e);return;}
                var buffer="",size=0;
                if(typeof res.setEncoding==="function")res.setEncoding("utf8");
                res.on("data",function(chunk){
                    size+=typeof chunk==="string"?Buffer.byteLength(chunk,"utf8"):chunk.length;
                    if(size>65536){req.destroy(Error("Respuesta demasiado grande"));return;}
                    buffer+=typeof chunk==="string"?chunk:chunk.toString("utf8");
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
    // Start only after the original title scene starts (or first map frame).
    // The game is never held waiting for weights, hashing or translation.
    if(!runtimeActivated){state.status="IA espera iniciar juego";return;}
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
    if(connectionProbe)return;
    connectionProbe=true;lastStatusProbe=Date.now();
    request("/status",null,2500).then(function(d){
        if(d.schema!=="ia-traductora-bridge-v1"||d.active!==true)throw Error("Motor no autenticado");
        connectionProbe=false;state.connected=true;state.status="IA local conectada";
        state.qualityRejected=typeof d.quality_rejected==="number"?
            d.quality_rejected:0;
        state.batch=d.batch===true;
        nextPrefetch();
    }).catch(function(){
        connectionProbe=false;state.connected=false;
        state.status=startupCode()||"Esperando IA local";
        startWorker();
    });
}
function prepareNamedDialogue(text,source){
    var output={text:text,needed:[]};
    if(source!=="ja"||!isJapanese(text))return output;
    var keys=Object.keys(knownNames).filter(function(k){return k.length>=2;})
        .sort(function(a,b){return b.length-a.length;});
    // Match in one pass: do not re-replace a substring within a longer name.
    var lookup=Object.create(null),escaped=[];
    keys.forEach(function(k){
        lookup[k]=knownNames[k];
        escaped.push(k.replace(/[.*+?^$()|[\]\\]/g,"\\$&"));
    });
    if(!escaped.length)return output;
    var used=[];
    var rewritten=text.replace(new RegExp(escaped.join("|"),"g"),function(k){
        var reading=lookup[k];
        if(used.indexOf(reading)<0)used.push(reading);
        return " "+reading+" ";
    });
    output.text=rewritten.replace(/[ \t]{2,}/g," ");
    output.needed=used;
    return output;
}
function containsNames(output,expected){
    if(!expected.length)return true;
    var text=String(output||"").toLowerCase();
    for(var i=0;i<expected.length;i++){
        var name=expected[i].toLowerCase();
        var start=text.indexOf(name);
        if(start<0)return false;
        // Avoid counting a name just because it is embedded in another word.
        if(start>0&&/[a-záéíóúñ]/i.test(text.charAt(start-1)))return false;
        var end=start+name.length;
        if(end<text.length&&/[a-záéíóúñ]/i.test(text.charAt(end)))return false;
    }
    return true;
}
// One HTTP batch at a time. Older verified workers still support /translate.
var wireQueue=[],wireBusy=false,wireScheduled=false,foregroundDepth=0;
function wireTranslate(source,text,priority){
    if(!state.batch)return request("/translate",{source:source,target:"es",text:text},30000);
    return new Promise(function(resolve,reject){
        var job={source:source,text:text,resolve:resolve,reject:reject,priority:!!(priority||foregroundDepth)};
        if(job.priority)wireQueue.unshift(job);else wireQueue.push(job);
        if(!wireScheduled&&!wireBusy){
            wireScheduled=true;setTimeout(flushWire,3);
        }
    });
}
function flushWire(){
    wireScheduled=false;
    if(wireBusy||!wireQueue.length)return;
    wireBusy=true;
    var first=wireQueue.shift(),jobs=[first];
    // Bound background batches and never mix them with visible requests.
    var cap=first.priority?6:4;
    for(var i=0;i<wireQueue.length&&jobs.length<cap;){
        if(wireQueue[i].source===first.source&&wireQueue[i].priority===first.priority)jobs.push(wireQueue.splice(i,1)[0]);
        else i++;
    }
    var route=jobs.length===1?"/translate":"/translate_batch";
    var body={source:first.source,target:"es"};
    if(jobs.length===1)body.text=first.text;
    else body.texts=jobs.map(function(v){return v.text;});
    function finish(){
        wireBusy=false;
        if(wireQueue.length){wireScheduled=true;setTimeout(flushWire,3);}
    }
    request(route,body,30000).then(function(answer){
        if(jobs.length===1)jobs[0].resolve(answer);
        else if(answer&&Array.isArray(answer.results)&&answer.results.length===jobs.length){
            for(var j=0;j<jobs.length;j++){
                var result=answer.results[j];
                if(result&&typeof result.translated==="string")jobs[j].resolve(result);
                else{
                    var error=Error("IA batch item rejected");
                    error.permanent=!!(result&&result.permanent);
                    jobs[j].reject(error);
                }
            }
        }else jobs.forEach(function(job){job.reject(Error("IA batch response invalid"));});
        finish();
    },function(error){jobs.forEach(function(job){job.reject(error);});finish();});
}
function translate(source,text,priority){
    priority=!!(priority||foregroundDepth);
    var key=source+"\u0000"+text;
    var fixed=stableDisplay(text,false);
    if(fixed!==null)return Promise.resolve(fixed);
    var existing=repairDisplayTerms(source,text,cache.get(key));
    if(typeof existing==="string"&&validTranslation(source,text,existing,false))
        return Promise.resolve(existing);
    if(existing!==undefined)cache.delete(key);
    if(pending.has(key)){
        if(priority){for(var i=0;i<wireQueue.length;i++){
            if(wireQueue[i].source===source&&wireQueue[i].text===prepareNamedDialogue(text,source).text){var job=wireQueue.splice(i,1)[0];job.priority=true;wireQueue.unshift(job);break;}
        }}
        return pending.get(key);
    }
    if(rejectedKeys.has(key)&&rejectedKeys.get(key)>Date.now())return Promise.resolve(null);
    if(pending.size>=(priority?96:72)){rejectedKeys.set(key,Date.now()+500);return Promise.resolve(null);}
    state.requested++;
    var prepared=prepareNamedDialogue(text,source);
    var raw=new Promise(function(resolve){
        var beginning=Date.now(),attempts=0;
        function stop(permanent){
            rejectedKeys.set(key,permanent?Infinity:Date.now()+60000);
            state.errors++;resolve(null);
        }
        function attempt(){
            if(Date.now()-beginning>maxWait||!state.connected){stop(false);return;}
            attempts++;
            wireTranslate(source,prepared.text,priority).then(function(r){
                if(r&&containsNames(r.translated,prepared.needed)&&
                   acceptCache(source,text,r.translated,false,true)){
                    state.received++;resolve(cache.get(key));
                }else stop(true);
            },function(error){
                if((error&&error.permanent)||attempts>=2){
                    stop(!!(error&&error.permanent));return;
                }
                setTimeout(attempt,800);
            });
        }
        attempt();
    });
    var call=raw.then(function(value){pending.delete(key);return value;},
        function(error){pending.delete(key);throw error;});
    pending.set(key,call);return call;
}

function numbersIn(text){
    var n=String(text).match(/[0-9０-９]+/g)||[];
    return n.map(function(v){return v.replace(/[０-９]/g,function(c){
        return String(c.charCodeAt(0)-65296);
    }).replace(/^0+(?=\d)/,"");}).sort().join("|");
}
function validTranslation(source,original,result,composed){
    if(typeof original!=="string"||typeof result!=="string"||
       !original||!result.trim()||result===original||
       result.length>Math.max(100,Math.min(5400,original.length*5+80))||
       /\uFFFD|\u0000/.test(result)||numbersIn(original)!==numbersIn(result))
        return false;
    var fixed=stableDisplay(original,false);
    if(fixed!==null&&fixed!==result)return false;
    if(source==="ja"&&(spuriousLaughter(original,result)||spuriousApplause(original,result)))return false;
    if(source==="en"&&badEnglishOutput(visibleProse(original),visibleProse(result)))return false;
    if(/(?:\\|\x1b)[NVP]\[[0-9]+\](?=[A-Za-zÁÉÍÓÚÜÑáéíóúüñ])/i.test(result))return false;
    if(source==="ja"){
        var visibleOriginal=protectedParts(original).filter(function(c){return !c.locked;}).map(function(c){return c.value;}).join("");
        if(!containsNames(result,prepareNamedDialogue(visibleOriginal,source).needed))return false;
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
    result=repairDisplayTerms(source,original,result);
    if(!validTranslation(source,original,result,!!composed)){
        diskStats.rejected++;return false;
    }
    var key=source+"\u0000"+original;
    rejectedKeys.delete(key);
    if(approvedKeys.has(key)){
        cache.set(key,approvedKeys.get(key));return true;
    }
    if(cache.has(key)&&cache.get(key)===result)return true;
    cache.set(key,result);indexDisplayAlias(source,original,result);
    if(typeof discovered!=="undefined"&&discovered.has(key)){
        var item=discovered.get(key);
        if(item.status!=="ready"){
            if(item.status==="rejected")scanStats.rejected--;
            item.status="ready";scanStats.ready++;
        }
    }
    if(cache.size>MAX_CACHE_ENTRIES){cache.delete(cache.keys().next().value);}
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
    function finish(ok){
        cacheReadDone=true;diskReady=ok;queueFlush();nextPrefetch();
    }
    function onReady(){
        if(!safeCachePath()){diskStats.errors++;finish(false);return;}
        loadNameGlossary();loadApprovedTranslations();
        fs.readFile(cacheFile,"utf8",function(err,data){
            if(err&&err.code!=="ENOENT"){diskStats.errors++;finish(false);return;}
            if(err||typeof data!=="string"){finish(true);return;}
            if(Buffer.byteLength(data,"utf8")>CACHE_LIMIT){
                diskStats.errors++;finish(false);return;
            }
            var lines=data.split("\n"),limit=Math.min(lines.length-1,100000);
            var at=0,loadedKeys=new Map();
            // Recover only explicit author-provided kana readings, then audit
            // prior results. Do not delete or rewrite the existing journal.
            function learnSlice(){
                var end=Math.min(at+400,limit);
                for(;at<end;at++){
                    try{if(lines[at].length<=6000){
                        var r=JSON.parse(lines[at]);if(typeof r.original==="string")learnReadings(r.original);
                    }}catch(_){}
                }
                if(at<limit)setTimeout(learnSlice,0);
                else{at=0;loadSlice();}
            }
            function loadSlice(){
                var end=Math.min(at+400,limit);
                for(;at<end;at++){
                    if(!lines[at]||lines[at].length>6000)continue;
                    try{
                        var r=JSON.parse(lines[at]);
                        r.translated=repairDisplayTerms(r.source,r.original,r.translated);
                        if(r.schema!==CACHE_SCHEMA||!/^(ja|en)$/.test(r.source)||
                           !validTranslation(r.source,r.original,r.translated,r.composed)){
                            diskStats.rejected++;continue;
                        }
                        var key=r.source+"\u0000"+r.original;
                        if(approvedKeys.has(key))continue;
                        if(!cache.has(key)||loadedKeys.has(key)){
                            if(!loadedKeys.has(key))diskStats.loaded++;
                            cache.set(key,r.translated);indexDisplayAlias(r.source,r.original,r.translated);loadedKeys.set(key,true);
                            if(cache.size>MAX_CACHE_ENTRIES)cache.delete(cache.keys().next().value);
                        }
                    }catch(_){diskStats.rejected++;}
                }
                if(at<limit)setTimeout(loadSlice,0);else finish(true);
            }
            learnSlice();
        });
    }
    try{
        var d;
        try{d=fs.lstatSync(cacheDir);}catch(e){if(!e||e.code!=="ENOENT")throw e;}
        if(d){
            if(!d.isDirectory()||d.isSymbolicLink())throw Error("IA_CACHE_DIR_UNSAFE");
            onReady();
        }else fs.mkdir(cacheDir,0o700,function(e){
            if(e&&e.code!=="EEXIST"){diskStats.errors++;finish(false);return;}
            onReady();
        });
    }catch(_){diskStats.errors++;finish(false);}
}

function isJapanese(s){return /[\u3041-\u3096\u30a1-\u30fa\u3400-\u9fff\uff66-\uff9d]/.test(s||"");}
var englishUi={"Yes":"Sí","No":"No","New Game":"Nueva partida","Continue":"Continuar",
    "Options":"Opciones","Save":"Guardar","Load":"Cargar","Cancel":"Cancelar",
    "Items":"Objetos","Equipment":"Equipo","Exit":"Salir","Quit Game":"Salir del juego",
    "Quest":"Misión","Quests":"Misiones","Quest Journal":"Diario de misiones","Main Quests":"Misiones principales","Side Quests":"Misiones secundarias"};
function englishLabel(text){
    return Object.prototype.hasOwnProperty.call(englishUi,text)?englishUi[text]:null;
}
function visibleProse(text){
    return protectedParts(text).filter(function(p){return !p.locked;}).map(function(p){return p.value;}).join("");
}
// Read only explicit, pure-color macro definitions; never execute or expand
// arbitrary author macros. A color is a person marker only if the author
// uses an identity label and no other macro assigns that color another role.
function loadDisplayMacros(){
    if(typeof $plugins==="undefined"||!Array.isArray($plugins))return;
    var roles=Object.create(null);
    $plugins.forEach(function(plugin){
        if(!plugin||!plugin.status||!/^YEP_X_MessageMacros\d+$/.test(plugin.name)||!plugin.parameters)return;
        var p=plugin.parameters;
        for(var i=1;i<=300;i++){
            var name=p["Macro "+i+" Name"],value=p["Macro "+i+" Text"];
            if(typeof name!=="string"||!name.trim()||typeof value!=="string")continue;
            var m=/^\\c\[(\d{1,3})\]$/i.exec(value.trim());if(!m)continue;
            var color=Number(m[1]);if(color>255)continue;
            var key=name.trim().toLowerCase();
            if(!Object.prototype.hasOwnProperty.call(displayMacros,key))displayMacros[key]=color;
            if(!Object.prototype.hasOwnProperty.call(displayMacros,String(i)))displayMacros[String(i)]=color;
            var person=/^(?:people|person|persons|names|characters|npcs|npc)$/.test(key);
            roles[color]=(roles[color]||0)|(person?1:2);
        }
    });
    Object.keys(roles).forEach(function(k){if(roles[k]===1)personColors[k]=true;});
}
function formatColor(code){
    var m=/^(?:\\|\x1b)c\[(\d{1,3})\]$/i.exec(code);
    if(m&&Number(m[1])<=255)return Number(m[1]);
    m=/^(?:\\|\x1b)m\[([A-Za-z0-9 _\-]{1,60})\]$/i.exec(code);
    return m&&Object.prototype.hasOwnProperty.call(displayMacros,m[1].trim().toLowerCase())?
        displayMacros[m[1].trim().toLowerCase()]:null;
}
function protectedPerson(open,value){
    var color=formatColor(open),name=value.trim();
    if(actorNames[name])return name;
    return color!==null&&personColors[color]&&/^[A-Z][A-Za-z0-9'’.-]{0,30}(?:[ \-][A-Z][A-Za-z0-9'’.-]{0,30}){0,4}$/.test(name)&&
        name.length<=75?name:null;
}
function repairDisplayTerms(source,original,result){
    if(source!=="en"||typeof original!=="string"||typeof result!=="string")return result;
    // Only matching paired color/macro spans are repaired. Never change the
    // code, speaker tag, variable or unrelated narrative from the journal.
    var pattern=/(\\(?:c\[\d{1,3}\]|m\[[A-Za-z0-9 _\-]{1,60}\]))([^\\\r\n]+)(\\c\[0\])/gi;
    var expected=[],m;
    while((m=pattern.exec(original))!==null)expected.push([m[1],m[2],m[3]]);
    var at=0;
    result=result.replace(pattern,function(all,open,body,close){
        var e=expected[at++];
        if(!e||e[0]!==open||e[2]!==close)return all;
        var name=protectedPerson(open,e[1]);
        if(name!==null)return open+e[1]+close;
        if(/^\\m\[quests?\]$/i.test(open)&&/^\s*quests?\s*$/i.test(e[1])){
            return open+(/quests/i.test(e[1])?"misiones":"misión")+close;
        }
        return all;
    });
    if(/\bquests?\b/i.test(visibleProse(original))&&
       (/\\m\[quests?\]/i.test(original)||/\b(?:categories|journal|objectives|quest log|main quests|side quests)\b/i.test(visibleProse(original)))){
        result=protectedParts(result).map(function(c){
            return c.locked?c.value:c.value.replace(/\bbúsquedas?\b/gi,function(v){
                var out=/s$/i.test(v)?"misiones":"misión";
                return /^[A-ZÁÉÍÓÚ]/.test(v)?out.charAt(0).toUpperCase()+out.slice(1):out;
            });
        }).join("");
    }
    return result;
}
function languageFor(s){
    if(typeof s!=="string"||!s||s.length>1800)return null;
    if(isJapanese(s))return "ja";
    if(actorNames[s])return null;
    if((typeof questTexts!=="undefined"&&questTexts.has(s))||
       (typeof discovered!=="undefined"&&discovered.has("en\u0000"+s)))return "en";
    var visible=visibleProse(s);
    if(englishLabel(visible.trim())!==null)return "en";
    var prose=visible.replace(/[\u2018\u2019]/g,"'").replace(/[\u201c\u201d]/g,'"')
        .replace(/[\u2010-\u2015]/g,"-").replace(/\u2026/g,"...").replace(/\u00a0/g," ");
    if(/[áéíóúñ¿¡]/i.test(prose)||/[^\x09\x0a\x0d\x20-\x7e]/.test(prose))return null;
    var words=prose.match(/[A-Za-z']+/g)||[];
    if(words.length<2||prose.trim().length<5)return null;
    if(/\b(?:the|you|your|are|have|this|that|with|where|please|hello|sorry|why|what|when|would|could|should|really|don't|doesn't|isn't|won't|i'm|you're|we're|can't|thank|good|morning|and|of|from|into|there|here|was|were|will|must|he|she|they|their|his|her|my|our|is|i|it|him|himself|herself|ourselves|themselves|says|said|keep|moving|writing|looking|always|typical|absurd|enough|stop|listen|leave|wait|come|get|go|back|ready|look|find|help|give|take|bring|open|close|follow)\b/i.test(prose))return "en";
    return null;
}
// Never send game control sequences (including character names) to OPUS.
var controlRE=/\\(?:[A-Za-z]{1,12}\[[^\]\r\n]{0,120}\]|[A-Za-z]{1,12}<[^>\r\n]{1,120}>|[A-Za-z]{1,12}\b|[{}!.,|^<>$\\])|\x1b(?:[A-Za-z]+\[[0-9]{1,8}\]|[{}!])|%(?:[0-9]{1,3}|[sdf])|\$\{[A-Za-z0-9_]{1,50}\}|\r?\n|<\/?[A-Za-z][A-Za-z0-9 _.,:'"=\/#%+\-]{0,100}>|\([A-Za-z]{1,10}:[^()\r\n]{1,100}\)/g;
// Brackets at a segment's edges are presentation, not instructions for OPUS.
// Preserve them byte-for-byte, including an opening/closing bracket on separate
// native lines. Internal punctuation stays in the sentence for grammar.
var OPEN_BRACKETS="(（[［【「『《〈〔";
var CLOSE_BRACKETS=")）]］】」』》〉〕";
function edgeChunks(value){
    var result=[],left=0,right=value.length;
    while(left<right&&OPEN_BRACKETS.indexOf(value.charAt(left))>=0)left++;
    while(right>left&&CLOSE_BRACKETS.indexOf(value.charAt(right-1))>=0)right--;
    if(left)result.push({value:value.slice(0,left),locked:true,literal:true});
    if(right>left)result.push({value:value.slice(left,right),locked:false});
    if(right<value.length)result.push({value:value.slice(right),locked:true,literal:true});
    return result;
}
function protectedParts(text){
    var chunks=[],position=0,match;
    function addProse(value){
        // Keep whitespace exactly; brackets just inside indentation still
        // belong to the visible outer envelope.
        var lead=(value.match(/^[ \t\u3000]*/)||[""])[0];
        var tail=(value.match(/[ \t\u3000]*$/)||[""])[0];
        if(lead.length+tail.length>=value.length){
            if(value)chunks.push({value:value,locked:false});return;
        }
        var center=value.slice(lead.length,value.length-tail.length);
        var parts=edgeChunks(center);
        if(parts.length===1&&!parts[0].locked){chunks.push({value:value,locked:false});return;}
        if(lead)chunks.push({value:lead,locked:false});
        Array.prototype.push.apply(chunks,parts);
        if(tail)chunks.push({value:tail,locked:false});
    }
    controlRE.lastIndex=0;
    while((match=controlRE.exec(text))!==null){
        if(match.index>position)addProse(text.slice(position,match.index));
        chunks.push({value:match[0],locked:true});
        position=controlRE.lastIndex;
    }
    if(position<text.length)addProse(text.slice(position));
    return chunks;
}
function dynamicValue(part){return /^(?:\\|\x1b)[NVP]\[[0-9]+\]$/i.test(part);}
function joinNativeParts(parts){
    var result="";
    for(var i=0;i<parts.length;i++){
        var current=parts[i],previous=i?parts[i-1]:"";
        // Japanese needs no space between a variable and the next word;
        // Spanish does. Never insert inside an escape, color or name tag.
        if((dynamicValue(previous)&&/^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]/.test(current))||
           (dynamicValue(current)&&/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]$/.test(previous)))result+=" ";
        result+=current;
    }
    return result;
}
function spuriousLaughter(original,result){
    return /^\s*[\(\[（【「『]?\s*(?:risas?|jajaja|ja ja ja)\s*[.!…]*\s*[\)\]）】」』]?\s*$/i.test(result)&&
        !/(?:笑|わら|[wｗ]{2,}|(?:あ|は|ふ|へ|え|ひ)[はふへひハフヘヒ]{2,}|ハハ|フフ|へへ|ハッ|フッ)/i.test(original);
}
function spuriousApplause(original,result){
    return /^\s*[\(\[（【「『]?\s*(?:aplausos?|ovaci[oó]n)[.!…\s]*[\)\]）】」』]?\s*$/i.test(result)&&
        !/(?:拍手|喝采|パチパチ|ぱちぱち|万雷)/.test(original);
}
// Standard, unambiguous notice fragments only. No names, game scripts,
// title-specific data or whole-dialogue replacement dictionaries.
// Match complete segments rather than replacing words inside other prose.
function standardNotice(text){
    // Match complete conventional notices, not arbitrary prose. Outer
    // indentation and exact native color controls remain untouched.
    var lead=(text.match(/^[ \t\u3000]*/)||[""])[0];
    var tail=(text.match(/[ \t\u3000]*$/)||[""])[0];
    if(lead.length+tail.length>=text.length)return null;
    var body=text.slice(lead.length,text.length-tail.length);
    if(body==="この物語はフィクションであり、")return lead+"Esta historia es ficticia y"+tail;
    if(body==="実在する人物・団体・その他法律等とは一切関係ありません。")
        return lead+"no tiene relación con personas, organizaciones ni leyes reales."+tail;
    // Native MV accepts lower-case c and ESC-prefixed color controls.
    // Also accept a plain acronym, fullwidth Latin letters, and spacing.
    // Only paired colors (or neither) are permitted; no code is invented.
    var m=/^また、本作では([ \t\u3000]*)((?:\\|\x1b)[Cc]\[\d{1,3}\])?([A-ZＡ-Ｚ](?:[ \t\u3000]*[A-ZＡ-Ｚ]){1,9})((?:\\|\x1b)[Cc]\[\d{1,3}\])?([ \t\u3000]*)要素が含まれております。予めご了承下さい。$/.exec(body);
    if(m&&!!m[2]===!!m[4])
        return lead+"Además, esta obra incluye elementos de tipo "+m[1]+(m[2]||"")+m[3]+(m[4]||"")+m[5]+". Tenlo en cuenta."+tail;
    return null;
}
function badEnglishOutput(original,result){
    if(/[<>]/.test(result)&&!/[<>]/.test(original))return true;
    if(/word\s*wrap|wordwordwrap/i.test(result)&&!/word\s*wrap/i.test(original))return true;
    var sw=original.match(/[A-Za-z']+/g)||[],words=result.toLowerCase().match(/[a-záéíóúüñ]+/g)||[];
    if(result.length>Math.max(48,original.length*2.8+24)||words.length>Math.max(12,sw.length*2.5+6))return true;
    for(var i=2;i<words.length;i++)if(words[i]===words[i-1]&&words[i]===words[i-2])return true;
    return false;
}
// A context-preserving formatting plan for ordinary color/macro spans.
// If the translated span cannot be aligned unambiguously, fail back to
// the original segment path, never move or invent a control.
function englishFormatPlan(text){
    var parts=protectedParts(text),plain="",spans=[],prefix="",suffix="",active=null,seen=false;
    if(parts.length<2||text.indexOf("\n")>=0)return null;
    for(var i=0;i<parts.length;i++){
        var p=parts[i],v=p.value;
        if(!p.locked){plain+=v;if(v.trim())seen=true;if(active)active.text+=v;continue;}
        if(!seen&&!active&&(/^<[A-Za-z][A-Za-z .'\-]{0,48}>$/i.test(v)||
            /^\\n[cr]?<[^\\<>\r\n]{1,75}>$/i.test(v))){prefix+=v;continue;}
        if(!active&&/^<\/wordwrap>$/i.test(v)&&i===parts.length-1){suffix+=v;continue;}
        if(!active&&/^(?:\\|\x1b)(?:c\[\d+\]|m\[[A-Za-z][A-Za-z0-9 _\-]{0,60}\])$/i.test(v)&&!/^(?:\\|\x1b)c\[0\]$/i.test(v)){active={open:v,text:"",close:""};continue;}
        if(active&&/^(?:\\|\x1b)c\[0\]$/i.test(v)&&active.text.trim()){active.close=v;active.person=protectedPerson(active.open,active.text);spans.push(active);active=null;continue;}
        return null;
    }
    if(active||!plain.trim()||(!prefix&&!suffix&&!spans.length))return null;
    return {plain:plain,prefix:prefix,suffix:suffix,spans:spans};
}
function renderEnglishPlan(plan,whole,spanValues){
    var out="",cursor=0,lower=whole.toLowerCase();
    for(var i=0;i<plan.spans.length;i++){
        var v=spanValues[i];if(typeof v!=="string"||!v.trim())return null;
        v=v.trim();var needle=v.toLowerCase(),at=lower.indexOf(needle,cursor);
        if(at<0||lower.indexOf(needle,at+needle.length)>=0)return null;
        if((at>0&&/[A-Za-zÀ-ÿ]/.test(whole.charAt(at-1)))||
           (at+v.length<whole.length&&/[A-Za-zÀ-ÿ]/.test(whole.charAt(at+v.length))))return null;
        out+=whole.slice(cursor,at)+plan.spans[i].open+whole.slice(at,at+v.length)+plan.spans[i].close;
        cursor=at+v.length;
    }
    return plan.prefix+out+whole.slice(cursor)+plan.suffix;
}
function englishPlanReady(text,plan){
    var whole=cachedPart("en",plan.plain);if(whole===null)return null;
    var values=plan.spans.map(function(span){var k=span.text.trim();return span.person!==null&&span.person!==undefined?span.person:actorNames[k]?k:cachedPart("en",k);});
    if(values.some(function(x){return x===null;}))return null;
    var out=renderEnglishPlan(plan,whole,values);
    return out&&acceptCache("en",text,out,true,true)?cache.get("en\u0000"+text):null;
}
function englishPlanTranslate(text,plan,priority){
    var tasks=[translate("en",plan.plain,priority)];
    plan.spans.forEach(function(span){var k=span.text.trim();tasks.push(span.person!==null&&span.person!==undefined?Promise.resolve(span.person):actorNames[k]?Promise.resolve(k):translate("en",k,priority));});
    return Promise.all(tasks).then(function(values){
        if(values.some(function(v){return v===null;}))return null;
        var out=renderEnglishPlan(plan,values[0],values.slice(1));
        return out&&acceptCache("en",text,out,true,true)?cache.get("en\u0000"+text):null;
    });
}
function hasProse(source,text){return source==="ja"?hasJapaneseProse(text):/[A-Za-z]{2}/.test(visibleProse(text))&&!actorNames[text];}

function translatePreservingControls(source,text,skipPlan,priority){
    priority=!!(priority||foregroundDepth);
    var key=source+"\u0000"+text;
    var ready=readyText(source,text);
    if(ready!==null)return Promise.resolve(ready);
    var plan=source==="en"&&!skipPlan?englishFormatPlan(text):null;
    if(plan)return englishPlanTranslate(text,plan,priority).then(function(out){
        return out!==null?out:translatePreservingControls(source,text,true,priority);
    });
    // Separate a native speaker header before OPUS sees any dialogue body.
    // No variable codes, name-entry values or event state are rewritten.
    var speaker=source==="ja"?speakerHeader(text):null;
    if(speaker){
        return translatePreservingControls(source,speaker.body,false,priority).then(function(out){
            if(!out)return null;
            var name=nameInSpanish(speaker.name)||speaker.name;
            var joint=name+speaker.separator+out;
            return acceptCache(source,text,joint,true,true)?joint:null;
        });
    }
    if((source==="ja"||source==="en")&&text.indexOf("\n")>=0){
        var lines=text.split(/(\r?\n)/);
        // Prefer complete line keys so reviewed text and color spans
        // remain available even when another line needs neural inference.
        return Promise.all(lines.map(function(line,index){
            return index%2||!hasProse(source,line)?Promise.resolve(line):
                translatePreservingControls(source,line,false,priority);
        })).then(function(parts){
            if(parts.some(function(part){return part===null;})){
                var retryAt=0;
                for(var i=0;i<parts.length;i++){
                    if(parts[i]!==null)continue;
                    var until=rejectedKeys.get(source+"\u0000"+lines[i]);
                    if(until&&until!==Infinity&&until>Date.now())retryAt=Math.max(retryAt,until);
                }
                if(retryAt)rejectedKeys.set(key,retryAt);
                return null;
            }
            var merged=parts.join("");
            if(merged===text||!acceptCache(source,text,merged,true,true))return null;
            return cache.get(key);
        });
    }
    var chunks=protectedParts(text);
    if(chunks.length===0)return Promise.resolve(null);
    // Reject malformed/unrecognized escapes instead of letting the model change them.
    var rest=chunks.filter(function(c){return !c.locked;}).map(function(c){return c.value;}).join("");
    if(/\\[A-Za-z]/.test(rest))return Promise.resolve(null);
    if(chunks.length===1 && !chunks[0].locked)return translate(source,text,priority);
    return Promise.all(chunks.map(function(chunk,index){
        if(chunk.locked)return Promise.resolve(chunk.value);
        if(source==="en"&&index>0&&index+1<chunks.length&&/^(?:\\|\x1b)c\[0\]$/i.test(chunks[index+1].value)&&protectedPerson(chunks[index-1].value,chunk.value)!==null)return Promise.resolve(chunk.value);
        var before=(chunk.value.match(/^\s*/)||[""])[0];
        var after=(chunk.value.match(/\s*$/)||[""])[0];
        var body=chunk.value.slice(before.length,chunk.value.length-after.length);
        var eligible=source==="ja"?isJapanese(body):
            /[A-Za-z]{2}/.test(body)&&!actorNames[body];
        if(!eligible)return Promise.resolve(chunk.value);
        return translate(source,body,priority).then(function(out){
            return out?before+out+after:null;
        });
    })).then(function(parts){
        if(parts.some(function(p){return p===null;})){
            // A composite must not be marked permanently failed just
            // because one of its fragments hit a temporary queue limit.
            var retryAt=0;
            for(var i=0;i<parts.length;i++){
                if(parts[i]!==null)continue;
                var until=rejectedKeys.get(source+"\u0000"+chunks[i].value.trim());
                if(until&&until!==Infinity&&until>Date.now())retryAt=Math.max(retryAt,until);
            }
            if(retryAt)rejectedKeys.set(key,retryAt);
            return null;
        }
        var updated=joinNativeParts(parts);
        if(updated===text)return null;
        if(!acceptCache(source,text,updated,true,true))return null;
        return cache.get(key);
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
var knownNames=Object.create(null),ownerNames=Object.create(null),actorNames=Object.create(null);
knownNames["夏実"]="Natsumi";knownNames["隼人"]="Hayato";
knownNames["保林 隼人"]="Hobayashi Hayato";knownNames["保林"]="Hobayashi";
// Kana readings supplied by the game are evidence; do not invent kanji readings.
// Basic Hepburn transliteration for explicit hiragana/katakana name readings.
function romanizeKana(value){
    var raw=String(value).replace(/[\u30a1-\u30f6]/g,function(c){
        return String.fromCharCode(c.charCodeAt(0)-96);
    });
    var kana="あいうえおかきくけこがぎぐげござじずぜぞさしすせそたちつてとだぢづでどなにぬねのはひふへほばびぶべぼぱぴぷぺぽまみむめもやゆよらりるれろわをん";
    var latin=("a i u e o ka ki ku ke ko ga gi gu ge go za ji zu ze zo sa shi su se so ta chi tsu te to da ji zu de do na ni nu ne no ha hi fu he ho ba bi bu be bo pa pi pu pe po ma mi mu me mo ya yu yo ra ri ru re ro wa o n").split(" ");
    // Ensure both arrays have identical length; reject unsupported symbols.
    var pairs={"きゃ":"kya","きゅ":"kyu","きょ":"kyo","ぎゃ":"gya","ぎゅ":"gyu","ぎょ":"gyo",
        "しゃ":"sha","しゅ":"shu","しょ":"sho","じゃ":"ja","じゅ":"ju","じょ":"jo",
        "ちゃ":"cha","ちゅ":"chu","ちょ":"cho","にゃ":"nya","にゅ":"nyu","にょ":"nyo",
        "ひゃ":"hya","ひゅ":"hyu","ひょ":"hyo","びゃ":"bya","びゅ":"byu","びょ":"byo",
        "ぴゃ":"pya","ぴゅ":"pyu","ぴょ":"pyo","みゃ":"mya","みゅ":"myu","みょ":"myo",
        "りゃ":"rya","りゅ":"ryu","りょ":"ryo"};
    if(!raw||raw.length>30||kana.length!==latin.length)return null;
    var out="",doubleNext=false;
    for(var i=0;i<raw.length;i++){
        var ch=raw.charAt(i);
        if(ch==="っ"){if(doubleNext)return null;doubleNext=true;continue;}
        if(ch==="ー"){var vowel=out.match(/[aeiou]$/);if(!vowel)return null;out+=vowel[0];continue;}
        var pair=raw.slice(i,i+2),part;
        if(pairs[pair]){part=pairs[pair];i++;}
        else{var index=kana.indexOf(ch);if(index<0)return null;part=latin[index];}
        if(doubleNext){
            if(!/^[bcdfghjklmnpqrstvwxyz]/.test(part))return null;
            out+=(part.indexOf("ch")===0?"t":part.charAt(0));doubleNext=false;
        }
        out+=part;
    }
    if(doubleNext||!out)return null;
    return out.charAt(0).toUpperCase()+out.slice(1);
}
function learnReadings(text){
    if(typeof text!=="string")return;
    var patterns=[
        /デフォルト名は[『「]([^』」\r\n]{1,24})[』」]\s*[（(]([ぁ-ゖァ-ヶー]{1,30})[）)]/g,
        /苗字は[《〈]([^（(\r\n]{1,24})[（(]([ぁ-ゖァ-ヶー]{1,30})[）)][》〉]/g
    ];
    for(var j=0;j<patterns.length;j++){
        var m;
        while((m=patterns[j].exec(text))!==null){
            var name=m[1].trim(),reading=romanizeKana(m[2]);
            if(name&&reading&&!ownerNames[name])knownNames[name]=reading;
        }
    }
}
function roleLabel(text){
    var m=/^(?:モブ)?(男子?|女子?)?(?:生徒|学生)\s*([Ａ-ＺA-Z])?$/.exec(text);
    if(m){
        var suffix=m[2]||"";
        if(/[Ａ-Ｚ]/.test(suffix))suffix=String.fromCharCode(suffix.charCodeAt(0)-65248);
        return "Estudiante"+(suffix?" "+suffix:"");
    }
    return null;
}
function nameInSpanish(name,identity){
    if(typeof name!=="string"||!name||name.length>100)return null;
    if(Object.prototype.hasOwnProperty.call(knownNames,name))return knownNames[name];
    var role=roleLabel(name);if(role!==null)return role;
    // The last part may be a user-entered name; never feed it to OPUS.
    var m=/^([^\s]+)([ \u3000]+)(.+)$/.exec(name);
    if(m&&Object.prototype.hasOwnProperty.call(knownNames,m[1])&&
       (identity||/^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'\-]{0,47}$/.test(m[3])))
        return knownNames[m[1]]+m[2]+m[3];
    if(identity||actorNames[name]){
        if(/^[ぁ-ゖァ-ヶー]{2,30}$/.test(name))return romanizeKana(name)||name;
        return name;
    }
    return null;
}
function stableDisplay(text,identity){
    if(typeof text!=="string"||!text)return null;
    // Game-defined name setup instructions can be reconstructed without a
    // neural model. Preserve selected values and the original event controls.
    learnReadings(text);
    var name=nameInSpanish(text,identity);
    if(name!==null)return name;
    if(Object.prototype.hasOwnProperty.call(knownUi,text))return knownUi[text];
    var label=englishLabel(text);if(label!==null)return label;
    var notice=standardNotice(text);if(notice!==null)return notice;
    var m=/^デフォルト名は[『「]([^』」\r\n]{1,24})[』」]\s*[（(]([ぁ-ゖァ-ヶー]{1,30})[）)]です[。．.]?$/.exec(text);
    if(m){var first=nameInSpanish(m[1],true);return "El nombre predeterminado es «"+first+"».";}
    m=/^※?\s*苗字は[《〈]([^（(\r\n]{1,24})[（(]([ぁ-ゖァ-ヶー]{1,30})[）)][》〉]で固定です[。．.]?$/.exec(text);
    if(m){var last=nameInSpanish(m[1],true);return "El apellido «"+last+"» es fijo.";}
    if(text==="このキャラクターの名前を決めて下さい。")return "Elige el nombre de este personaje.";
    return localizeDate(text);
}
// Only aliases with exactly equivalent presentation codes. Never infer
// an alias for executable or dynamic controls.
var formatAliases=new Map();
function canonicalDisplay(text){
    if(typeof text!=="string"||text.length>1800||!/(?:\\|\x1b)[cmi]\[/i.test(text))return null;
    var raw=protectedParts(text),keys=[],codes=[];
    for(var i=0;i<raw.length;i++){
        var p=raw[i],v=p.value;
        if(!p.locked){keys.push(v);continue;}
        var color=formatColor(v),token;
        if(color!==null)token="C:"+color;
        else if(/^(?:\\|\x1b)i\[\d{1,4}\]$/i.test(v))token="I:"+Number(v.match(/\d+/)[0]);
        else if(/^<\/?wordwrap>$/i.test(v)||/^\\n[cr]?<[^\\<>\r\n]{1,75}>$/i.test(v)||p.literal||/^\r?\n$/.test(v))token=v;
        else return null;
        keys.push("\u0001"+token+"\u0001");codes.push(v);
    }
    return {key:keys.join(""),codes:codes};
}
function indexDisplayAlias(source,text,result){
    if(source!=="en")return;
    var alias=canonicalDisplay(text);
    if(!alias)return;
    if(formatAliases.size>=MAX_CACHE_ENTRIES&&!formatAliases.has(alias.key))return;
    formatAliases.set(alias.key,{original:text,result:result});
}
function aliasDisplay(source,text){
    if(source!=="en")return null;
    var alias=canonicalDisplay(text);if(!alias)return null;
    var old=formatAliases.get(alias.key);if(!old||old.original===text)return null;
    var at=0,out=protectedParts(old.result).map(function(p){return p.locked?alias.codes[at++]:p.value;}).join("");
    if(at!==alias.codes.length)return null;
    out=repairDisplayTerms(source,text,out);
    return validTranslation(source,text,out,true)?out:null;
}
function cachedPart(source,text){
    var key=source+"\u0000"+text;
    if(approvedKeys.has(key))return approvedKeys.get(key);
    var fixed=stableDisplay(text,false);
    if(fixed!==null)return fixed;
    var old=repairDisplayTerms(source,text,cache.get(key));
    if(typeof old==="string"){
        if(validTranslation(source,text,old,true))return old;
        cache.delete(key);diskStats.rejected++;
    }
    var alias=aliasDisplay(source,text);
    if(alias!==null&&acceptCache(source,text,alias,true,true))return cache.get(key);
    return null;
}
function hasJapaneseProse(text){
    return protectedParts(text).some(function(part){
        return !part.locked&&isJapanese(part.value);
    });
}
function readyText(source,text){
    var exact=cachedPart(source,text);
    if(exact!==null)return exact;
    var plan=source==="en"?englishFormatPlan(text):null;
    if(plan){var rendered=englishPlanReady(text,plan);if(rendered!==null)return rendered;}
    // The scanner stores native full lines as well as message blocks.
    // Reuse a translated whole line (including inline colors) before
    // splitting it into shorter fragments. Existing exact hits win.
    if((source==="ja"||source==="en")&&text.indexOf("\n")>=0){
        var lines=text.split(/(\r?\n)/),complete=true,translatedAny=false;
        for(var n=0;n<lines.length;n+=2){
            if(!hasProse(source,lines[n]))continue;
            var line=readyText(source,lines[n]);
            if(line===null){complete=false;break;}
            if(line!==lines[n])translatedAny=true;
            lines[n]=line;
        }
        if(complete&&translatedAny){
            var whole=lines.join("");
            if(acceptCache(source,text,whole,true,true))return cache.get(source+"\u0000"+text);
        }
    }
    var chunks=protectedParts(text);
    if(chunks.length<=1)return null;
    var changed=false,parts=[];
    for(var i=0;i<chunks.length;i++){
        var c=chunks[i];
        if(c.locked){parts.push(c.value);continue;}
        var before=(c.value.match(/^\s*/)||[""])[0];
        var after=(c.value.match(/\s*$/)||[""])[0];
        var body=c.value.slice(before.length,c.value.length-after.length);
        if(!body||!(source==="ja"?isJapanese(body):/[A-Za-z]{2}/.test(body)&&!actorNames[body])){
            parts.push(c.value);continue;
        }
        var result=source==="en"&&i>0&&i+1<chunks.length&&/^(?:\\|\x1b)c\[0\]$/i.test(chunks[i+1].value)&&protectedPerson(chunks[i-1].value,c.value)!==null?body:cachedPart(source,body);
        if(result===null)return null;
        if(result!==body)changed=true;
        parts.push(before+result+after);
    }
    if(!changed)return null;
    var joined=joinNativeParts(parts);
    return acceptCache(source,text,joined,true,true)?cache.get(source+"\u0000"+text):null;
}
function loadApprovedTranslations(){
    // Exact, owner-reviewed sentences can repair ambiguous OPUS phrasing.
    // Optional file stays inside this game's private cache directory.
    var filename=path.join(cacheDir,"traducciones_aprobadas_es.json");
    try{
        var info=fs.lstatSync(filename);
        if(!info.isFile()||info.isSymbolicLink()||info.size>131072)return;
    }catch(_){return;}
    fs.readFile(filename,"utf8",function(err,body){
        if(err||!body||body.length>131072)return;
        try{
            var values=JSON.parse(body);
            if(!values||typeof values!=="object"||Array.isArray(values))return;
            var keys=Object.keys(values);
            if(keys.length>1400)return;
            keys.forEach(function(original){
                var translated=values[original],lang=languageFor(original);
                if(!lang||!validTranslation(lang,original,translated,true))return;
                var key=lang+"\u0000"+original;
                approvedKeys.set(key,translated);
                cache.set(key,translated);
            });
        }catch(_){diskStats.errors++;}
    });
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
                if(k.length>=1&&k.length<=36&&isJapanese(k)&&
                   typeof v==="string"&&v.length>=2&&v.length<=64&&
                   !isJapanese(v)&&!/[\r\n\\<>]/.test(v)){
                    knownNames[k]=v;ownerNames[k]=true;
                }
            });
        }catch(_){diskStats.errors++;}
    });
}
function speakerHeader(text){
    if(typeof text!=="string"||text.length<5)return null;
    var m=/^([\u3400-\u9fff々\u30a0-\u30ff・ー ]{2,20})(\r?\n)([\s\S]+)$/.exec(text);
    if(m&&nameInSpanish(m[1],false)!==null&&isJapanese(m[3]))
        return {name:m[1],separator:m[2],body:m[3]};
    m=/^([\u3400-\u9fff々\u30a0-\u30ff・ー ]{2,20})([「『])([\s\S]+)$/.exec(text);
    if(m&&nameInSpanish(m[1],false)!==null&&isJapanese(m[3]))
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
function translatedNativeLabel(text,identity){
    if(typeof text!=="string"||text.length>1800||!isJapanese(text))return text;
    if(typeof SceneManager!=="undefined"&&SceneManager._scene&&
       typeof Scene_Name!=="undefined"&&SceneManager._scene instanceof Scene_Name){
        // Only the literal buttons, never the name-entry keyboard/value.
        return text==="決定"?"Aceptar":text==="キャンセル"?"Cancelar":text;
    }
    if(identity)return nameInSpanish(text,true)||text;
    var source=languageFor(text);
    if(!source)return text;
    var found=readyText(source,text);
    if(found!==null)return found;
    if(state.connected&&pending.size<18){
        translatePreservingControls(source,text).catch(function(){state.errors++;});
    }
    return text;
}
function isQuestWindow(win){
    return !!(win&&win.constructor&&/^Window_Quest(?:Data|Title|List|Category|Info|Detail|Journal|Help|Command)/.test(win.constructor.name||""));
}
// Match only known quest labels/titles on nonstandard bitmap-based journals.
// Decoration and numeric counters remain the author's original characters.
// The author's category format can include a color prefix, count and
// expansion marker. Keep them, even when the caption itself is short.
function questEnvelope(text){
    var lead=(text.match(/^(?:(?:\\|\x1b)(?:[ci]\[\d{1,4}\]|[{}])|<\/?wordwrap>|[ \t])*/i)||[""])[0];
    var rest=text.slice(lead.length);
    var tail=(rest.match(/(?:(?:\\|\x1b)(?:c\[\d{1,3}\]|[{}])|<\/wordwrap>|[ \t])*$/i)||[""])[0];
    return {lead:lead,body:rest.slice(0,rest.length-tail.length),tail:tail};
}
function questCachedLabel(text,scoped){
    if(typeof text!=="string"||text.length>1800||actorNames[text])return null;
    var e=questEnvelope(text);
    var m=/^([ \t+\-–—]*)(.*?)([ \t]*(?:\(\d{1,6}\)|\[\d{1,6}\])?[ \t]*)$/.exec(e.body);
    if(!m||!m[2])return null;
    var value=m[2];
    if(!scoped&&/^(?:From|Location|Level|Castle|Forest|Village|Town|Close)$/.test(value))return null;
    var translated=Object.prototype.hasOwnProperty.call(questLabels,value)?questLabels[value]:null;
    if(translated===null&&questTexts.has(value))translated=readyText(questTexts.get(value),value);
    return translated!==null&&translated!==value?e.lead+m[1]+translated+m[3]+e.tail:null;
}
function queueQuest(win,source,text){
    if(!state.connected){addPrefetch(text,true,source);return;}
    var requests=win._iaQuestRequests||(win._iaQuestRequests=new Map());
    if(requests.has(text)||requests.size>=24)return;
    var scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
    requests.set(text,true);
    requestVisible(source,text).then(function(result){
        requests.delete(text);
        if(typeof result!=="string"||!scene||win._iaQuestRefreshTimer)return;
        win._iaQuestRefreshTimer=setTimeout(function(){
            win._iaQuestRefreshTimer=null;
            if(SceneManager._scene!==scene||!win.parent||win.visible===false||win.openness===0||
               typeof win.refresh!=="function"||win.refresh.length!==0)return;
            try{
                var index=typeof win.index==="function"?win.index():null;
                var row=typeof win.topRow==="function"?win.topRow():null;
                win.refresh();
                if(index!==null&&win.index()!==index&&typeof win.select==="function")win.select(index);
                if(row!==null&&win.topRow()!==row&&typeof win.setTopRow==="function")win.setTopRow(row);
            }catch(_){state.errors++;}
        },100);
    },function(){requests.delete(text);});
}
function questLine(win,text){
    if(!text.trim()||text.length>1800)return text;
    var label=questCachedLabel(text,true);if(label!==null)return label;
    var e=questEnvelope(text),body=e.body;
    // Do not ask a language model to translate the quest giver's identity.
    var header=/^(From|Location|Level|Description|Objectives|Rewards|Difficulty):([ \t]*)(.*)$/i.exec(body);
    if(header){
        var k=header[1].charAt(0).toUpperCase()+header[1].slice(1).toLowerCase();
        var fixed=k==="Difficulty"?"Dificultad":questLabels[k];
        if(!fixed)return text;
        var value=header[3];
        if(value&&k!=="From"){
            var v=questCachedLabel(value,true),source=questSource(value);
            if(v!==null)value=v;
            else if(source){
                var found=readyText(source,value);
                if(found!==null)value=found;else queueQuest(win,source,value);
            }
        }
        return e.lead+fixed+":"+header[2]+value+e.tail;
    }
    var source=questSource(body);
    if(!source||!body)return text;
    var found=readyText(source,body);
    if(found!==null)return e.lead+found+e.tail;
    queueQuest(win,source,body);
    return text;
}
function questDraw(win,text){
    // QuestDataFormat joins many fields with <br>, native newlines and
    // font size controls. Translate the visible fields separately; never
    // hand the assembled layout or the name of a giver to the model.
    if(text.length<=16000&&/\r?\n|<br\s*\/?>/i.test(text)){
        var pieces=text.split(/(\r?\n|<br\s*\/?>)/i);
        if(pieces.length<=240)return pieces.map(function(piece,i){
            return i%2?piece:questLine(win,piece);
        }).join("");
        return text;
    }
    return questLine(win,text);
}
function isAmbientWindow(win){
    var name=win&&win.constructor&&win.constructor.name;
    if(!name||! /^(?:Window_GalvCaption|Window_Gab(?:Window)?)$/.test(name)||typeof $plugins==="undefined"||!Array.isArray($plugins))return false;
    return $plugins.some(function(p){
        return p&&p.status&&((p.name==="GALV_TimedMessagePopups"&&name==="Window_GalvCaption")||
            (p.name==="YEP_GabWindow"&&/^Window_Gab(?:Window)?$/.test(name)));
    });
}
function ambientDraw(win,method,args,original){
    var text=args[0],source=null,found=null,epoch=(win._iaCaptionEpoch||0)+1;
    win._iaCaptionEpoch=epoch;
    try{
        source=languageFor(text);
        if(source)found=readyText(source,text);
    }catch(_){state.errors++;}
    if(found!==null){args[0]=found;ambientStats.shown++;}
    // Invoke the author's native draw exactly once, even if IA fails.
    var out=original.apply(win,args);
    if(!source||found!==null)return out;
    try{
    if(!state.connected){addPrefetch(text,true);return out;}
    var scene=typeof SceneManager!=="undefined"?SceneManager._scene:null,b=win.contents;
    var x=Number(args[1]),y=Number(args[2]),h=typeof win.lineHeight==="function"?win.lineHeight():(b&&b.fontSize||24)+8;
    var ticket=null;
    // Only an existing caption's one text region; ignore unknown layout,
    // measurement-only calls, and anything containing executable controls.
    if(method==="drawTextEx"&&scene&&win.parent&&b&&nativeRenderParts(text)&&
       integer(b.width)&&integer(b.height)&&b.width<=4096&&b.height<=512&&
       isFinite(x)&&isFinite(y)&&x>=0&&y>=0&&x<b.width&&y<b.height&&h>=8&&h<=128&&
       typeof b.clearRect==="function"&&typeof b.blt==="function"&&typeof win.textColor==="function"){
        var style={};nativeStyleKeys.forEach(function(k){if(b[k]!==undefined)style[k]=b[k];});
        if(typeof win.normalColor==="function")style.textColor=win.normalColor();
        ticket={geometry:{bitmap:b,x:Math.floor(x),y:Math.floor(y),line:Math.ceil(h),
            width:b.width,height:b.height,style:style},result:null};
    }
    ambientStats.requested++;
    requestVisible(source,text).then(function(result){
        if(!ticket||typeof result!=="string"||!validTranslation(source,text,result,true)||
           win._iaCaptionEpoch!==epoch||SceneManager._scene!==scene||
           win.contents!==b||!win.parent||win.visible===false||win.openness===0)return;
        ticket.result=result;
        if(replaceNativeMessage(win,ticket)){ambientStats.shown++;state.shown++;}
    },function(){state.errors++;});
    }catch(_){state.errors++;}
    return out;
}
function withQuestGlyphs(bitmap,text,draw){
    var font=bitmap&&bitmap.fontFace;
    // Some handwritten fonts map accented glyphs to blank spaces. Use a
    // local legible face for Spanish accented text in configured journal
    // fonts only; never change strings, save data, or the global font.
    if(typeof font!=="string"||!questFontFaces[font.toLowerCase()]||
       typeof text!=="string"||!/[áéíóúüñÁÉÍÓÚÜÑ¿¡]/.test(text))return draw();
    bitmap.fontFace="Georgia, serif";
    try{return draw();}finally{bitmap.fontFace=font;}
}
function hookNativeSurface(){
    if(typeof Window_Base!=="undefined"&&Window_Base.prototype){
        ["drawText","drawTextEx"].forEach(function(method){
            var original=Window_Base.prototype[method];
            if(typeof original!=="function")return;
            Window_Base.prototype[method]=function(){
                var args=Array.prototype.slice.call(arguments),identity=!!this._iaNameSurface;
                if(!identity&&!identityDrawDepth&&!this._iaOwnSurface&&typeof args[0]==="string"&&isAmbientWindow(this)){
                    return ambientDraw(this,method,args,original);
                }
                try{
                    if(typeof args[0]==="string"&&!identityDrawDepth&&!this._iaOwnSurface){
                        if(!identity&&isQuestWindow(this))args[0]=questDraw(this,args[0]);
                        else {var bookLabel=!identity?questCachedLabel(args[0]):null;
                            args[0]=bookLabel!==null?bookLabel:translatedNativeLabel(args[0],identity);}
                        if(!identity&&!isQuestWindow(this)&&typeof Window_Message!=="undefined"&&!(this instanceof Window_Message)&&
                           !(typeof Scene_Name!=="undefined"&&typeof SceneManager!=="undefined"&&SceneManager._scene instanceof Scene_Name)&&
                           languageFor(args[0])==="en"){
                            var cachedEnglish=readyText("en",args[0]);
                            if(cachedEnglish!==null)args[0]=cachedEnglish;
                        }
                    }
                }catch(_){state.errors++;}
                if(identity)identityDrawDepth++;
                try{return original.apply(this,args);}
                finally{if(identity)identityDrawDepth--;}
            };
        });
    }
    // The author's name window is created as a subwindow of Window_Message.
    // Mark that instance, not an arbitrary class or all Japanese short labels.
    if(typeof Window_Message!=="undefined"&&Window_Message.prototype){
        var create=Window_Message.prototype.createSubWindows;
        if(typeof create==="function")Window_Message.prototype.createSubWindows=function(){
            var result=create.apply(this,arguments);
            try{
                var win=this._nameWindow;
                if(win&&!win._iaNameSurface){
                    win._iaNameSurface=true;
                    // Adapt the display-only value before the author's window
                    // computes its width. Never modify Game_Actor.name().
                    var set=win.setText;
                    if(typeof set==="function")win.setText=function(value){
                        var args=Array.prototype.slice.call(arguments);
                        if(typeof value==="string")args[0]=nameInSpanish(value,true)||value;
                        return set.apply(this,args);
                    };
                }
            }catch(_){}
            return result;
        };
    }
    if(typeof Bitmap!=="undefined"&&Bitmap.prototype&&typeof Bitmap.prototype.drawText==="function"){
        var bitmapDraw=Bitmap.prototype.drawText;
        Bitmap.prototype.drawText=function(){
            var args=Array.prototype.slice.call(arguments);
            try{
                if(!identityDrawDepth&&typeof args[0]==="string"&&args[0].length>=2)
                    {var label=questCachedLabel(args[0]);args[0]=label!==null?label:translatedNativeLabel(args[0],false);}
            }catch(_){state.errors++;}
            var bitmap=this;return withQuestGlyphs(bitmap,args[0],function(){return bitmapDraw.apply(bitmap,args);});
        };
        var measure=Bitmap.prototype.measureTextWidth;
        if(typeof measure==="function")Bitmap.prototype.measureTextWidth=function(text){
            var bitmap=this,args=arguments;return withQuestGlyphs(bitmap,text,function(){return measure.apply(bitmap,args);});
        };
    }
}

function readyIndependentLines(source,text){
    if((source!=="ja"&&source!=="en")||text.indexOf("\n")<0||speakerHeader(text))return null;
    // This narrow fallback is for ordinary prose and color formatting only.
    // Do not touch identity, variable, icon, timing or plugin control blocks.
    if(protectedParts(text).some(function(part){
        return part.locked&&!part.literal&&
            !/^(?:\r?\n|(?:\\|\x1b)[Cc]\[\d{1,3}\])$/.test(part.value);
    }))return null;
    var lines=text.split(/(\r?\n)/),changed=false,missing=false;
    for(var i=0;i<lines.length;i+=2){
        var original=lines[i];
        if(!hasProse(source,original))continue;
        var result=readyText(source,original);
        if(result!==null&&result!==original&&validTranslation(source,original,result,true)){
            lines[i]=result;changed=true;
        }else missing=true;
    }
    return changed&&missing?lines.join(""):null;
}
function requestVisible(source,text){
    foregroundDepth++;try{return translatePreservingControls(source,text,false,true);}finally{foregroundDepth--;}
}
// A late answer is presentation only. Never repeat native message start,
// mutate an active text state, consume input or restart story execution.
// Translate in the original native message bitmap, never in another window.
// The late renderer accepts only simple, demonstrably presentation-only
// content. All script/variable/choice/event state stays with the game.
var lateStats={shown:0,requested:0,unsupported:0};
function hideLate(win){win._iaLateTicket=null;}
function nativeRenderParts(text){
    if(typeof text!=="string"||text.length>1800)return null;
    var re=/<\/?wordwrap>|\\n[cr]?<[^\\<>\r\n]{1,75}>|(?:\\|\x1b)(?:c\[\d{1,3}\]|m\[[A-Za-z0-9 _\-]{1,60}\]|i\[\d{1,4}\])|\r?\n|<br>/gi;
    var parts=[],flat="",at=0,m,color=null,seen=false;
    function prose(value){
        if(/[\\\x1b<>|\f]/.test(value))return false;
        if(value){parts.push({text:value,color:color});flat+=value;if(value.trim())seen=true;}
        return true;
    }
    while((m=re.exec(text))!==null){
        if(!prose(text.slice(at,m.index)))return null;
        var code=m[0];at=re.lastIndex;
        if(/^\\n[cr]?</i.test(code)){if(seen)return null;continue;}
        if(/^<\/?wordwrap>$/i.test(code))continue;
        if(/^(?:\r?\n|<br>)$/i.test(code)){parts.push({text:"\n",color:color});flat+="\n";continue;}
        var icon=/^(?:\\|\x1b)i\[(\d{1,4})\]$/i.exec(code);
        if(icon){var id=Number(icon[1]);if(id>4095)return null;
            parts.push({text:"\uFFFC",color:color,icon:id});flat+="\uFFFC";seen=true;continue;}
        color=formatColor(code);if(color===null)return null;
    }
    if(!prose(text.slice(at))||!flat.trim())return null;
    return {parts:parts,flat:flat};
}
function plainCompare(text){return text.replace(/\s+/g," ").trim();}
var nativeStyleKeys=["fontFace","fontSize","fontBold","fontItalic","textColor","outlineColor","outlineWidth","paintOpacity"];
function snapshotMessage(win,ticket){
    var ts=win._textState,b=win.contents;
    if(!ts||!b||typeof ts.text!=="string"||!integer(ts.index)||ts.index!==0||
       !integer(b.width)||!integer(b.height)||b.width>4096||b.height>2048||
       typeof b.clearRect!=="function"||typeof b.blt!=="function"||
       typeof win.textColor!=="function")return;
    var original=nativeRenderParts(ticket.displayed),native=nativeRenderParts(ts.text);
    if(!original||!native||plainCompare(original.flat)!==plainCompare(native.flat))return;
    // Native plugin conversion can change a macro or text alignment.
    // Require the same visible color runs, not merely the same words.
    function signature(parsed){
        return parsed.parts.filter(function(x){return x.text.trim();})
            .map(function(x){return String(x.color)+":"+plainCompare(x.text)+(x.icon!==undefined?":"+x.icon:"");}).join("\u0002");
    }
    if(signature(original)!==signature(native))return;
    var x=typeof ts.x==="number"?ts.x:ts.left,y=ts.y,h=ts.height;
    if(!isFinite(x)||!isFinite(y)||!isFinite(h)||x<0||y<0||h<8||h>128||
       x>=b.width||y>=b.height)return;
    var style={};
    nativeStyleKeys.forEach(function(k){if(b[k]!==undefined)style[k]=b[k];});
    ticket.geometry={bitmap:b,x:Math.floor(x),y:Math.floor(y),line:Math.ceil(h),
        width:b.width,height:b.height,style:style,original:native.flat};
}
function planNativeWords(parsed,bitmap,win,geometry){
    var words=[],word=[],space=false;
    function flush(){
        if(word.length){words.push({runs:word,space:space});word=[];space=false;}
    }
    for(var i=0;i<parsed.parts.length;i++){
        var part=parsed.parts[i];
        if(part.icon!==undefined){word.push(part);continue;}
        var pieces=part.text.match(/\n|[ \t]+|[^\n \t]+/g)||[];
        pieces.forEach(function(t){
            if(t==="\n"){flush();words.push({line:true});space=false;}
            else if(/^[ \t]+$/.test(t)){flush();space=true;}
            else word.push({text:t,color:part.color});
        });
    }
    flush();
    var left=geometry.x,top=geometry.y,line=geometry.line,
        width=geometry.width-left,height=geometry.height-top,ops=[],x=0,y=0;
    if(width<=0||height<line)return null;
    var gap=bitmap.measureTextWidth(" ");
    for(var j=0;j<words.length;j++){
        var w=words[j];if(w.line){x=0;y+=line;continue;}
        var lengths=w.runs.map(function(r){return r.icon!==undefined?36:bitmap.measureTextWidth(r.text);});
        if(lengths.some(function(v){return !isFinite(v)||v<0;}))return null;
        var total=lengths.reduce(function(a,b){return a+b;},0),pad=x&&w.space?gap:0;
        if(total>width)return null;
        if(x+pad+total>width){x=0;y+=line;pad=0;}
        if(y+line>height)return null;
        x+=pad;
        for(var k=0;k<w.runs.length;k++){
            var r=w.runs[k],c=r.color===null?geometry.style.textColor:win.textColor(r.color);
            if(typeof c!=="string")return null;
            ops.push({text:r.text,x:x,y:y,w:Math.max(1,Math.ceil(lengths[k])+4),color:c,icon:r.icon});
            x+=lengths[k];
        }
    }
    return ops.length?ops:null;
}
function replaceNativeMessage(win,ticket){
    var g=ticket.geometry,b=win.contents,parsed=nativeRenderParts(ticket.result);
    if(!g||b!==g.bitmap||b.width!==g.width||b.height!==g.height||!parsed||
       typeof Bitmap!=="function")return false;
    // Never clear a face or nameplate. The native text starts to the right
    // of its face. Stage both the new render and a rollback copy offscreen.
    var margin=Math.max(2,Math.ceil(Number(g.style.outlineWidth)||0)+1),
        x=Math.max(0,g.x-margin),y=g.y,w=g.width-x,h=g.height-y;
    if(w*h>4096*2048||w<=0||h<=0)return false;
    var stage=null,backup=null,changed=false,opacity=b.paintOpacity;
    try{
        stage=new Bitmap(w,h);backup=new Bitmap(w,h);
        if(typeof stage.measureTextWidth!=="function"||typeof stage.drawText!=="function"||typeof backup.blt!=="function")return false;
        nativeStyleKeys.forEach(function(k){if(g.style[k]!==undefined)stage[k]=g.style[k];});
        var ops=planNativeWords(parsed,stage,win,g);
        if(!ops)return false; // no clipping; leave native original untouched
        var icons=null;
        if(ops.some(function(op){return op.icon!==undefined;})){
            if(typeof ImageManager==="undefined"||typeof ImageManager.loadSystem!=="function"||g.line<32)return false;
            icons=ImageManager.loadSystem("IconSet");
            if(!icons||typeof icons.isReady!=="function"||!icons.isReady()||icons.width<512||
                ops.some(function(op){return op.icon!==undefined&&(Math.floor(op.icon/16)+1)*32>icons.height;}))return false;
        }
        identityDrawDepth++;
        try{
            ops.forEach(function(op){
                stage.textColor=op.color;
                if(op.icon!==undefined)stage.blt(icons,(op.icon%16)*32,Math.floor(op.icon/16)*32,32,32,op.x+g.x-x+2,op.y+Math.floor((g.line-32)/2));
                else stage.drawText(op.text,op.x+g.x-x,op.y,op.w,g.line,"left");
            });
        }finally{identityDrawDepth--;}
        backup.blt(b,x,y,w,h,0,0);
        b.paintOpacity=255;changed=true;b.clearRect(x,y,w,h);
        b.blt(stage,0,0,w,h,x,y);
        return true;
    }catch(_){
        if(changed&&backup){try{b.clearRect(x,y,w,h);b.blt(backup,0,0,w,h,x,y);}catch(__){}}
        return false;
    }finally{
        b.paintOpacity=opacity;
        [stage,backup].forEach(function(v){if(v&&typeof v.destroy==="function")try{v.destroy();}catch(_){}});
    }
}
function displayLate(win){
    var ticket=win._iaLateTicket;if(!ticket)return;
    if(typeof SceneManager==="undefined"||!ticket.scene||SceneManager._scene!==ticket.scene||
       typeof $gameMessage==="undefined"||$gameMessage!==ticket.message||
       !$gameMessage.hasText()||$gameMessage.allText()!==ticket.displayed){
        hideLate(win);return;
    }
    if(!ticket.result||ticket.drawn||!win.pause||win._textState||
       (typeof win.isAnySubWindowActive==="function"&&win.isAnySubWindowActive())||
       (typeof $gameMessage.isChoice==="function"&&$gameMessage.isChoice()))return;
    ticket.drawn=true;
    if(ticket.pages<=1&&replaceNativeMessage(win,ticket)){state.shown++;lateStats.shown++;}
    else lateStats.unsupported++;
}
function hookMessages(){
    if(typeof Window_Message==="undefined"||!Window_Message.prototype)return;
    var proto=Window_Message.prototype,original=proto.startMessage;
    if(typeof original!=="function")return;
    proto.startMessage=function(){
        hideLate(this);
        try{
            if(typeof $gameMessage!=="undefined"&&$gameMessage&&$gameMessage.hasText&&$gameMessage.hasText()){
                var text=$gameMessage.allText(),source=languageFor(text);
                if(source){
                    var old=readyText(source,text);
                    if(typeof old==="string"&&old!==text){
                        $gameMessage._texts=old.split("\n");state.shown++;
                    }else{
                        var partial=readyIndependentLines(source,text);
                        if(partial!==null)$gameMessage._texts=partial.split("\n");
                        var win=this,ticket=null;
                        if(source==="en"&&nativeRenderParts(text)){
                            ticket={message:$gameMessage,displayed:$gameMessage.allText(),
                                scene:typeof SceneManager!=="undefined"?SceneManager._scene:null,
                                result:null,drawn:false,pages:0,geometry:null};
                            win._iaLateTicket=ticket;lateStats.requested++;
                        }
                        if(state.connected)requestVisible(source,text).then(function(result){
                            if(ticket&&win._iaLateTicket===ticket&&typeof result==="string"&&result!==text&&
                               validTranslation(source,text,result,true))ticket.result=result;
                        },function(){state.errors++;});
                        else addPrefetch(text,true);
                    }
                }
            }
        }catch(_){state.errors++;}
        var out=original.apply(this,arguments);
        if(this._iaLateTicket)try{snapshotMessage(this,this._iaLateTicket);}catch(_){hideLate(this);}
        return out;
    };
    var newPage=proto.newPage;
    if(typeof newPage==="function")proto.newPage=function(){
        var t=this._iaLateTicket;if(t)t.pages++;
        return newPage.apply(this,arguments);
    };
    var update=proto.update;
    if(typeof update==="function")proto.update=function(){
        // Apply before native input consumes a final pause. No new window.
        var ticket=this._iaLateTicket;
        if(ticket&&!ticket.result&&state.connected&&ticket.scene&&
           typeof SceneManager!=="undefined"&&SceneManager._scene===ticket.scene&&
           this.pause&&!this._textState){
            try{var candidate=readyText("en",ticket.displayed);
                if(typeof candidate==="string"&&candidate!==ticket.displayed&&validTranslation("en",ticket.displayed,candidate,true))ticket.result=candidate;
            }catch(_){}
        }
        try{displayLate(this);}catch(_){hideLate(this);state.errors++;}
        return update.apply(this,arguments);
    };
    var terminate=proto.terminateMessage;
    if(typeof terminate==="function")proto.terminateMessage=function(){hideLate(this);return terminate.apply(this,arguments);};
    if(typeof Game_Message!=="undefined"&&Game_Message.prototype&&typeof Game_Message.prototype.add==="function"){
        var add=Game_Message.prototype.add;
        Game_Message.prototype.add=function(text){
            var out=add.apply(this,arguments);
            try{
                var source=typeof text==="string"?languageFor(text):null;
                if(source){
                    addPrefetch(text,true);
                    if(state.connected&&pending.size<90)requestVisible(source,text).catch(function(){state.errors++;});
                }
                nextPrefetch();
            }catch(_){state.errors++;}
            return out;
        };
    }
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
                var cached=readyText(source,choices[i]);
                if(typeof cached==="string"&&cached!==choices[i]){
                    translated[i]=cached;changed=true;
                }else if(state.connected){
                    // A live choice belongs to the author's native UI.
                    requestVisible(source,choices[i]).catch(function(){
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
// Read-only full MV inventory. Never parse plugin source, save files, script
// commands, variable values, filenames, or event conditions as dialogue.
var prefetchedMap=null,discovered=new Map(),priorityQueue=[],prefetchQueue=[];
var initialMapFile="",initialMapScanned=false,initialKeys=new Map(),collectInitial=false;
var scanStats={files:0,totalFiles:0,ready:0,rejected:0,skipped:0,done:false,limited:false};
var scanStarted=false,prefetchBusy=false,MAX_DISCOVERED=40000;
var inkStats={detected:false,files:0,candidates:0,excluded:0};
var tableStats={files:0,candidates:0};
var questTexts=new Map(),questStats={records:0,fields:0,ready:0};
var questFontFaces=Object.create(null),ambientStats={requested:0,shown:0};
var commonEventLists=null,commonPrioritySeen=new Map(),commonInitialSeen=new Map(),commonDeferred=new Map();
var questLabels={"Quest":"Misión","Quests":"Misiones","Objectives":"Objetivos","Rewards":"Recompensas",
    "Description":"Descripción","Completed":"Completadas","Failed":"Fallidas","Active":"Activas","All":"Todas",
    "Main Quests":"Misiones principales","Side Quests":"Misiones secundarias","Quest Journal":"Diario de misiones",
    "Available":"Disponibles","All Quests":"Todas las misiones","Tutorial Quests":"Misiones de tutorial",
    "NPC Quests":"Misiones de PNJ","Job Quests":"Misiones de trabajo","Skill Quests":"Misiones de habilidad",
    "Training Quests":"Misiones de entrenamiento","Wizard Quests":"Misiones de mago","Shaman Quests":"Misiones de chamán",
    "Weakness Quests":"Misiones de debilidades","From":"De","Location":"Ubicación","Level":"Nivel",
    "Castle":"Castillo","Forest":"Bosque","Village":"Aldea","Town":"Pueblo","Close":"Cerrar","Journal":"Diario"};
function questSource(text){
    if(typeof text!=="string"||!text.trim()||text.length>1800||actorNames[text])return null;
    return questTexts.get(text)||languageFor(text)||null;
}
function registerQuestText(text){
    if(typeof text!=="string"||!text.trim()||text.length>1800||actorNames[text]||
       /^\s*(?:[=+@]|\d+\s*$|[\[{])/.test(text)||/\\(?:eval|script)\b/i.test(text))return;
    var source=languageFor(text);
    if(!source&&/^[A-Za-z][A-Za-z0-9 .,'!?:\-]{0,79}$/.test(text))source="en";
    if(!source||questTexts.has(text)||questTexts.size>=6000)return;
    questTexts.set(text,source);questStats.fields++;
    addPrefetch(text,false,source);
    // Titles may be drawn by a custom book directly without their color code.
    var plain=text.replace(/^(?:<WordWrap>|\\c\[\d{1,3}\])+/gi,"").trim();
    if(plain!==text&&plain&&!/[\\<>\x1b]/.test(plain))registerQuestText(plain);
}
function questValues(value,depth){
    if(depth>5||value===null||value===undefined)return;
    if(Array.isArray(value)){value.slice(0,250).forEach(function(v){questValues(v,depth+1);});return;}
    if(typeof value!=="string"||value.length>32768||!value.trim())return;
    if(/^\s*["[]/.test(value)){
        try{var parsed=JSON.parse(value);
            if(Array.isArray(parsed)||typeof parsed==="string"&&parsed!==value){
                questValues(parsed,depth+1);return;
            }
        }catch(_){}
    }
    // Explicit display fields only; no executable plugin code or object traversal.
    registerQuestText(value);
}
function scanQuestParameters(done){
    if(typeof $plugins==="undefined"||!Array.isArray($plugins)){done();return;}
    var tasks=[];
    $plugins.forEach(function(plugin){
        if(!plugin||!plugin.status||!/^YEP_(?:QuestJournal|X_MoreQuests\d+)$/.test(plugin.name)||!plugin.parameters)return;
        Object.keys(plugin.parameters).forEach(function(k){
            if(/^Quest \d{1,5}$/.test(k)&&tasks.length<1000)tasks.push(plugin.parameters[k]);
        });
        if(plugin.name==="YEP_QuestJournal"){
            questValues(plugin.parameters["Quest Command"],0);
            ["---Main Menu---","Quest Category Window","Quest List Window","Quest Title Window","Quest Data Window"].forEach(function(key){
                try{
                    var field=JSON.parse(plugin.parameters[key]||"{}");
                    if(typeof field["Font Face"]==="string"&&/^[A-Za-z0-9_ -]{1,80}$/.test(field["Font Face"]))questFontFaces[field["Font Face"].toLowerCase()]=true;
                    ["Available Text","Completed Text","Failed Text","All Text","Cancel Text","Type Order","No Quest Title","No Data Text"].forEach(function(k){
                        if(Object.prototype.hasOwnProperty.call(field,k))questValues(field[k],0);
                    });
                }catch(_){}
            });
        }
    });
    function slice(){
        var cap=12;
        while(tasks.length&&cap--){
            var value=tasks.shift();
            try{
                var entry=typeof value==="string"&&value.length<=65536?JSON.parse(value):value;
                if(!entry||typeof entry!=="object"||Array.isArray(entry))continue;
                questStats.records++;
                ["Title","Type","Difficulty","Location","Description","Objectives List","Rewards List","Subtext"].forEach(function(k){
                    if(Object.prototype.hasOwnProperty.call(entry,k))questValues(entry[k],0);
                });
            }catch(_){}
        }
        nextPrefetch();
        if(tasks.length)setTimeout(slice,0);else done();
    }
    slice();
}
function priorityCommon(id,initial){
    if(!integer(id)||id<=0||id>10000)return;
    if(!commonEventLists){
        if(commonDeferred.size<256)commonDeferred.set(id,!!initial||commonDeferred.get(id));
        return;
    }
    var seen=initial?commonInitialSeen:commonPrioritySeen;
    if(seen.has(id)||seen.size>=256)return;
    seen.set(id,true);
    var row=commonEventLists[id];
    if(!row||!Array.isArray(row.list))return;
    var saved=collectInitial;collectInitial=!!initial;
    try{scanCommands(row.list,true);}finally{collectInitial=saved;}
}

function inkDisplayText(value,choice){
    if(typeof value!=="string"||value.charAt(0)!=="^")return null;
    var raw=value.slice(1);
    // Known shaped display macros: keep the payload as a candidate word.
    // We do NOT execute the macro, change Ink values, or rewrite JSON.
    var spans=[];
    // A numeric currency macro is not executable and its value must survive.
    // Its displayed icon is reconstructed by the native game.
    raw=raw.replace(/\(gp:(\d{1,9})\)/gi,"$1");
    var plain=raw.replace(/\((m[a-z]|gp|ob|ic|wp|stat):([A-Za-z][A-Za-z0-9 '\-]{0,55})\)/gi,function(_,kind,label){
        spans.push(label);return label;
    });
    if(/\([A-Za-z]{1,12}:|\{[^}]*\}|^\s*[A-Za-z_][\w.]*:/.test(plain))return null;
    if(languageFor(plain)!=="en"&&languageFor(plain)!=="ja"&&
       !(choice&&/^[A-Za-z][A-Za-z0-9 .,\'!?\-]{0,79}$/.test(plain)))return null;
    return {text:plain,spans:spans};
}
function walkInkStory(data,done){
    if(!data||!integer(data.inkVersion)||data.inkVersion<18||data.inkVersion>21||!Array.isArray(data.root)){
        scanStats.skipped++;done();return;
    }
    var stack=[{values:data.root,index:0,evalMode:false,tag:false}],visited=0;
    function addContainer(v,mode,tag){
        if(Array.isArray(v))stack.push({values:v,index:0,evalMode:mode,tag:tag});
    }
    function slice(){
        var budget=700;
        while(stack.length&&budget--&&discovered.size<MAX_DISCOVERED&&visited<1500000){
            var f=stack[stack.length-1];
            if(f.index>=f.values.length){stack.pop();continue;}
            var v=f.values[f.index++];visited++;
            if(v==="str"&&f.evalMode&&!f.tag){
                // Only a simple literal string directly consumed by a visible
                // choice point (flags 2/4). Never translate arbitrary eval values.
                var j=f.index,parts=[],size=0;
                while(j<f.values.length&&parts.length<20&&typeof f.values[j]==="string"&&
                      (f.values[j].charAt(0)==="^"||f.values[j]==="\n")){
                    var bit=f.values[j++];parts.push(bit==="\n"?bit:bit.slice(1));size+=bit.length;
                    if(size>1800)break;
                }
                if(parts.length&&size<=1800&&f.values[j]==="/str"){
                    var next=f.values[j+1]==="/ev"?f.values[j+2]:f.values[j+1];
                    if(next&&typeof next==="object"&&!Array.isArray(next)&&
                       typeof next["*"]==="string"&&integer(next.flg)&&(next.flg&6)&&!(next.flg&8)){
                        var label=inkDisplayText("^"+parts.join(""),true);
                        if(label){addPrefetch(label.text,false,"en");inkStats.candidates++;
                            label.spans.forEach(function(x){addPrefetch(x,false,"en");});}
                    }
                }
                continue;
            }
            if(v==="ev"){f.evalMode=true;continue;}
            if(v==="/ev"){f.evalMode=false;continue;}
            if(v==="#"){f.tag=true;continue;}
            if(v==="/#"){f.tag=false;continue;}
            if(typeof v==="string"){
                if(v.charAt(0)!=="^")continue;
                if(f.evalMode||f.tag){inkStats.excluded++;continue;}
                // Output fragments after a dynamic macro value often begin with the
                // closing parenthesis. Also inventory the corresponding visible suffix.
                var item=inkDisplayText(v);
                if(/^\^\)\s+/.test(v)&&f.values[f.index-2]==="/ev"){
                    var suffix=inkDisplayText("^"+v.slice(2).trim());
                    if(suffix)addPrefetch(suffix.text,false);
                }
                if(!item){inkStats.excluded++;continue;}
                inkStats.candidates++;addPrefetch(item.text,false);
                // Individual formatting spans use a dedicated trusted path.
                item.spans.forEach(function(x){addPrefetch(x,false,"en");});
            }else if(Array.isArray(v))addContainer(v,f.evalMode,f.tag);
            else if(v&&typeof v==="object"&&f.index===f.values.length&&!f.evalMode&&!f.tag){
                // Only named child containers; never inspect variable fields,
                // tags, choice targets, list definitions or global declarations.
                Object.keys(v).reverse().forEach(function(k){
                    if(k!=="global decl"&&k!=="#f"&&k!=="#n")addContainer(v[k],false,false);
                });
            }
        }
        if(stack.length&&discovered.size<MAX_DISCOVERED&&visited<1500000){setTimeout(slice,0);return;}
        if(stack.length)scanStats.limited=true;
        inkStats.files++;scanStats.files++;done();
    }
    slice();
}
function regularUnder(base,file,max){
    try{
        var st=fs.lstatSync(file),rel=path.relative(base,fs.realpathSync(file));
        return st.isFile()&&!st.isSymbolicLink()&&st.size<=max&&rel&&
            !path.isAbsolute(rel)&&rel.split(/[\\\/]/).indexOf("..")<0;
    }catch(_){return false;}
}
function directoryUnder(base,dir){
    try{
        var st=fs.lstatSync(dir),rel=path.relative(base,fs.realpathSync(dir));
        return st.isDirectory()&&!st.isSymbolicLink()&&rel&&
            !path.isAbsolute(rel)&&rel.split(/[\\\/]/).indexOf("..")<0;
    }catch(_){return false;}
}
// RFC-4180-style bounded CSV reader. Only a localization table with an
// explicit source column and id/key is accepted. No formulas are evaluated.
function csvRows(raw){
    var rows=[],row=[],cell="",quoted=false,closed=false;
    for(var i=0;i<raw.length;i++){
        var ch=raw.charAt(i);
        if(quoted){
            if(ch==='"'){if(raw.charAt(i+1)==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}
            else cell+=ch;
            continue;
        }
        if(closed&&ch!==","&&ch!=="\r"&&ch!=="\n")return null;
        if(ch==='"'){if(cell)return null;quoted=true;closed=false;continue;}
        if(ch===","){row.push(cell);cell="";closed=false;continue;}
        if(ch==="\r"||ch==="\n"){
            if(ch==="\r"&&raw.charAt(i+1)==="\n")i++;
            row.push(cell);rows.push(row);row=[];cell="";closed=false;
            if(rows.length>25000)return null;
        }else cell+=ch;
    }
    if(quoted)return null;
    if(cell||row.length){row.push(cell);rows.push(row);}
    return rows;
}
function scanLocaleCsv(raw,done){
    var rows=csvRows(raw.replace(/^\uFEFF/,""));
    if(!rows||rows.length<2){scanStats.skipped++;done();return;}
    var header=rows.shift().map(function(v){return v.trim().toLowerCase();});
    var id=header.indexOf("key");if(id<0)id=header.indexOf("id");
    var column=header.indexOf("en");if(column<0)column=header.indexOf("source");
    if(column<0)column=header.indexOf("text");
    if(id<0||column<0){scanStats.skipped++;done();return;}
    var at=0;
    function slice(){
        var end=Math.min(at+200,rows.length);
        for(;at<end&&discovered.size<MAX_DISCOVERED;at++){
            var row=rows[at],value=row[column];
            if(row.length!==header.length||!row[id]||typeof value!=="string"||/^\s*[=+@]/.test(value))continue;
            if(languageFor(value)){tableStats.candidates++;addPrefetch(value,false);}
        }
        if(at<rows.length&&discovered.size<MAX_DISCOVERED){setTimeout(slice,0);return;}
        if(at<rows.length)scanStats.limited=true;
        tableStats.files++;scanStats.files++;done();
    }
    slice();
}
function scanExtraSources(dataDir,done){
    var tasks=[],inkDir=path.join(dataDir,"ink"),localeDir=path.join(dataDir,"localization");
    // main.json is a conventional compiled story, not a source script or
    // test/backup. Additional ambiguous formats are not guessed or executed.
    var main=path.join(inkDir,"main.json");
    if(directoryUnder(dataDir,inkDir)&&regularUnder(inkDir,main,20*1024*1024)){
        inkStats.detected=true;tasks.push({file:main,type:"ink",base:inkDir});
    }
    function run(){
        scanStats.totalFiles+=tasks.length;
        function next(){
            if(!tasks.length||discovered.size>=MAX_DISCOVERED){if(tasks.length)scanStats.limited=true;done();return;}
            var t=tasks.shift();
            if(!regularUnder(t.base,t.file,t.type==="ink"?20*1024*1024:2*1024*1024)){
                scanStats.skipped++;setTimeout(next,0);return;
            }
            fs.readFile(t.file,"utf8",function(err,raw){
                if(err||typeof raw!=="string"){scanStats.skipped++;next();return;}
                try{
                    if(t.type==="ink")walkInkStory(JSON.parse(raw.replace(/^\uFEFF/,"")),next);
                    else scanLocaleCsv(raw,next);
                }catch(_){scanStats.skipped++;next();}
            });
        }
        next();
    }
    if(directoryUnder(dataDir,localeDir)){
        fs.readdir(localeDir,function(err,names){
            if(!err)names.filter(function(n){return /^[A-Za-z0-9_.\-]{1,100}\.csv$/i.test(n);}).sort().slice(0,32).forEach(function(n){
                tasks.push({file:path.join(localeDir,n),type:"csv",base:localeDir});
            });else scanStats.skipped++;
            run();
        });
    }else run();
}

function addPrefetch(text,priority,trustedLang){
    if(typeof text!=="string"||!text)return;
    learnReadings(text);
    var source=languageFor(text)||(trustedLang==="en"&&/^[A-Za-z][A-Za-z0-9 .,\'!?\-]{0,79}$/.test(text)&&!actorNames[text]?"en":null);
    if(!source)return;
    var key=source+"\u0000"+text,item=discovered.get(key);
    if(collectInitial&&initialKeys.size<48)initialKeys.set(key,true);
    if(item){
        if(priority&&item.status==="queued"&&!item.priority){
            item.priority=true;priorityQueue.push(item);
        }
        return;
    }
    if(discovered.size>=MAX_DISCOVERED){scanStats.limited=true;return;}
    item={source:source,text:text,status:"queued",priority:!!priority};
    discovered.set(key,item);
    if(readyText(source,text)!==null){if(item.status!=="ready"){item.status="ready";scanStats.ready++;}return;}
    (priority?priorityQueue:prefetchQueue).push(item);
}
function ambientPayload(text){
    if(typeof text!=="string"||text.length>1800)return null;
    var m=/^GabText\s+(.+)$/i.exec(text);
    if(m)return m[1];
    m=/^CreatePopup\s+\d{1,4}\s+(?:(?:left|right|center)\s+)?(.+)$/i.exec(text);
    return m?m[1]:null;
}
function scanCommands(list,priority){
    if(!Array.isArray(list))return;
    for(var i=0;i<list.length;i++){
        var cmd=list[i];
        if(!cmd||!Array.isArray(cmd.parameters))continue;
        if(cmd.code===401||cmd.code===405){
            var parts=[],code=cmd.code;
            while(cmd&&cmd.code===code&&Array.isArray(cmd.parameters)&&parts.length<4){
                if(typeof cmd.parameters[0]==="string")parts.push(cmd.parameters[0]);
                else break;
                if(i+1>=list.length||!list[i+1]||list[i+1].code!==code||parts.length===4)break;
                cmd=list[++i];
            }
            // Same exact group and component fragments used by native rendering.
            if(parts.length)addPrefetch(parts.join("\n"),priority);
            for(var j=0;j<parts.length;j++)addPrefetch(parts[j],priority);
        }else if(cmd.code===102&&Array.isArray(cmd.parameters[0])){
            cmd.parameters[0].forEach(function(t){addPrefetch(t,priority);});
        }else if(cmd.code===356){
            var caption=ambientPayload(cmd.parameters[0]);if(caption)addPrefetch(caption,priority,"en");
        }else if(cmd.code===117&&priority){
            priorityCommon(cmd.parameters[0],collectInitial);
        }else if(cmd.code===320||cmd.code===324){
            // A name or nickname assignment is identity, not prose.
            var value=cmd.parameters[1];
            if(typeof value==="string"&&value.length<=100)actorNames[value]=true;
        }else if(cmd.code===325)addPrefetch(cmd.parameters[1],priority);
    }
}
function scanMap(data,priority){
    if(!data||!Array.isArray(data.events))return;
    addPrefetch(data.displayName,priority);
    data.events.forEach(function(event){
        if(event&&Array.isArray(event.pages))event.pages.forEach(function(page){
            if(page)scanCommands(page.list,priority);
        });
    });
}
function scanDatabase(name,data){
    if(/^Map\d{3,6}\.json$/.test(name)){
        collectInitial=name===initialMapFile;
        try{scanMap(data,collectInitial);}finally{
            if(collectInitial)initialMapScanned=true;
            collectInitial=false;
        }
        return;
    }
    if(name==="System.json"){
        if(!data||typeof data!=="object")return;
        addPrefetch(data.gameTitle,true);addPrefetch(data.currencyUnit,true);
        var terms=data.terms||{};
        ["basic","commands","params"].forEach(function(k){
            if(Array.isArray(terms[k]))terms[k].forEach(function(v){addPrefetch(v,true);});
        });
        if(terms.messages&&typeof terms.messages==="object")
            Object.keys(terms.messages).forEach(function(k){addPrefetch(terms.messages[k],true);});
        return;
    }
    if(!Array.isArray(data))return;
    if(name==="CommonEvents.json"){
        commonEventLists=data;
        commonDeferred.forEach(function(initial,id){priorityCommon(id,initial);});commonDeferred.clear();
    }
    data.forEach(function(row){
        if(!row||typeof row!=="object")return;
        if(name==="CommonEvents.json"){scanCommands(row.list,false);return;}
        if(name==="Troops.json"){
            if(Array.isArray(row.pages))row.pages.forEach(function(p){if(p)scanCommands(p.list,false);});
            return;
        }
        if(name==="Actors.json"){
            if(typeof row.name==="string"&&row.name.length<=100)actorNames[row.name]=true;
            if(typeof row.nickname==="string"&&row.nickname.length<=100)actorNames[row.nickname]=true;
            addPrefetch(row.profile,true);return;
        }
        ["name","description","message1","message2","message3","message4"].forEach(function(k){
            if(typeof row[k]==="string")addPrefetch(row[k],false);
        });
    });
}
function startFullScan(){
    if(scanStarted||!content)return;scanStarted=true;
    var dataDir=path.join(content,"data");
    if(typeof fs.readdir!=="function"){scanStats.done=true;return;}
    try{
        var st=fs.lstatSync(dataDir);
        if(!st.isDirectory()||st.isSymbolicLink())throw Error("unsafe MV data");
        var relative=path.relative(content,fs.realpathSync(dataDir));
        if(relative!=="data")throw Error("unexpected MV data path");
    }catch(_){scanStats.skipped++;scanStats.done=true;return;}
    fs.readdir(dataDir,function(error,names){
        if(error){scanStats.skipped++;scanStats.done=true;return;}
        var order=["System.json","Actors.json","CommonEvents.json","Items.json",
            "Weapons.json","Armors.json","Skills.json","States.json","Classes.json",
            "Enemies.json","Troops.json"];
        var files=names.filter(function(n){
            return order.indexOf(n)>=0||/^Map\d{3,6}\.json$/.test(n);
        }).sort(function(a,b){
            var i=order.indexOf(a),j=order.indexOf(b);
            return (i<0?99:i)-(j<0?99:j)||a.localeCompare(b);
        });
        scanStats.totalFiles=files.length;
        inkStats.detected=directoryUnder(dataDir,path.join(dataDir,"ink"))&&regularUnder(path.join(dataDir,"ink"),path.join(dataDir,"ink","main.json"),20*1024*1024);
        if(files.length>5000){files=files.slice(0,5000);scanStats.limited=true;}
        function step(){
            if(!files.length||discovered.size>=MAX_DISCOVERED){
                scanQuestParameters(function(){scanExtraSources(dataDir,function(){scanStats.done=true;nextPrefetch();});});return;
            }
            var name=files.shift(),file=path.join(dataDir,name);
            try{
                var st=fs.lstatSync(file);
                if(!st.isFile()||st.isSymbolicLink()||st.size>16*1024*1024)
                    throw Error("unsafe or oversized MV data");
            }catch(_){scanStats.skipped++;setTimeout(step,0);return;}
            fs.readFile(file,"utf8",function(err,raw){
                if(err||typeof raw!=="string"){scanStats.skipped++;setTimeout(step,0);return;}
                try{
                    var data=JSON.parse(raw.replace(/^\uFEFF/,""));
                    if(name==="System.json"&&data&&integer(data.startMapId)&&data.startMapId>0){
                        var first="Map"+("000"+data.startMapId).slice(-Math.max(3,String(data.startMapId).length))+".json";
                        initialMapFile=first;
                        var p=files.indexOf(first);
                        if(p>=0){files.splice(p,1);files.unshift(first);}
                    }
                    scanDatabase(name,data);scanStats.files++;
                }catch(_){scanStats.skipped++;}
                nextPrefetch();setTimeout(step,0);
            });
        }
        step();
    });
}
function collectMapText(){
    if(typeof $dataMap==="undefined"||!$dataMap||prefetchedMap===$dataMap)return;
    prefetchedMap=$dataMap;scanMap($dataMap,true);nextPrefetch();
}
function nextPrefetch(){
    if(prefetchBusy||!state.connected||!cacheReadDone)return;
    if(!priorityQueue.length&&!prefetchQueue.length)return;
    prefetchBusy=true;
    setTimeout(function(){
        if(!state.connected){prefetchBusy=false;return;}
        var jobs=[],cap=state.batch?4:1;
        while(jobs.length<cap&&(priorityQueue.length||prefetchQueue.length)){
            var item=priorityQueue.length?priorityQueue.shift():prefetchQueue.shift();
            if(item.status!=="queued")continue;
            item.status="working";jobs.push(item);
        }
        if(!jobs.length){prefetchBusy=false;return;}
        Promise.all(jobs.map(function(item){
            return translatePreservingControls(item.source,item.text,false,item.priority).then(function(out){
                if(out!==null){if(item.status!=="ready"){item.status="ready";scanStats.ready++;}}
                else if(item.status!=="ready"){
                    // A transport failure is not a permanent linguistic rejection.
                    var retry=rejectedKeys.get(item.source+"\u0000"+item.text);
                    if(!state.connected||(retry&&retry!==Infinity)){
                        item.status="deferred";
                        setTimeout(function(){if(item.status==="deferred"){
                            item.status="queued";(item.priority?priorityQueue:prefetchQueue).push(item);nextPrefetch();
                        }},Math.min(60000,Math.max(1500,(retry||Date.now()+1500)-Date.now()+30)));
                    }else{item.status="rejected";scanStats.rejected++;}
                }
            },function(){
                item.status="rejected";scanStats.rejected++;state.errors++;
            });
        })).then(function(){
            prefetchBusy=false;
            setTimeout(nextPrefetch,state.batch?15:45);
        },function(){prefetchBusy=false;state.errors++;});
    },30);
}
// First-pass preparation is a bounded, optional title-screen wait, never
// a wait inside Game_Interpreter or Window_Message. The title keeps running.
function firstMapProgress(){
    var ready=0,finished=0;
    initialKeys.forEach(function(_,key){
        var item=discovered.get(key);
        if(item&&item.status==="ready"){ready++;finished++;}
        else if(item&&item.status==="rejected")finished++;
    });
    return {ready:ready,finished:finished,total:initialKeys.size,
        complete:initialMapScanned&&finished===initialKeys.size&&(!commonDeferred.size||scanStats.done)&&(!inkStats.detected||scanStats.done)};
}
function hookTitleStart(){
    if(typeof Scene_Title==="undefined"||!Scene_Title.prototype||
       typeof Scene_Title.prototype.start!=="function")return;
    var proto=Scene_Title.prototype,start=proto.start;
    proto.start=function(){
        var out=start.apply(this,arguments);
        if(!runtimeActivated){
            runtimeActivated=true;
            try{startFullScan();refreshConnection();}catch(_){state.errors++;}
        }
        return out;
    };
    var launch=proto.commandNewGame,update=proto.update;
    if(typeof launch!=="function"||typeof update!=="function")return;
    function finish(scene){
        var gate=scene._iaStartGate;
        if(!gate)return;
        scene._iaStartGate=null;
        if(scene._iaTitleProgress&&typeof scene._iaTitleProgress.hide==="function")scene._iaTitleProgress.hide();
        // invoke the original title handler exactly once, with its own arguments
        return launch.apply(scene,gate.args);
    }
    function showPreparation(scene){
        var width=Math.min(720,Graphics.boxWidth||816),x=Math.max(0,Math.floor(((Graphics.boxWidth||816)-width)/2));
        var win=scene._iaTitleProgress;
        if(!win){
            win=new Window_Base(x,8,width,124);win._iaOwnSurface=true;
            if(!win.contents)win.initialize(x,8,width,124);
            scene.addWindow(win);scene._iaTitleProgress=win;
        }
        win.show();win.contents.fontSize=18;return win;
    }
    proto.commandNewGame=function(){
        this._iaTitleMonitor=false;
        if(this._iaStartGate)return finish(this); // explicit second selection skips
        if(this._iaTitleProgress)this._iaTitleProgress.hide();
        var info=firstMapProgress();
        if((scanStats.done&&!initialMapFile)||info.complete||!content||
           !this._commandWindow||typeof this._commandWindow.activate!=="function"||
           typeof this.addWindow!=="function"||typeof Window_Base==="undefined")
            return launch.apply(this,arguments);
        try{
            var win=showPreparation(this);
            this._iaStartGate={deadline:Date.now()+25000,args:Array.prototype.slice.call(arguments),last:""};
            this._commandWindow.activate(); // allow pressing New Game again to skip
            win.contents.clear();
            win.drawText("Preparando textos iniciales · "+BUILD_ID,0,0,win.contentsWidth(),"center");
            win.drawText("Pulsa Nueva partida otra vez para continuar",0,36,win.contentsWidth(),"center");
            return;
        }catch(_){
            this._iaStartGate=null;state.errors++;return launch.apply(this,arguments);
        }
    };
    ["commandContinue","commandOptions"].forEach(function(method){
        var base=proto[method];if(typeof base!=="function")return;
        proto[method]=function(){
            this._iaStartGate=null;this._iaTitleMonitor=false;
            if(this._iaTitleProgress&&typeof this._iaTitleProgress.hide==="function")this._iaTitleProgress.hide();
            return base.apply(this,arguments);
        };
    });
    proto.update=function(){
        var out=update.apply(this,arguments);
        var gate=this._iaStartGate;
        if(!gate){
            try{
                if(typeof Input!=="undefined"&&Input.isTriggered("ia-traductora")){
                    this._iaTitleMonitor=!this._iaTitleMonitor;
                    if(this._iaTitleMonitor)showPreparation(this);
                    else if(this._iaTitleProgress)this._iaTitleProgress.hide();
                }
                if(this._iaTitleMonitor&&this._iaTitleProgress){
                    var label=(scanStats.done?"Inventario completo":"Inventariando")+" · "+scanStats.ready+"/"+discovered.size+" textos listos";
                    var extra="Fallos: "+scanStats.rejected+" · F10: cerrar · Puedes jugar cuando quieras";
                    if(this._iaTitleLabel!==label+extra){
                        this._iaTitleLabel=label+extra;var win=this._iaTitleProgress;win.contents.clear();
                        win.drawText(label,0,0,win.contentsWidth(),"center");
                        win.contents.fontSize=16;win.drawText(extra,0,36,win.contentsWidth(),"center");win.contents.fontSize=18;
                    }
                }
            }catch(_){state.errors++;this._iaTitleMonitor=false;}
            return out;
        }
        try{
            var info=firstMapProgress(),remaining=Math.max(0,Math.ceil((gate.deadline-Date.now())/1000));
            // Never launch a deferred command in a different scene.
            if(typeof SceneManager!=="undefined"&&SceneManager._scene&&SceneManager._scene!==this){
                this._iaStartGate=null;return out;
            }
            if(info.complete||(scanStats.done&&!initialMapFile)||remaining===0||
               (typeof Input!=="undefined"&&Input.isTriggered("cancel"))){finish(this);return out;}
            var label="Inicio: "+info.ready+"/"+info.total+" · Total: "+scanStats.ready+"/"+discovered.size+
                " · "+remaining+" s";
            var win=this._iaTitleProgress;
            if(win&&gate.last!==label){
                gate.last=label;win.contents.clear();
                win.drawText(label,0,0,win.contentsWidth(),"center");
                win.drawText("Nueva partida otra vez: continuar sin esperar",0,36,win.contentsWidth(),"center");
            }
        }catch(_){state.errors++;if(this._iaStartGate)finish(this);}
        return out;
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
        this._iaOwnSurface=true;Window_Base.prototype.initialize.call(this,Graphics.boxWidth-218,7,208,44);
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
        var h=Math.min(535,Math.max(340,(Graphics.boxHeight||720)-20));
        this._iaOwnSurface=true;Window_Base.prototype.initialize.call(this,
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
            "Español · "+BUILD_ID,
            "Fase: "+state.phase,
            "Motor:",
            state.status,
            "Solicitudes: "+state.requested,
            "Recibidas: "+state.received+"   Mostradas: "+state.shown,
            "Caché cargada: "+diskStats.loaded+"   Guardada: "+diskStats.saved,
            "Archivos: "+scanStats.files+"/"+scanStats.totalFiles+"   Omitidos: "+scanStats.skipped+(inkStats.detected?" · Ink":"") ,
            "Textos listos: "+scanStats.ready+"/"+discovered.size+"   Fallos: "+scanStats.rejected,
            "QA: "+state.qualityRejected+"   Caché revisada: "+diskStats.rejected,
            "Errores: "+state.errors+"   "+(scanStats.limited?"Límite de escaneo":scanStats.done?"Inventario terminado":"Inventario en curso"),
            "Misiones: "+questStats.records+" · Redib.: "+lateStats.shown+" · NPC: "+ambientStats.shown+" · F10"
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
            try{startFullScan();refreshConnection();}catch(_){state.errors++;}
        }
        try{collectMapText();}catch(_){state.errors++;}
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
    loadDisplayMacros();startPersistentCache();
    state.phase="NUCLEO";
    if(!ordinary(path.join(content,"js","rpg_core.js")))
        throw Error("IA_NUCLEO_MV_NO_ENCONTRADO");
    state.phase="MENSAJES";hookMessages();
    state.phase="OPCIONES";hookChoices();
    state.phase="INTERFAZ";hookNativeSurface();hookTitleStart();
    state.phase="CONEXION";startFullScan();refreshConnection();setInterval(function(){
        if(!state.connected||Date.now()-lastStatusProbe>=4500)refreshConnection();
    },750);
    state.phase="ACTIVO";
}catch(_){
    // Show a safe *stage* code instead of a generic exception or private path.
    state.status="IA_INICIO_"+state.phase+"_FALLIDO";
    state.errors++;
}
})();
