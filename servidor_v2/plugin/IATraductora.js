/*:
 * @plugindesc IA Traductora RPG Maker MV — motor local propio, sin cuentas ni nube.
 * @author Servidor
 * @help El instalador Servidor configura el motor local. F10 muestra el estado.
 * No necesita parámetros ni acceso a Internet.
 */
(function () {
"use strict";
var BRAND="IA Traductora";
var BUILD_ID="MV-R3-20261123"; // also checked against the installed package SHA
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
var wireQueue=[],wireBusy=false,wireScheduled=false;
function wireTranslate(source,text){
    if(!state.batch)return request("/translate",{source:source,target:"es",text:text},30000);
    return new Promise(function(resolve,reject){
        wireQueue.push({source:source,text:text,resolve:resolve,reject:reject});
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
    for(var i=0;i<wireQueue.length&&jobs.length<6;){
        if(wireQueue[i].source===first.source)jobs.push(wireQueue.splice(i,1)[0]);
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
function translate(source,text){
    var key=source+"\u0000"+text;
    var fixed=stableDisplay(text,false);
    if(fixed!==null)return Promise.resolve(fixed);
    var existing=cache.get(key);
    if(typeof existing==="string"&&validTranslation(source,text,existing,false))
        return Promise.resolve(existing);
    if(existing!==undefined)cache.delete(key);
    if(pending.has(key))return pending.get(key);
    if(rejectedKeys.has(key)&&rejectedKeys.get(key)>Date.now())return Promise.resolve(null);
    if(pending.size>=96)return Promise.resolve(null);
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
            wireTranslate(source,prepared.text).then(function(r){
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
    if(source==="ja"&&spuriousLaughter(original,result))return false;
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
    if(!validTranslation(source,original,result,!!composed)){
        diskStats.rejected++;return false;
    }
    var key=source+"\u0000"+original;
    if(approvedKeys.has(key)){
        cache.set(key,approvedKeys.get(key));return true;
    }
    if(cache.has(key)&&cache.get(key)===result)return true;
    cache.set(key,result);
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
                        if(r.schema!==CACHE_SCHEMA||!/^(ja|en)$/.test(r.source)||
                           !validTranslation(r.source,r.original,r.translated,r.composed)){
                            diskStats.rejected++;continue;
                        }
                        var key=r.source+"\u0000"+r.original;
                        if(approvedKeys.has(key))continue;
                        if(!cache.has(key)||loadedKeys.has(key)){
                            if(!loadedKeys.has(key))diskStats.loaded++;
                            cache.set(key,r.translated);loadedKeys.set(key,true);
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
var controlRE=/\\(?:[A-Za-z]{1,12}\[[^\]\r\n]{0,120}\]|[A-Za-z]{1,12}<[^>\r\n]{1,120}>|[A-Za-z]{1,12}\b|[{}!.,|^<>$\\])|\x1b(?:[A-Za-z]+\[[0-9]{1,8}\]|[{}!])|%(?:[0-9]{1,3}|[sdf])|\$\{[A-Za-z0-9_]{1,50}\}|\r?\n/g;
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
function translatePreservingControls(source,text){
    var key=source+"\u0000"+text;
    var ready=readyText(source,text);
    if(ready!==null)return Promise.resolve(ready);
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
            return out?before+out+after:null;
        });
    })).then(function(parts){
        if(parts.some(function(p){return p===null;}))return null;
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
    var m=/^デフォルト名は[『「]([^』」\r\n]{1,24})[』」]\s*[（(]([ぁ-ゖァ-ヶー]{1,30})[）)]です[。．.]?$/.exec(text);
    if(m){var first=nameInSpanish(m[1],true);return "El nombre predeterminado es «"+first+"».";}
    m=/^※?\s*苗字は[《〈]([^（(\r\n]{1,24})[（(]([ぁ-ゖァ-ヶー]{1,30})[）)][》〉]で固定です[。．.]?$/.exec(text);
    if(m){var last=nameInSpanish(m[1],true);return "El apellido «"+last+"» es fijo.";}
    if(text==="このキャラクターの名前を決めて下さい。")return "Elige el nombre de este personaje.";
    return localizeDate(text);
}
function cachedPart(source,text){
    var key=source+"\u0000"+text;
    if(approvedKeys.has(key))return approvedKeys.get(key);
    var fixed=stableDisplay(text,false);
    if(fixed!==null)return fixed;
    var old=cache.get(key);
    if(typeof old==="string"){
        if(validTranslation(source,text,old,true))return old;
        cache.delete(key);diskStats.rejected++;
    }
    return null;
}
function readyText(source,text){
    var exact=cachedPart(source,text);
    if(exact!==null)return exact;
    var chunks=protectedParts(text);
    if(chunks.length<=1)return null;
    var changed=false,parts=[];
    for(var i=0;i<chunks.length;i++){
        var c=chunks[i];
        if(c.locked){parts.push(c.value);continue;}
        var before=(c.value.match(/^\s*/)||[""])[0];
        var after=(c.value.match(/\s*$/)||[""])[0];
        var body=c.value.slice(before.length,c.value.length-after.length);
        if(!body||!(source==="ja"?isJapanese(body):/[A-Za-z]{2}/.test(body)&&body.length>=8)){
            parts.push(c.value);continue;
        }
        var result=cachedPart(source,body);
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
function hookNativeSurface(){
    if(typeof Window_Base!=="undefined"&&Window_Base.prototype){
        ["drawText","drawTextEx"].forEach(function(method){
            var original=Window_Base.prototype[method];
            if(typeof original!=="function")return;
            Window_Base.prototype[method]=function(){
                var args=Array.prototype.slice.call(arguments),identity=!!this._iaNameSurface;
                try{
                    if(typeof args[0]==="string"&&!identityDrawDepth)
                        args[0]=translatedNativeLabel(args[0],identity);
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
                    args[0]=translatedNativeLabel(args[0],false);
            }catch(_){state.errors++;}
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
                    var old=readyText(source,text);
                    if(typeof old==="string"&&old!==text){
                        $gameMessage._texts=old.split("\n");
                        state.shown++;
                    }else{
                        if(state.connected)translatePreservingControls(source,text).catch(function(){state.errors++;});
                        else addPrefetch(text,true);
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
                var cached=readyText(source,choices[i]);
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
// Read-only full MV inventory. Never parse plugin source, save files, script
// commands, variable values, filenames, or event conditions as dialogue.
var prefetchedMap=null,discovered=new Map(),priorityQueue=[],prefetchQueue=[];
var initialMapFile="",initialMapScanned=false,initialKeys=new Map(),collectInitial=false;
var scanStats={files:0,totalFiles:0,ready:0,rejected:0,skipped:0,done:false,limited:false};
var scanStarted=false,prefetchBusy=false,MAX_DISCOVERED=40000;
function addPrefetch(text,priority){
    if(typeof text!=="string"||!text)return;
    learnReadings(text);
    var source=languageFor(text);
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
        if(files.length>5000){files=files.slice(0,5000);scanStats.limited=true;}
        function step(){
            if(!files.length||discovered.size>=MAX_DISCOVERED){
                scanStats.done=true;nextPrefetch();return;
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
            return translatePreservingControls(item.source,item.text).then(function(out){
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
        complete:initialMapScanned&&finished===initialKeys.size};
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
    proto.commandNewGame=function(){
        if(this._iaStartGate)return finish(this); // explicit second selection skips
        var info=firstMapProgress();
        if((scanStats.done&&!initialMapFile)||info.complete||!content||
           !this._commandWindow||typeof this._commandWindow.activate!=="function"||
           typeof this.addWindow!=="function"||typeof Window_Base==="undefined")
            return launch.apply(this,arguments);
        try{
            var width=Math.min(560,Graphics.boxWidth||816);
            var win=this._iaTitleProgress;
            if(!win){
                win=new Window_Base();win.initialize(
                    Math.max(0,Math.floor(((Graphics.boxWidth||816)-width)/2)),8,width,124);
                this.addWindow(win);this._iaTitleProgress=win;
            }
            if(typeof win.show==="function")win.show();
            win.visible=true;win.contents.fontSize=18;
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
            this._iaStartGate=null;
            if(this._iaTitleProgress&&typeof this._iaTitleProgress.hide==="function")this._iaTitleProgress.hide();
            return base.apply(this,arguments);
        };
    });
    proto.update=function(){
        var out=update.apply(this,arguments);
        var gate=this._iaStartGate;
        if(!gate)return out;
        try{
            var info=firstMapProgress(),remaining=Math.max(0,Math.ceil((gate.deadline-Date.now())/1000));
            // Never launch a deferred command in a different scene.
            if(typeof SceneManager!=="undefined"&&SceneManager._scene&&SceneManager._scene!==this){
                this._iaStartGate=null;return out;
            }
            if(info.complete||(scanStats.done&&!initialMapFile)||remaining===0||
               (typeof Input!=="undefined"&&Input.isTriggered("cancel"))){finish(this);return out;}
            var label="Textos iniciales: "+info.ready+"/"+info.total+
                " · "+remaining+" s máx.";
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
        var h=Math.min(535,Math.max(340,(Graphics.boxHeight||720)-20));
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
            "Español · "+BUILD_ID,
            "Fase: "+state.phase,
            "Motor:",
            state.status,
            "Solicitudes: "+state.requested,
            "Recibidas: "+state.received+"   Mostradas: "+state.shown,
            "Caché cargada: "+diskStats.loaded+"   Guardada: "+diskStats.saved,
            "Archivos: "+scanStats.files+"/"+scanStats.totalFiles+"   Omitidos: "+scanStats.skipped,
            "Textos listos: "+scanStats.ready+"/"+discovered.size+"   Fallos: "+scanStats.rejected,
            "QA: "+state.qualityRejected+"   Caché revisada: "+diskStats.rejected,
            "Errores: "+state.errors+"   "+(scanStats.limited?"Límite de escaneo":scanStats.done?"Inventario terminado":"Inventario en curso"),
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
    startPersistentCache();
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
