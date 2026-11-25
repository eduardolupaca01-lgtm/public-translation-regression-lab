/*:
 * @target MV MZ
 * @plugindesc IA Traductora RPG Maker MV/MZ — motor local propio, sin cuentas ni nube.
 * @author Servidor
 * @help El instalador Servidor configura el motor local. F10 muestra el estado.
 * No necesita parámetros ni acceso a Internet.
 */
(function () {
"use strict";
var BRAND="IA Traductora";
var BUILD_ID="RPG-MVMZ-R15-20261125"; // also checked against the installed package SHA
if(typeof Utils==="undefined" || !Utils.isNwjs || !Utils.isNwjs()) return;
var ENGINE_ID=Utils.RPGMAKER_NAME||"MV",isMZ=ENGINE_ID==="MZ";
if(ENGINE_ID!=="MV"&&!isMZ)return;
// A missing Node module must never prevent the game itself from booting.
var fs,path,crypto,http,spawn;
try{
    fs=require("fs");path=require("path");crypto=require("crypto");
    http=require("http");spawn=require("child_process").spawn;
}catch(_){return;}
if(typeof Map!=="function"||typeof Promise!=="function")return;
var game="",content="",sidecar="",worker="",descriptorFile="",startupFile="";
var remNative={detected:false,images:false,configured:false,spanish:new Set(),fallback:new Map()};
var state={connected:false,status:"Comprobando instalación",phase:"INICIO",requested:0,received:0,shown:0,errors:0,qualityRejected:0};
var token="",port=0,starting=false,lastAttempt=0,proc=null;
var runtimeActivated=false,connectionProbe=false,lastStatusProbe=0;
var cache=new Map(),approvedKeys=new Map(),pending=new Map(),rejectedKeys=new Map(),maxWait=45000;
var cacheReadDone=false,identityDrawDepth=0;
var displayMacros=Object.create(null),personColors=Object.create(null);
var cacheDir="",cacheFile="",diskReady=false,diskBusy=false,diskQueue=[],diskRetryAt=0,diskNeedsSeparator=false;
var diskStats={loaded:0,saved:0,rejected:0,errors:0};
// A cache never includes game assets or saves. The schema is versioned to
// quarantine old, unverified outputs from previous releases.
var CACHE_SCHEMA="ia-traductora-cache-v2",CACHE_LIMIT=64*1024*1024,MAX_CACHE_ENTRIES=50000;
// NW.js versions resolve index.html and Game.exe differently. Detect only an
// actual MV root by checking its original files; never trust a guessed path.
function engineAt(folder){
    var js=path.join(folder,"js"),mv=ordinary(path.join(js,"rpg_core.js")),mz=ordinary(path.join(js,"rmmz_core.js"));
    if(mv&&mz)return "AMBIGUOUS";
    if(!ordinary(path.join(js,"plugins.js")))return "";
    if(mz){
        if(!["rmmz_managers.js","rmmz_objects.js","rmmz_scenes.js","rmmz_windows.js"].every(function(n){return ordinary(path.join(js,n));})||
           !ordinary(path.join(folder,"data","System.json")))return "AMBIGUOUS";
        return "MZ";
    }
    return mv?"MV":"";
}
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
        var base=candidates[i],layouts=[path.join(base,"www"),base],found=layouts.map(engineAt);
        if(found.indexOf("AMBIGUOUS")>=0||found.filter(Boolean).length>1)throw Error("IA_RPG_RUTA_AMBIGUA");
        var at=found.indexOf(ENGINE_ID);
        if(at<0)continue;
        try{
            var root=fs.realpathSync(base),folder=at===0?path.join(root,"www"):root;
            if(engineAt(folder)===ENGINE_ID)return {root:root,content:folder};
        }catch(_){}
    }
    throw Error("IA_RUTA_RPG_NO_RECONOCIDA");
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
    if(externalLocalizationReference(text))return Promise.resolve(null);
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
// Iavra localization references are identifiers, not dialogue. Recognize the
// stock syntax even if the plugin/catalog is not ready, plus configured variants.
function externalLocalizationReference(text){
    if(typeof text!=="string")return false;
    if(remNative.detected&&/(?:\\|\x1b)REM_[A-Z_]{1,40}\[[^\]\r\n]{1,200}\]/i.test(text))return true;
    if(/#\{[A-Za-z0-9_.-]{1,300}\}|«[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+»/.test(text))return true;
    return typeof iavra!=="undefined"&&!!iavra&&iavra.detected&&iavraHasReference(text);
}
function validTranslation(source,original,result,composed){
    if(typeof original!=="string"||typeof result!=="string"||
       !original||!result.trim()||result===original||
       externalLocalizationReference(original)||externalLocalizationReference(result)||
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
           words[i-2]===words[i-5]&&!tsvAuthoredRepeat(original,result,composed))return false;
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
    if(typeof discovered!=="undefined"&&discovered.has(key))markPrefetchReady(discovered.get(key));
    if(approvedKeys.has(key)){
        cache.set(key,approvedKeys.get(key));return true;
    }
    if(cache.has(key)&&cache.get(key)===result)return true;
    cache.set(key,result);indexDisplayAlias(source,original,result);
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
// Keep unwritten records on temporary disk errors. Batch small journal
// appends to avoid unnecessary file opens competing with gameplay.
function queueFlush(){
    if(!diskReady||diskBusy||!diskQueue.length||Date.now()<diskRetryAt)return;
    if(!safeCachePath()){diskStats.errors++;diskRetryAt=Date.now()+2000;return;}
    var items=[],lines=[],count=externalTables()?16:1;
    while(diskQueue.length&&items.length<count){
        var item=diskQueue.shift(),line=JSON.stringify(item)+"\n";
        if(line.length>6000){diskStats.rejected++;continue;}
        items.push(item);lines.push(line);
    }
    if(!items.length)return;
    var prefix=diskNeedsSeparator?"\n":"";
    diskBusy=true;
    function completed(err){
        diskBusy=false;
        if(err){
            // A failed append might have written a partial last record.
            // Separate it from the next batch; repeated keys are harmless.
            diskNeedsSeparator=true;
            diskQueue=items.concat(diskQueue);diskStats.errors++;
            diskRetryAt=Date.now()+1000;setTimeout(queueFlush,1050);return;
        }
        diskNeedsSeparator=false;diskStats.saved+=items.length;
        queueFlush();nextPrefetch();
    }
    try{fs.appendFile(cacheFile,prefix+lines.join(""),{encoding:"utf8",mode:0o600},completed);}
    catch(error){completed(error);}
}
function enqueuePersistentCache(record){
    if(diskQueue.length>=(externalTables()?4096:400)){diskStats.errors++;return;}
    diskQueue.push(record);queueFlush();
}
function startPersistentCache(){
    cacheDir=path.join(sidecar,".local","Rpg","cache");
    cacheFile=path.join(cacheDir,"translations-ja-en-es-v2.jsonl");
    function finish(ok){
        cacheReadDone=true;diskReady=ok;
        if(externalTables()){
            // Early visible requests can precede the disk read. Reconcile
            // restored exact keys, then inventory against the full cache.
            discovered.forEach(function(item){
                if(item.status!=="ready"&&(cache.has(item.source+"\u0000"+item.text)||approvedKeys.has(item.source+"\u0000"+item.text)))
                    markPrefetchReady(item);
            });
            startFullScan();
        }
        queueFlush();nextPrefetch();
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
            diskNeedsSeparator=!!data&&data.charAt(data.length-1)!=="\n";
            var lines=data.split("\n"),limit=lines.length;
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
    if(typeof s!=="string"||!s||s.length>1800||remNativeSpanishText(s))return null;
    if(externalLocalizationReference(s))return null;
    if(tsvExcluded(s))return null;
    var declared=tsvEntry(s);if(declared&&!actorNames[s])return declared.source;
    if(typeof tableStats!=="undefined"&&(tableStats.root||isMZ)&&csvExecutableSyntax(s))return null;
    if(isMZ&&/(?:\\|\x1b)(?:js|eval|script)(?:\b|\[)|<script\b/i.test(s))return null;
    if(isMZ&&actorNames[s])return null;
    if(typeof csvKnown!=="undefined"&&csvKnown.has(s)&&!actorNames[s])return csvKnown.get(s);
    if(isJapanese(s))return "ja";
    if(actorNames[s])return null;
    if((typeof questTexts!=="undefined"&&questTexts.has(s))||
       (typeof discovered!=="undefined"&&discovered.has("en\u0000"+s)))return "en";
    var visible=visibleProse(s);
    if(englishLabel(visible.trim())!==null)return "en";
    var prose=visible.replace(/[\u2018\u2019]/g,"'").replace(/[\u201c\u201d]/g,'"')
        .replace(/[\u2010-\u2015]/g,"-").replace(/\u2026/g,"...").replace(/\u00a0/g," ")
        // Decorative symbols are not evidence of a non-English source.
        // Keep the original glyph in the translation payload and on screen.
        .replace(/[♡♥☆★♪♫♬]/g,"");
    if(/[áéíóúñ¿¡]/i.test(prose)||/[^\x09\x0a\x0d\x20-\x7e]/.test(prose))return null;
    var words=prose.match(/[A-Za-z']+/g)||[];
    if(words.length<2||prose.trim().length<5)return null;
    if(/\b(?:the|you|your|are|have|this|that|with|where|please|hello|sorry|why|what|when|would|could|should|really|don't|doesn't|isn't|won't|i'm|you're|we're|can't|thank|good|morning|and|of|from|into|there|here|was|were|will|must|he|she|they|their|his|her|my|our|is|i|it|him|himself|herself|ourselves|themselves|says|said|keep|moving|writing|looking|always|typical|absurd|enough|stop|listen|leave|wait|come|get|go|back|ready|look|find|help|give|take|bring|open|close|follow|one|year|earlier|city|courthouse|courtroom|change|relationship|text|skip|speed|setting|romantic|idea|naughty|exposing|love|capped|never|mind|me|out|let|read|more|drink|compliment|ask|about|tell|yourself|before|head|door|wake)\b/i.test(prose))return "en";
    return null;
}
// Confirmed rendered surfaces may contain short UI labels that are not
// sentence-like. Restrict one-word inference to a conservative UI vocabulary;
// multiword labels use explicit English signals and never inspect script text.
var displayUiWords=Object.create(null),displaySignalWords=Object.create(null);
("accept back shop read help options save load continue exit quit cancel confirm yes no start next previous return retry resume pause menu settings close open buy sell talk interact select choose skip inventory equipment status profile journal quests quest map guide information details more less done finish apply reset default enabled disabled agree decline reject gift compliment popup rules bet shoe chips flowers prize grab round level score mash timing swipe arrows rotate tracking reaction hold release").split(" ").forEach(function(w){displayUiWords[w]=true;});
("about me yourself tell one year earlier city courthouse courtroom change relationship text skip speed setting romantic idea naughty exposing love capped never mind more drink gift compliment ask let out read before head door click press key target ring closes wrong means instant fail start tap space fill bar time runs lands green zone drag cursor path arrows matching arrow charge gauge release inside target band rotate moving capture reaction marker clicking").split(" ").forEach(function(w){displaySignalWords[w]=true;});
function displaySource(text,context){
    if(typeof text!=="string"||!text.trim()||text.length>1800||actorNames[text]||
       remNativeSpanishText(text)||externalLocalizationReference(text)||tsvExcluded(text)||csvExecutableSyntax(text)||
       /(?:\\|\x1b)(?:js|eval|script)(?:\b|\[)|<script\b/i.test(text))return null;
    var source=languageFor(text);if(source)return source;
    var prose=visibleProse(text).replace(/[\u2018\u2019]/g,"'").replace(/[\u201c\u201d]/g,'"')
        .replace(/[\u2010-\u2015]/g,"-").replace(/\u2026/g,"...").replace(/\u00a0/g," ")
        .replace(/[♡♥☆★♪♫♬]/g,"").trim();
    if(!prose||/[áéíóúñ¿¡]/i.test(prose)||/[^\x09\x0a\x0d\x20-\x7e]/.test(prose)||
       /^[A-Za-z0-9_./-]+\.(?:png|jpe?g|webp|gif|ogg|mp3|wav|js|json|csv|tsv|webm|mp4)$/i.test(prose))return null;
    var words=prose.match(/[A-Za-z']+/g)||[];
    if(!words.length||words.length>60)return null;
    var normalized=words.map(function(w){return w.toLowerCase();});
    if(words.length===1){
        return context!=="message"&&displayUiWords[normalized[0]]?"en":null;
    }
    if(normalized.some(function(w){return !!displaySignalWords[w];}))return "en";
    return null;
}
// Never send game control sequences (including character names) to OPUS.
var controlRE=/(?:\\|\x1b)(?:[Aa][CcLlRr](?![A-Za-z])|[Aa][Ll][Ii][Gg][Nn]\[[A-Za-z]{1,10}\])|(?:\\|\x1b)[Tt][Ll]\{[^{}\r\n]{1,300}\}|\\(?:[A-Za-z]{1,12}\[[^\]\r\n]{0,120}\]|[A-Za-z]{1,12}<[^>\r\n]{1,120}>|(?:fi|fb|fr|lson|lsoff|playtime|msgreset|auto)(?=[A-Za-z])|[A-Za-z]{1,12}\b|[{}!.,|^<>$\\])|\x1b(?:[mM]\[[A-Za-z0-9 _\-]{1,60}\]|[A-Za-z]+\[[0-9]{1,8}\]|[{}!.,|^<>$])|%(?:[0-9]{1,3}|[sdf])|\$\{[A-Za-z0-9_]{1,50}\}|\r?\n|<(?!\/?[Ii][Ff]\s+[^<>]{1,80}\s+[Cc]apped>)[\/]?[A-Za-z][A-Za-z0-9 _.,:'"=\/#%+\-]{0,100}>|[<>]|\([A-Za-z]{1,10}:[^()\r\n]{1,100}\)/g;
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
    // In external sheets the leading ※ in an explicitly selected display
    // cell is a visual note marker, not an executable annotation.
    if(typeof tableStats!=="undefined"&&tableStats.root&&/^[ \t]*※[ \t]*/.test(text)){
        var mark=/^[ \t]*※[ \t]*/.exec(text)[0];
        return [{value:mark,locked:true}].concat(protectedParts(text.slice(mark.length)));
    }
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
    if(externalLocalizationReference(text)||tsvRef(text)||tsvExcluded(text))return Promise.resolve(null);
    priority=!!(priority||foregroundDepth);
    var key=source+"\u0000"+text;
    var ready=readyText(source,text);
    if(ready!==null)return Promise.resolve(ready);
    var completePlan=tsvEnglishPlan(source,text);
    if(completePlan)return tsvPlanTranslate(source,text,completePlan,priority);
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
var authoredSpeakerNames=Object.create(null),authoredKanaReadings=Object.create(null);
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
    // Parenthetical kana is evidence only for a literal authored speaker.
    // Keep ambiguous readings unresolved; never use these as model aliases.
    if(isMZ&&text.length<=1800){
        var marked=/([\u3400-\u9fff々]{1,12})[（(]([ぁ-ゖァ-ヶー]{1,24})[）)]/g,reading;
        while((reading=marked.exec(text))!==null){
            var k=reading[1],v=romanizeKana(reading[2]);
            if(v&&Object.keys(authoredKanaReadings).length<2048){
                if(!Object.prototype.hasOwnProperty.call(authoredKanaReadings,k))authoredKanaReadings[k]=v;
                else if(authoredKanaReadings[k]!==v)authoredKanaReadings[k]=null;
            }
        }
    }
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
var formatAliases=new Map(),captionAliases=new Map(),displayBodyAliases=new Map();
function captionEnvelope(text){
    if(typeof text!=="string"||text.length>1800)return null;
    var m=/^(<c:-?\d{1,6},\d{1,6},\d{1,6}(?:,[A-Za-z0-9_ -]{1,64})?(?:,-?\d{1,6})?>)([\s\S]+)$/i.exec(text);
    return m&&m[2].trim()?{tag:m[1],body:m[2]}:null;
}
// A caption's native parser removes its positioning/timing tag before drawing.
// Recover that exact body from verified historical entries; conflicting
// translations for the same body must not be selected arbitrarily.
function indexCaptionAlias(source,text,result){
    var a=captionEnvelope(text),b=captionEnvelope(result);
    if(!a||!b||a.tag!==b.tag||!validTranslation(source,a.body,b.body,true))return;
    var key=source+"\u0000"+a.body;
    if(captionAliases.has(key)){
        if(captionAliases.get(key)!==b.body)captionAliases.set(key,null);
    }else if(captionAliases.size<MAX_CACHE_ENTRIES)captionAliases.set(key,b.body);
}
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
// The developer's native name box and caption parser may remove their
// presentation prefix before asking the text renderer to draw the body.
// Only equivalent, exact color/icon sequences and uniquely cached results
// are eligible; preserve the caller's own prefix, never copy a speaker.
function displayEnvelope(text){
    var cap=captionEnvelope(text);
    if(cap)return {prefix:cap.tag,body:cap.body};
    var prefix=(text.match(/^(?:(?:<wordwrap>)[ \t]*|\\n[cr]?<[^\\<>\r\n]{1,75}>[ \t]*)+/i)||[""])[0];
    return {prefix:prefix,body:text.slice(prefix.length)};
}
function indexDisplayBody(source,text,result){
    if(source!=="en"||typeof text!=="string"||typeof result!=="string")return;
    var a=displayEnvelope(text),b=displayEnvelope(result);
    if(!a.prefix||a.prefix!==b.prefix||!validTranslation(source,a.body,b.body,true))return;
    var k=canonicalDisplay(a.body),v=canonicalDisplay(b.body);
    if(!k||!v||k.codes.length!==v.codes.length)return;
    if(displayBodyAliases.has(k.key)){
        var old=displayBodyAliases.get(k.key);
        if(old&&old.target!==v.key)displayBodyAliases.set(k.key,null);
    }else if(displayBodyAliases.size<MAX_CACHE_ENTRIES)displayBodyAliases.set(k.key,{target:v.key,result:b.body});
}
function displayBodyAlias(source,text){
    if(source!=="en"||typeof text!=="string")return null;
    var env=displayEnvelope(text),alias=canonicalDisplay(env.body);
    if(!alias)return null;
    var old=displayBodyAliases.get(alias.key);
    if(!old)return null;
    var at=0,out=protectedParts(old.result).map(function(p){
        return p.locked?alias.codes[at++]:p.value;
    }).join("");
    if(at!==alias.codes.length)return null;
    out=env.prefix+out;
    return validTranslation(source,text,out,true)?out:null;
}
function indexDisplayAlias(source,text,result){
    indexCaptionAlias(source,text,result);
    indexDisplayBody(source,text,result);
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
    if(remNativeSpanishText(text))return text;
    var key=source+"\u0000"+text;
    if(approvedKeys.has(key))return approvedKeys.get(key);
    var fixed=stableDisplay(text,false);
    if(fixed!==null)return fixed;
    var old=repairDisplayTerms(source,text,cache.get(key));
    if(typeof old==="string"){
        if(validTranslation(source,text,old,true))return old;
        cache.delete(key);diskStats.rejected++;
    }
    var authored=typeof csvAuthored!=="undefined"?csvAuthored.get(key):null;
    if(typeof authored==="string"&&validTranslation(source,text,authored,true))return authored;
    var caption=captionAliases.get(key);
    if(typeof caption==="string"&&validTranslation(source,text,caption,true))return caption;
    var bodyAlias=displayBodyAlias(source,text);
    if(bodyAlias!==null)return bodyAlias;
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
    var exact=cachedPart(source,text),tsvPlan=tsvEnglishPlan(source,text);
    if(tsvPlan&&(!exact||tsvCoverageSuspect(text,exact,tsvPlan))){
        // Keep the original journal; only replace the in-memory result
        // after every sentence has a usable translation.
        return tsvPlanReady(source,text,tsvPlan);
    }
    if(exact!==null)return exact;
    var csvEquivalent=csvAlternateReady(source,text);
    if(csvEquivalent!==null)return csvEquivalent;
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
    if(tsvExcluded(text))return text;
    if(typeof text!=="string"||text.length>1800||!isJapanese(text))return text;
    if(typeof SceneManager!=="undefined"&&SceneManager._scene&&
       typeof Scene_Name!=="undefined"&&SceneManager._scene instanceof Scene_Name){
        // Only the literal buttons, never the name-entry keyboard/value.
        return text==="決定"?"Aceptar":text==="キャンセル"?"Cancelar":text;
    }
    if(identity)return isMZ?text:nameInSpanish(text,true)||text;
    var source=languageFor(text);
    if(!source)return text;
    var found=readyText(source,text);
    if(found!==null)return found;
    if(state.connected&&pending.size<18){
        translatePreservingControls(source,text).catch(function(){state.errors++;});
    }
    return text;
}
function pluginEnabled(pattern){
    return typeof $plugins!=="undefined"&&Array.isArray($plugins)&&$plugins.some(function(p){
        return p&&p.status&&pattern.test(p.name||"");
    });
}
function hasNativeClass(win,pattern){
    for(var p=win,i=0;p&&i<8;i++,p=Object.getPrototypeOf(p)){
        if(p.constructor&&pattern.test(p.constructor.name||""))return true;
    }
    return false;
}
function visuQuestEnabled(){return isMZ&&pluginEnabled(/^VisuMZ_2_QuestSystem$/);}
function visuQuestScene(){
    var scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
    return visuQuestEnabled()&&!!scene&&hasNativeClass(scene,/^Scene_Quest(?:$|[A-Za-z])/);
}
function visuQuestBitmapScope(bitmap){
    if(!visuQuestEnabled()||identityDrawDepth||inputFormActive())return false;
    var owner=bitmap&&bitmap._iaOwnerWindow;
    if(owner&&(owner._iaOwnSurface||owner._iaNameSurface||
       typeof Window_Message!=="undefined"&&owner instanceof Window_Message))return false;
    return !!(owner&&isQuestWindow(owner)||visuQuestScene()||
        /\bVisuMZ_2_QuestSystem\.js(?::|\?)/.test(String(new Error().stack||"")));
}
function visuQuestFixed(value){
    if(!visuQuestEnabled()||typeof value!=="string")return null;
    var labels={"Prologue":"Prólogo","Epilogue":"Epílogo","Character Quests":"Misiones de personajes",
        "Scroll Up/Down":"Desplazar arriba/abajo","Track":"Seguir","Untrack":"Dejar de seguir",
        "Expand":"Expandir","Collapse":"Contraer","Difficulty":"Dificultad",
        "Easy":"Fácil","Normal":"Normal","Hard":"Difícil","No Quests Listed":"No hay misiones",
        "(No Quests Listed)":"(No hay misiones)"};
    if(Object.prototype.hasOwnProperty.call(labels,value))return labels[value];
    var hotkey=/^([A-Za-z0-9/+\-]{1,16}:[ \t]*)(Scroll Up\/Down|Track|Untrack|Expand|Collapse)$/.exec(value);
    if(hotkey)return hotkey[1]+labels[hotkey[2]];
    var objective=/^(Speak to|Talk to|Meet|Find|Visit) (.{1,80})([.!?]?)$/.exec(value);
    if(objective){
        var who=objective[2],suffix=objective[3]||"";
        // The greedy capture can include final punctuation; normalize only
        // against the original, proven actor identity.
        if(!suffix&&/[.!?]$/.test(who)){suffix=who.slice(-1);who=who.slice(0,-1);}
        var verbs={"Speak to":"Habla con","Talk to":"Habla con","Meet":"Reúnete con","Find":"Encuentra a","Visit":"Visita a"};
        if(actorNames[who])return verbs[objective[1]]+" "+who+suffix;
    }
    return null;
}
function isQuestWindow(win){
    if(!win||win._iaOwnSurface||win._iaNameSurface||
       typeof Window_Message!=="undefined"&&win instanceof Window_Message)return false;
    if(hasNativeClass(win,/^Window_Quest(?:Data|Title|List|Category|Info|Detail|Journal|Help|Command)/))return true;
    if(visuQuestEnabled()&&(hasNativeClass(win,/^Window_Quest(?:Log|Label|Button|Tracker)/)||visuQuestScene()))return true;
    var scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
    return !!(scene&&hasNativeClass(scene,/^Scene_Quest/)&&
        (scene._questDataWindow===win||scene._dataWindow===win||scene._descriptionWindow===win));
}
function isQuestTemplate(win,text){
    if(typeof text!=="string"||text.length>16000||(!pluginEnabled(/^YEP_QuestJournal$/)&&!visuQuestEnabled())||
       (typeof Window_Message!=="undefined"&&win instanceof Window_Message))return false;
    // Some journal plugins implement their own drawTextEx, then call the
    // native escape conversion on the complete assembled data template.
    return /\bDescription\s*:/i.test(text)&&/\b(?:From|Location|Objectives|Rewards)\s*:/i.test(text);
}
function questSurface(win,text){
    return isQuestWindow(win)||isQuestTemplate(win,text);
}
// Match only known quest labels/titles on nonstandard bitmap-based journals.
// Decoration and numeric counters remain the author's original characters.
// The author's category format can include a color prefix, count and
// expansion marker. Keep them, even when the caption itself is short.
function questEnvelope(text){
    var lead=(text.match(/^(?:(?:\\|\x1b)(?:[ci]\[\d{1,4}\]|[{}])|<\/?wordwrap>|<ColorLock>|[◎✔✘]|[ \t])*/i)||[""])[0];
    var rest=text.slice(lead.length);
    var tail=(rest.match(/(?:(?:\\|\x1b)(?:c\[\d{1,3}\]|[{}])|<\/wordwrap>|<\/ColorLock>|[ \t])*$/i)||[""])[0];
    return {lead:lead,body:rest.slice(0,rest.length-tail.length),tail:tail};
}
function questCachedLabel(text,scoped){
    if(typeof text!=="string"||text.length>1800||actorNames[text])return null;
    var e=questEnvelope(text);
    var m=/^([ \t+\-–—]*)(.*?)([ \t]*(?:\(\d{1,6}\)|\[\d{1,6}\])?[ \t]*)$/.exec(e.body);
    if(!m||!m[2])return null;
    var value=m[2];
    if(!scoped&&/^(?:From|Location|Level|Castle|Forest|Village|Town|Close)$/.test(value))return null;
    var translated=scoped?visuQuestFixed(value):null;
    if(translated===null)translated=Object.prototype.hasOwnProperty.call(questLabels,value)?questLabels[value]:null;
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
               typeof win.refresh!=="function")return;
            var refreshArgs=win._iaQuestRefreshArgs;
            if(win.refresh.length!==0&&!refreshArgs)return;
            try{
                var index=typeof win.index==="function"?win.index():null;
                var row=typeof win.topRow==="function"?win.topRow():null;
                win.refresh.apply(win,refreshArgs||[]);
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
        if(value&&k==="From"){
            // Translate generic ranks, never a person's identity.
            var rank={"Baroness":"Baronesa","Baron":"Barón","King":"Rey","Queen":"Reina","Guard":"Guardia","Captain":"Capitán"};
            if(Object.prototype.hasOwnProperty.call(rank,value))value=rank[value];
        }else if(value&&k!=="From"){
            var v=questCachedLabel(value,true),source=questSource(value);
            if(v!==null)value=v;
            else if(source){
                var found=readyText(source,value);
                if(found!==null)value=found;else queueQuest(win,source,value);
            }
        }
        return e.lead+fixed+":"+header[2]+value+e.tail;
    }
    // Prefer whole authored fields, before the native renderer wraps them.
    // Do not turn an isolated word drawn from a sentence into a new request.
    var source=questSource(body);
    if(!source||!body)return text;
    var found=readyText(source,body);
    if(found!==null)return e.lead+found+e.tail;
    queueQuest(win,source,body);
    return text;
}
function visuQuestBitmapText(bitmap,text){
    if(typeof text!=="string"||surfaceDepth||identityDrawDepth)return text;
    var label=questCachedLabel(text,true);
    if(label!==null)return label;
    var e=questEnvelope(text);
    // If an unrecognized custom renderer only emits individual words, do
    // not use unrelated word-cache hits. Only complete, proven fields.
    var src=questTexts.get(e.body);
    if(!src)return text;
    var out=readyText(src,e.body);
    if(out!==null)return e.lead+out+e.tail;
    var owner=bitmap&&bitmap._iaOwnerWindow;
    if(owner&&typeof owner.refresh==="function")queueQuest(owner,src,e.body);
    else firstViewRequest(src,e.body);
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
    if(!win)return false;
    return (pluginEnabled(/^GALV_TimedMessagePopups$/)&&hasNativeClass(win,
        /^Window_(?:Galv(?:Caption|Message|Popup)|(?:Map)?Caption|TimedMessage(?:Popup)?|Popup)$/))||
        (pluginEnabled(/^YEP_GabWindow$/)&&hasNativeClass(win,/^Window_Gab(?:Window)?$/));
}
function isAmbientSurface(win,text){
    if(!win||win._iaOwnSurface||win._iaNameSurface||
       (typeof Window_Message!=="undefined"&&win instanceof Window_Message))return false;
    if(isAmbientWindow(win))return true;
    if(!pluginEnabled(/^GALV_TimedMessagePopups$/))return false;
    if(captionEnvelope(text))return true;
    // Narrow, native presentation fallback for author-specific map captions:
    // only whole, clearly English text with a recognized color run, not
    // glyphs, names, dialogue windows, or arbitrary executable arguments.
    var scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
    if(!scene||typeof Scene_Map==="undefined"||!(scene instanceof Scene_Map)||
       typeof text!=="string"||text.length>1800||text.length<8||actorNames[text])return false;
    return languageFor(text)==="en"&&/(?:\\|\x1b)(?:c\[\d{1,3}\]|m\[[A-Za-z0-9 _\-]{1,60}\])/i.test(text)&&
        /[A-Za-z]{2,}\s+[A-Za-z]{2,}/.test(visibleProse(text));
}
function captionSource(text){
    var env=captionEnvelope(text),body=env?env.body:text,source=languageFor(body);
    if(source)return source;
    // In a confirmed caption a short punctuated English utterance is valid
    // prose even if it lacks a common English stopword.
    return typeof body==="string"&&!actorNames[body]&&
        /^[A-Za-z][A-Za-z '\-]{1,69}[.!?]$/.test(body)&&!/[áéíóúüñ]/i.test(body)? "en":null;
}
function captionReady(source,text){
    var env=captionEnvelope(text);
    if(!env)return readyText(source,text);
    var body=readyText(source,env.body);
    if(body!==null&&validTranslation(source,text,env.tag+body,true))return env.tag+body;
    return readyText(source,text);
}
function captionRequest(source,text){
    var env=captionEnvelope(text);
    if(!env)return requestVisible(source,text);
    return requestVisible(source,env.body).then(function(body){
        var out=typeof body==="string"?env.tag+body:null;
        return out&&validTranslation(source,text,out,true)?out:null;
    });
}
var surfaceRequests=new Map(),surfaceDepth=0;
function projectCaption(text){
    var source=captionSource(text);
    if(!source)return text;
    var ready=captionReady(source,text);
    if(ready!==null){ambientStats.shown++;return ready;}
    var env=captionEnvelope(text),body=env?env.body:text;
    addPrefetch(body,true,source);
    var key=source+"\u0000"+body;
    if(state.connected&&pending.size<32&&surfaceRequests.size<24&&!surfaceRequests.has(key)){
        surfaceRequests.set(key,true);ambientStats.requested++;
        captionRequest(source,text).then(function(){surfaceRequests.delete(key);},function(){surfaceRequests.delete(key);state.errors++;});
    }
    nextPrefetch();
    return text;
}
function projectMessageSurface(win,text){
    if(typeof $gameMessage==="undefined"||!$gameMessage||!$gameMessage.hasText||
       !$gameMessage.hasText()||typeof $gameMessage.allText!=="function"||
       typeof text!=="string"||text.length>1800)return text;
    var current=$gameMessage.allText();
    // Never translate the separate name box, control parameters or an
    // unrelated measuring call. Require the exact active message body.
    function matches(raw){
        if(typeof raw!=="string")return false;
        if(raw===text)return true;
        var a=displayEnvelope(raw),b=displayEnvelope(text);
        if(a.body===b.body)return true;
        var ak=canonicalDisplay(a.body),bk=canonicalDisplay(b.body);
        return !!(ak&&bk&&ak.key===bk.key);
    }
    if(!matches(current)&&!matches(win._iaSourceMessage))return text;
    var source=languageFor(text);
    if(source!=="en"&&!(isMZ&&source==="ja"))return text;
    var ready=readyText(source,text);
    if(ready!==null&&validTranslation(source,text,ready,true)){
        hideLate(win);state.shown++;
        return ready;
    }
    return text;
}
function projectSurface(win,text){
    var external=iavraDisplayValue(text,true);if(external!==null)return external;
    if(typeof Window_Message!=="undefined"&&win instanceof Window_Message)
        return projectMessageSurface(win,text);
    if(questSurface(win,text))return questDraw(win,text);
    if(isAmbientSurface(win,text))return projectCaption(text);
    return text;
}
// Intercept the author's final conversion before word-wrap, even when a
// subclass bypasses the inherited drawing methods. No synthetic window.
function hookSurfaceConversion(proto,ownOnly){
    if(!proto||typeof proto.convertEscapeCharacters!=="function"||
       (ownOnly&&!Object.prototype.hasOwnProperty.call(proto,"convertEscapeCharacters")))return;
    var original=proto.convertEscapeCharacters;
    proto.convertEscapeCharacters=function(){
        if(inputFormActive()||identityDrawDepth||this._iaNameSurface||this._iaOwnSurface||typeof arguments[0]!=="string")
            return original.apply(this,arguments);
        var args=Array.prototype.slice.call(arguments),raw=args[0],csv=csvWindowEligible(this),choice=csv&&csvWindowChoice(this),out;
        // Other RPG dialects keep their previous native conversion behavior.
        if(!csv&&surfaceDepth)return original.apply(this,arguments);
        try{
            if(!surfaceDepth)args[0]=projectSurface(this,args[0]);
            if(csv&&(!surfaceDepth||choice)){
                var before=tsv.visu&&tsvRef(args[0])?null:csvProjectDisplay(args[0],choice,true);
                if(before!==null){args[0]=before;if(tsv.detected&&typeof Window_Message!=="undefined"&&this instanceof Window_Message){state.shown++;tsv.shown++;}}
            }
        }catch(_){state.errors++;}
        surfaceDepth++;
        try{out=original.apply(this,args);}finally{surfaceDepth--;}
        // The game may turn a lookup key into text or expand \V here.
        // Match only known CSV display strings (or a real choice window).
        if(csv&&typeof out==="string"){
            try{var after=tsvResolvedProjection(raw,out,true);
                if(after===null&&out!==args[0])after=csvProjectDisplay(out,choice,true);if(after!==null){if(tsv.detected&&typeof Window_Message!=="undefined"&&this instanceof Window_Message){state.shown++;tsv.shown++;}return after;}}catch(_){state.errors++;}
        }
        return out;
    };
}
function hookSpecificSurfaces(){
    if(typeof window==="undefined")return;
    // Do not wrap arbitrary third-party prototypes. Only opt in classes
    // from the two supported surface families; preserve inherited hooks.
    var names=Object.getOwnPropertyNames(window).filter(function(k){
        return /^Window_(?:Quest(?:Data|Title|List|Category|Info|Detail|Journal|Help|Command)\w*|Galv(?:Caption|Message|Popup)|(?:Map)?Caption|TimedMessage(?:Popup)?|Popup|Gab(?:Window)?)$/.test(k)||
            visuQuestEnabled()&&/^Window_Quest(?:Log|Label|Button|Tracker)\w*$/.test(k);
    }),seen=[];
    names.forEach(function(k){
        var descriptor=Object.getOwnPropertyDescriptor(window,k),ctor=descriptor&&descriptor.value;
        var p=typeof ctor==="function"?ctor.prototype:null;
        if(!p||seen.indexOf(p)>=0)return;seen.push(p);
        hookSurfaceConversion(p,true);
        ["drawText","drawTextEx"].forEach(function(method){
            if(!Object.prototype.hasOwnProperty.call(p,method)||typeof p[method]!=="function")return;
            var original=p[method];
            p[method]=function(){
                if(inputFormActive()||surfaceDepth||identityDrawDepth||this._iaOwnSurface||this._iaNameSurface||typeof arguments[0]!=="string")
                    return original.apply(this,arguments);
                var args=Array.prototype.slice.call(arguments);
                surfaceDepth++;
                try{
                    if(isAmbientWindow(this))return ambientDraw(this,method,args,original);
                    try{args[0]=projectSurface(this,args[0]);}catch(_){state.errors++;}
                    return original.apply(this,args);
                }finally{surfaceDepth--;}
            };
        });
        // A data window may refresh with a quest ID instead of zero args.
        // Record only primitive arguments of its actual native invocation.
        if(/^Window_Quest/.test(k)&&Object.prototype.hasOwnProperty.call(p,"refresh")&&typeof p.refresh==="function"){
            var refresh=p.refresh;
            p.refresh=function(){
                var args=Array.prototype.slice.call(arguments);
                this._iaQuestRefreshArgs=args.every(function(v){return v===null||typeof v==="string"||typeof v==="number"||typeof v==="boolean";})?args:null;
                return refresh.apply(this,arguments);
            };
        }
    });
}
// Static timed messages are Show Text event commands, but Galv can consume
// them before Game_Message.add. Supply a transient copy to its original
// interpreter; restore the original array and never change event indices,
// speaker, timing, position, switches, choices or saved map data.
function hookCaptionInterpreter(){
    if(!pluginEnabled(/^GALV_TimedMessagePopups$/)||typeof Game_Interpreter==="undefined"||
       !Game_Interpreter.prototype||typeof Game_Interpreter.prototype.command101!=="function")return;
    var original=Game_Interpreter.prototype.command101;
    Game_Interpreter.prototype.command101=function(){
        var list=this._list,index=this._index,copy=null;
        try{
            if(Array.isArray(list)&&integer(index)&&list[index]&&list[index].code===101&&
               list[index+1]&&list[index+1].code===401&&Array.isArray(list[index+1].parameters)&&captionEnvelope(list[index+1].parameters[0])){
                var changes=[],end=index+1;
                while(end<list.length&&end<index+5&&list[end]&&list[end].code===401){
                    var row=list[end],raw=row.parameters&&row.parameters[0];
                    if(typeof raw!=="string")break;
                    var out=projectCaption(raw);
                    if(out!==raw)changes.push({index:end,command:row,text:out});
                    end++;
                }
                if(changes.length){
                    copy=list.slice();
                    changes.forEach(function(c){
                        var item={},key;
                        for(key in c.command)if(Object.prototype.hasOwnProperty.call(c.command,key))item[key]=c.command[key];
                        item.parameters=c.command.parameters.slice();item.parameters[0]=c.text;copy[c.index]=item;
                    });
                    this._list=copy;
                }
            }
        }catch(_){state.errors++;copy=null;this._list=list;}
        try{return original.apply(this,arguments);}finally{if(copy&&this._list===copy)this._list=list;}
    };
}
// Galv 1.7--2.0 declares its caption class inside a private closure. The
// stable map factory receives textArray after interpreter/author scripts
// assemble the text, and before the original class measures the layout.
// Observe that actual API, not a global Window_GalvCaption constructor.
var nativeCaptionPending=new Map();
function nativeCaptionScope(receiver,fn,args){
    surfaceDepth++;identityDrawDepth++;
    try{return fn.apply(receiver,args);}finally{identityDrawDepth--;surfaceDepth--;}
}
function sameCaptionLines(a,b){
    return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&
        a.every(function(v,i){return v===b[i];});
}
function nativeCaptionInput(raw){
    // Only resolve an entire display-only text variable, not arbitrary
    // expressions, script calls, event variables or numeric game state.
    var m=/^(?:\\|\x1b)v\[(\d{1,6})\]$/i.exec(raw);
    if(m&&typeof $gameVariables!=="undefined"&&$gameVariables&&typeof $gameVariables.value==="function"){
        var id=Number(m[1]),value=$gameVariables.value(id);
        if(typeof value==="string"&&value.length<=1800&&captionSource(value))
            return {raw:raw,text:value,source:captionSource(value),variable:id};
    }
    return {raw:raw,text:raw,source:captionSource(raw),variable:null};
}
function captionInputCurrent(input){
    return input.variable===null||
        (typeof $gameVariables!=="undefined"&&$gameVariables&&typeof $gameVariables.value==="function"&&
         $gameVariables.value(input.variable)===input.text);
}
function nativeCaptionValue(input){
    if(!input.source||!captionInputCurrent(input))return null;
    var result=captionReady(input.source,input.text);
    return typeof result==="string"&&validTranslation(input.source,input.text,result,true)?result:null;
}
function requestNativeCaption(input){
    if(!input.source||!captionInputCurrent(input))return;
    var env=captionEnvelope(input.text),body=env?env.body:input.text;
    addPrefetch(body,true,input.source);
    var key=input.source+"\u0000"+body,blocked=rejectedKeys.get(key);
    if(state.connected&&pending.size<96&&nativeCaptionPending.size<24&&
       !nativeCaptionPending.has(key)&&!(blocked&&blocked>Date.now())){
        nativeCaptionPending.set(key,true);ambientStats.requested++;
        captionRequest(input.source,input.text).then(function(){
            nativeCaptionPending.delete(key);
        },function(){nativeCaptionPending.delete(key);state.errors++;});
    }
    nextPrefetch();
}
function attachNativeCaption(scene,win,inputs,displayed){
    if(!win||!hasNativeClass(win,/^Window_GalvCaption$/)||
       !sameCaptionLines(win._txtArray,displayed)||
       typeof win.setWindowDimensions!=="function"||typeof win.update!=="function")return;
    // Layout may happen immediately or later when the skin has loaded.
    // In either case let Galv measure and paint its own existing bitmap
    // without secondary interception of each color span or glyph.
    var layout=win.setWindowDimensions;
    win.setWindowDimensions=function(){
        return nativeCaptionScope(this,layout,arguments);
    };
    var update=win.update,shown=displayed.slice(),tick=0,tries=0,finished=false,epoch=formEpoch;
    var remaining=inputs.some(function(input,i){return input.source&&shown[i]===input.raw;});
    if(!remaining)return;
    win.update=function(){
        var output=update.apply(this,arguments);
        if(finished||this!==win)return output;
        if(inputFormActive()||epoch!==formEpoch){finished=true;return output;}
        try{
            if(typeof SceneManager==="undefined"||SceneManager._scene!==scene||
               !Array.isArray(scene._captionWindows)||scene._captionWindows.indexOf(win)<0||
               !win.parent||win.active===false||win._disable||
               typeof win._time!=="number"||win._time<=0||
               !sameCaptionLines(win._txtArray,shown)){
                finished=true;return output;
            }
            if(++tick%4!==0)return output;
            var next=shown.slice(),changed=0,missing=false;
            inputs.forEach(function(input,i){
                if(!input.source||shown[i]!==input.raw||!captionInputCurrent(input))return;
                var value=nativeCaptionValue(input);
                if(value!==null){next[i]=value;changed++;}
                else {
                    missing=true;
                    if(tick%20===0&&tries<4)requestNativeCaption(input);
                }
            });
            if(tick%20===0)tries++;
            if(changed){
                var old=win._txtArray;
                // A pending skin will use the new display array at its
                // normal first draw. An already-painted bubble is cleared
                // and remeasured only by its own native layout method.
                win._txtArray=next;
                try{
                    if(win.imagesLoaded!==false){
                        win.setWindowDimensions();
                        var max=typeof Graphics!=="undefined"&&(Graphics.boxWidth||Graphics.width);
                        if(typeof max==="number"&&max>0&&typeof win.width==="number"&&win.width>max)
                            throw Error("IA_CAPTION_LAYOUT_TOO_WIDE");
                    }
                    shown=next;ambientStats.shown+=changed;state.shown+=changed;
                }catch(_){
                    win._txtArray=old;
                    try{if(win.imagesLoaded!==false)win.setWindowDimensions();}catch(__){}
                    state.errors++;finished=true;
                }
            }
            if(!missing)finished=true;
        }catch(_){state.errors++;finished=true;}
        return output;
    };
}
function hookGalvCaptionFactory(){
    if(!pluginEnabled(/^GALV_TimedMessagePopups$/i)||typeof Scene_Map==="undefined"||
       !Scene_Map.prototype||typeof Scene_Map.prototype.createCaptionWindow!=="function")return false;
    var original=Scene_Map.prototype.createCaptionWindow;
    Scene_Map.prototype.createCaptionWindow=function(){
        var args=Array.prototype.slice.call(arguments),raw=args[2],before,inputs,displayed,ready=0;
        if(!Array.isArray(raw)||!raw.length||raw.length>16||
           !raw.every(function(v){return typeof v==="string"&&v.length<=1800;}))
            return original.apply(this,arguments);
        try{
            // Copy only the presentation list, never the event data or
            // other factory arguments (target, time, delay, skin, offset).
            before=Array.isArray(this._captionWindows)?this._captionWindows.slice():[];
            inputs=raw.map(nativeCaptionInput);
            displayed=inputs.map(function(input){
                var found=nativeCaptionValue(input);
                if(found!==null){ready++;return found;}
                if(input.source)requestNativeCaption(input);
                return input.raw;
            });
            if(!inputs.some(function(input){return !!input.source;}))
                return original.apply(this,arguments);
            args[2]=displayed.slice();ambientStats.factory=(ambientStats.factory||0)+1;
        }catch(_){state.errors++;return original.apply(this,arguments);}
        // Exactly one native creation. No wait, no duplicate window.
        var result=nativeCaptionScope(this,original,args);
        try{
            ambientStats.shown+=ready;state.shown+=ready;
            var scene=this,newWindows=Array.isArray(scene._captionWindows)?
                scene._captionWindows.filter(function(w){return before.indexOf(w)<0;}):[];
            if(newWindows.length===1)attachNativeCaption(scene,newWindows[0],inputs,displayed);
        }catch(_){state.errors++;}
        return result;
    };
    return true;
}

function ambientDraw(win,method,args,original){
    var text=args[0],source=null,found=null,epoch=(win._iaCaptionEpoch||0)+1;
    win._iaCaptionEpoch=epoch;
    try{
        source=captionSource(text);
        if(source)found=captionReady(source,text);
    }catch(_){state.errors++;}
    if(found!==null){args[0]=found;ambientStats.shown++;}
    // Invoke the author's native draw exactly once, even if IA fails.
    var out=original.apply(win,args);
    if(!source||found!==null)return out;
    try{
    if(!state.connected){var env=captionEnvelope(text);addPrefetch(env?env.body:text,true,source);return out;}
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
            width:b.width,height:b.height,style:style},result:null,formEpoch:formEpoch};
    }
    ambientStats.requested++;
    captionRequest(source,text).then(function(result){
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
// Exact display-only CSV labels can also be painted directly on a bitmap
// by a custom UI without passing through the native Window_Base methods.
// The CSV loader resolves variable-backed labels after the interpreter
// builds its choices. Project only display values; never write to variables,
// choice indices, event branches, database records, or original CSV files.
var csvUiLabels={"Information":"Información","NAME":"NOMBRE","Name":"Nombre","JOB":"CLASE","Job":"Clase",
    "Level":"Nivel","MAX HP":"PV MÁX.","MAX MP":"PM MÁX.","Strength":"Fuerza","Endurance":"Resistencia",
    "Intelligence":"Inteligencia","Charisma":"Carisma","Dexterity":"Destreza","Faith":"Fe",
    "Rank":"Rango","Fame":"Fama","Alignment":"Alineamiento","Neutral":"Neutral","Talk":"Hablar",
    "Go solo":"Ir solo","Cancel":"Cancelar","Quest":"Misión","Quests":"Misiones","Title:":"Título:",
    "Place:":"Lugar:","Client:":"Cliente:","Reward:":"Recompensa:","Progress:":"Progreso:",
    "Description:":"Descripción:","Detail:":"Detalles:","Previous Page":"Página anterior",
    "Next Page":"Página siguiente","Scroll Up":"Subir","Scroll Down":"Bajar","Exit":"Salir"};
function csvFixedLabel(text){
    if(Object.prototype.hasOwnProperty.call(csvUiLabels,text))return csvUiLabels[text];
    // Composite property labels keep the value exactly as supplied by the
    // game. Do not replace names, class IDs, stats or user input.
    var m=/^([A-Za-z ]{2,24}?)([ \t]*:[ \t]*)([^\r\n]+)$/.exec(text);
    if(m&&Object.prototype.hasOwnProperty.call(csvUiLabels,m[1]))return csvUiLabels[m[1]]+m[2]+m[3];
    return null;
}
function csvWindowChoice(win){
    return !!win&&((typeof Window_ChoiceList!=="undefined"&&win instanceof Window_ChoiceList)||
        hasNativeClass(win,/^Window_(?:ChoiceList|Choice|SelectChoice)/));
}
function csvWindowEligible(win){
    return (externalTables()||isMZ)&&!identityDrawDepth&&(!win||!win._iaOwnSurface&&!win._iaNameSurface)&&
        !(typeof Scene_Name!=="undefined"&&typeof SceneManager!=="undefined"&&SceneManager._scene instanceof Scene_Name);
}
function csvActorExpansion(text){
    if(typeof $gameActors==="undefined"||!$gameActors||typeof $gameActors.actor!=="function")return null;
    var good=true,out=text.replace(/\\n\[(\d{1,5})\]/gi,function(all,n){
        var a=$gameActors.actor(Number(n)),name=a&&typeof a.name==="function"?a.name():null;
        if(typeof name!=="string"||!name||name.length>100||/[\r\n\\\x1b]/.test(name)){good=false;return all;}
        return name;
    });
    return good?out:null;
}
function rememberNameTemplate(source,text){
    if((source!=="en"&&source!=="ja")||typeof text!=="string"||text.length>1800||actorNames[text])return;
    var tokens=text.match(/\\n\[\d{1,5}\]/gi)||[];
    if(tokens.length!==1)return;
    var token=tokens[0],at=text.indexOf(token),prefix=text.slice(0,at);
    if(prefix.length<8||/[\u0000\uFFFD]/.test(text))return;
    var k=prefix.slice(0,8),list=csvNameTemplates.get(k)||[];
    if(csvNameCount<12000&&list.length<24&&!list.some(function(v){return v.text===text;})){
        var id=/\[(\d{1,5})\]/.exec(token);
        list.push({source:source,text:text,id:id?Number(id[1]):0,prefix:prefix,suffix:text.slice(at+token.length)});
        csvNameTemplates.set(k,list);csvNameCount++;
    }
}
function csvNameReady(text){
    var list=csvNameTemplates.get(text.slice(0,8)),answer=null;
    if(!list)return null;
    for(var i=0;i<list.length;i++){
        var t=list[i],original=csvActorExpansion(t.text);
        if(typeof original!=="string")continue;
        var result=readyText(t.source,t.text),expanded=result!==null?csvActorExpansion(result):null;
        if(typeof expanded!=="string"||expanded===original)continue;
        var candidate=null;
        if(original===text)candidate=expanded;
        else if(original.indexOf("\n")>=0&&expanded.indexOf("\n")>=0){
            var sourceLines=original.split(/\r?\n/),targetLines=expanded.split(/\r?\n/);
            if(sourceLines.length===targetLines.length){
                for(var j=0;j<sourceLines.length;j++)if(sourceLines[j]===text)candidate=targetLines[j];
            }
        }
        if(candidate!==null){
            if(answer!==null&&answer!==candidate)return null;
            answer=candidate;
        }
    }
    return answer;
}
function csvKnownReady(text){
    var source=csvKnown.get(text);
    if(source){
        var exact=readyText(source,text);
        if(typeof exact==="string"&&validTranslation(source,text,exact,true))return exact;
    }
    // Equivalent presentation forms only: trim outside whitespace, native
    // ESC representation, and the sheet's escaped comma. Revalidate the
    // caller's original control and numeric sequence before returning.
    var key=csvRenderKey(text),entry=key&&(csvKnown.has(key)?{source:csvKnown.get(key),text:key}:csvRenderAliases.get(key));
    if(entry&&entry.text!==text){
        var value=readyText(entry.source,entry.text);
        if(typeof value==="string"){
            var out=csvRenderKey(value);
            if(out!==null){
                if(text.indexOf("\x1b")>=0&&text.indexOf("\\")<0)out=out.replace(/\\(?=[A-Za-z])/g,"\x1b");
                var lead=(text.match(/^[ \t]*/)||[""])[0],tail=(text.match(/[ \t]*$/)||[""])[0];
                out=lead+out+tail;
                if(validTranslation(entry.source,text,out,true))return out;
            }
        }
    }
    return null;
}
function csvRequestLive(source,text){
    if(!source)return;
    addPrefetch(text,true,source);
    if(!cacheReadDone||!state.connected)return;
    if(pending.size>=90||csvLiveRequests.size>=32)return;
    var key=source+"\u0000"+text;
    if(csvLiveRequests.has(key)||rejectedKeys.get(key)>Date.now())return;
    csvLiveRequests.set(key,true);addPrefetch(text,true,source);
    requestVisible(source,text).then(function(){csvLiveRequests.delete(key);},function(){csvLiveRequests.delete(key);state.errors++;});
}
function csvProjectDisplay(text,choice,requestMissing){
    var localized=tsvProject(text,requestMissing);if(localized!==null)return localized;
    if(tsvExcluded(text))return null;
    if((!tableStats.root&&!isMZ)||typeof text!=="string"||!text.trim()||text.length>1800||csvExecutableSyntax(text)||actorNames[text])return null;
    if(isMZ&&/(?:\\|\x1b)(?:js|eval|script)(?:\b|\[)|<script\b/i.test(text))return null;
    var raw=text;
    if(choice){
        var v=/^(?:\\|\x1b)v\[(\d{1,6})\]$/i.exec(text);
        if(v&&typeof $gameVariables!=="undefined"&&$gameVariables&&typeof $gameVariables.value==="function"){
            var value=$gameVariables.value(Number(v[1]));
            if(typeof value!=="string"||!value.trim()||value.length>1800||csvExecutableSyntax(value)||actorNames[value])return null;
            text=value;
        }
    }
    var fixed=csvFixedLabel(text);
    if(typeof fixed==="string"&&fixed!==text)return fixed;
    var found=csvKnownReady(text);
    if(found!==null)return found;
    if(!/[\r\n\\\x1b<>]/.test(text)){
        var named=csvNameReady(text);if(named!==null)return named;
    }
    var source=csvKnown.get(text);
    // The same conservative classifier serves native choices and custom
    // rendered surfaces; single-word labels are accepted only in UI context.
    if(!source)source=displaySource(text,choice?"choice":"surface");
    if(source&&csvCandidate(text,source,true)){
        var ready=readyText(source,text);
        if(typeof ready==="string"&&validTranslation(source,text,ready,true))return ready;
        if(requestMissing)csvRequestLive(source,text);
    }
    // Profile/menu labels frequently arrive as separate native lines.
    if(text.indexOf("\n")>=0){
        var lines=text.split(/(\r?\n)/),changed=false;
        for(var i=0;i<lines.length;i+=2){
            var translated=csvProjectDisplay(lines[i],false,requestMissing);
            if(translated!==null){lines[i]=translated;changed=true;}
        }
        if(changed)return lines.join("");
    }
    return null;
}
function csvPlainLabel(text){
    if(tsv.detected&&!surfaceDepth&&!identityDrawDepth&&typeof text==="string"&&
       !(typeof Scene_Name!=="undefined"&&typeof SceneManager!=="undefined"&&SceneManager._scene instanceof Scene_Name)){
        var localized=tsvProject(text,true);
        if(localized!==null&&!/[\\\x1b\r\n]/.test(localized))return localized;
        if(tsvExcluded(text))return null;
    }
    if(!tableStats.root||surfaceDepth||identityDrawDepth||typeof text!=="string"||
       /[\r\n\\\x1b<>]/.test(text)||actorNames[text]||csvExecutableSyntax(text)||
       (typeof Scene_Name!=="undefined"&&typeof SceneManager!=="undefined"&&SceneManager._scene instanceof Scene_Name))
        return null;
    return csvProjectDisplay(text,false,true);
}
function scheduleNativeDisplayRefresh(owner,bitmap){
    if(!owner||owner._iaDisplayRefreshPending||owner._iaOwnSurface||owner._iaNameSurface||
       typeof owner.refresh!=="function")return;
    owner._iaDisplayRefreshPending=true;
    var finish=function(){
        owner._iaDisplayRefreshPending=false;
        if(owner.contents!==bitmap||owner.visible===false||owner.openness===0||
           typeof owner.refresh!=="function")return;
        try{owner.refresh();}catch(_){state.errors++;}
    };
    if(typeof setTimeout==="function")setTimeout(finish,0);else finish();
}
function nativeDisplayProjection(text,context,bitmap){
    // Name-entry bitmaps contain user-authored values, not translatable UI.
    // Let translatedNativeLabel handle only the literal OK/Cancel buttons.
    if(typeof Scene_Name!=="undefined"&&typeof SceneManager!=="undefined"&&
       SceneManager._scene instanceof Scene_Name)return null;
    if(inputFormActive()||identityDrawDepth||typeof text!=="string"||!text.trim()||
       text.length>1800||actorNames[text]||csvExecutableSyntax(text)||
       /(?:\\|\x1b)(?:js|eval|script)(?:\b|\[)|<script\b/i.test(text))return null;
    if(statusPresentationScope())return statusRenderValue(text);
    if(visuQuestBitmapScope(bitmap))return visuQuestBitmapText(bitmap,text);
    if(ultraHudScope())return ultraHudRender(text);
    if(remNativeSpanishText(text))return text;
    var phoneLabel=phoneDrawLabel(text);if(phoneLabel!==null)return phoneLabel;
    var external=iavraDisplayValue(text,true);if(external!==null)return external;
    var localized=tsvProject(text,true);if(localized!==null)return localized;
    if(tsvExcluded(text))return null;
    var named=csvNameReady(text);if(named!==null)return named;
    var known=csvKnownReady(text);if(known!==null)return known;
    var source=displaySource(text,context||"surface");if(!source)return null;
    var ready=readyText(source,text);
    if(typeof ready==="string"&&ready!==text&&validTranslation(source,text,ready,true))return ready;
    var owner=bitmap&&bitmap._iaOwnerWindow,key=source+"\u0000"+text;
    if(owner&&typeof owner.refresh==="function"){
        if(bitmap._iaPendingDisplayKey!==key){
            bitmap._iaPendingDisplayKey=key;
            Promise.resolve(requestVisible(source,text)).then(function(result){
                if(bitmap._iaPendingDisplayKey===key)bitmap._iaPendingDisplayKey=null;
                if(typeof result==="string"&&result!==text)scheduleNativeDisplayRefresh(owner,bitmap);
            },function(){if(bitmap._iaPendingDisplayKey===key)bitmap._iaPendingDisplayKey=null;state.errors++;});
        }
    }else firstViewRequest(source,text);
    return null;
}
// Engine-specific presentation adapter. Keep the neural/cache/scheduler core shared.
function ownWindowArgs(x,y,w,h){return isMZ?[new Rectangle(x,y,w,h)]:[x,y,w,h];}
function nativeTextColor(win,index){
    if(isMZ&&typeof ColorManager!=="undefined"&&typeof ColorManager.textColor==="function")
        return ColorManager.textColor(index);
    return typeof win.textColor==="function"?win.textColor(index):null;
}
function literalSpeakerLabel(value){
    if(typeof value!=="string"||!value.trim()||value.length>40||/[\r\n\\\x1b<>\[\]]/.test(value))return;
    if(typeof $dataActors!=="undefined"&&Array.isArray($dataActors)&&
       $dataActors.some(function(row){return row&&row.name===value;})||actorNames[value]||isJapanese(value))
        authoredSpeakerNames[value]=true;
}
function projectedSpeakerName(raw){
    if(!isMZ||inputFormActive()||typeof raw!=="string"||!authoredSpeakerNames[raw])return raw;
    // A dynamic name (actor escape or actual player-entered actor 1) is not
    // an authored name. Preserve it, even if it matches a role.
    try{
        var player=typeof $gameActors!=="undefined"&&$gameActors&&typeof $gameActors.actor==="function"?$gameActors.actor(1):null;
        if(player&&typeof player.name==="function"&&player.name()===raw)return raw;
    }catch(_){return raw;}
    var roles={"ママ":"Mamá","お母さん":"Mamá","母":"Madre","パパ":"Papá","お父さん":"Papá","父":"Padre","先生":"Profesor","？？？":"???"};
    if(Object.prototype.hasOwnProperty.call(roles,raw))return roles[raw];
    if(ownerNames[raw]&&knownNames[raw])return knownNames[raw];
    if(authoredKanaReadings[raw])return authoredKanaReadings[raw];
    if(knownNames[raw])return knownNames[raw];
    // No invented readings for kanji. Literal kana names are unambiguous.
    return nameInSpanish(raw,true)||raw;
}
function protectMZName(value){
    if(typeof value==="string"&&value.trim()&&value.length<=100&&!/[\r\n\\\x1b<>]/.test(value))actorNames[value]=true;
}
function mzChoiceWidth(win,text){
    if(isMZ&&typeof win.textSizeEx==="function"){
        var size=win.textSizeEx(text);return size&&typeof size.width==="number"?size.width:0;
    }
    return typeof win.textWidthEx==="function"?win.textWidthEx(text):0;
}
function hookMZPresentation(){
    if(typeof Game_Message!=="undefined"&&Game_Message.prototype&&typeof Game_Message.prototype.setSpeakerName==="function"){
        var setSpeaker=Game_Message.prototype.setSpeakerName;
        Game_Message.prototype.setSpeakerName=function(value){protectMZName(value);return setSpeaker.apply(this,arguments);};
    }
    if(typeof Window_NameBox!=="undefined"&&Window_NameBox.prototype){
        var p=Window_NameBox.prototype;
        ["initialize","setName","refresh","windowWidth","drawTextEx","textSizeEx"].forEach(function(method){
            var original=p[method];if(typeof original!=="function")return;
            p[method]=function(){
                this._iaNameSurface=true;
                if(method==="setName")protectMZName(arguments[0]);
                var raw=this._name,paint=method==="refresh"||method==="windowWidth",
                    shown=paint?projectedSpeakerName(raw):raw,changed=paint&&shown!==raw;
                if(changed)this._name=shown;
                if(method==="refresh")this._iaDisplayedSpeaker=shown;
                identityDrawDepth++;
                try{return original.apply(this,arguments);}
                finally{identityDrawDepth--;if(changed)this._name=raw;}
            };
        });
        var updateName=p.update;
        if(typeof updateName==="function"&&typeof p.refresh==="function")p.update=function(){
            var out=updateName.apply(this,arguments);
            if(this.visible!==false&&this.openness!==0&&typeof this._name==="string"&&
               (this._iaReadingTick=(this._iaReadingTick||0)+1)%15===0){
                var shown=projectedSpeakerName(this._name);
                if(this._iaDisplayedSpeaker!==shown&&shown!==this._name)this.refresh();
            }
            return out;
        };
    }
    function protectIdentity(proto,method){
        if(!proto||typeof proto[method]!=="function")return;
        var original=proto[method];
        proto[method]=function(){identityDrawDepth++;try{return original.apply(this,arguments);}finally{identityDrawDepth--;}};
    }
    if(typeof Window_StatusBase!=="undefined")protectIdentity(Window_StatusBase.prototype,"drawActorName");
    if(typeof Sprite_Name!=="undefined")protectIdentity(Sprite_Name.prototype,"redraw");
    if(typeof Window_Help!=="undefined"&&Window_Help.prototype){
        var hp=Window_Help.prototype,update=hp.update;
        if(typeof update==="function"&&typeof hp.refresh==="function"){
            hp.update=function(){
                var out=update.apply(this,arguments);
                try{
                    if(this.visible===false||this.openness===0||this._iaOwnSurface||
                       typeof this._text!=="string"||!this._text.trim()||this._text.length>1800)return out;
                    if((this._iaMZHelpTick=(this._iaMZHelpTick||0)+1)%15!==0)return out;
                    var raw=this._text,source=languageFor(raw);if(!source)return out;
                    var translated=readyText(source,raw);
                    if(translated===null){csvRequestLive(source,raw);return out;}
                    if(this._iaMZHelpRaw!==raw||this._iaMZHelpShown!==translated){
                        this._iaMZHelpRaw=raw;this._iaMZHelpShown=translated;this.refresh();
                    }
                }catch(_){state.errors++;}
                return out;
            };
        }
    }
}
function hookNativeSurface(){
    if(typeof Window_Base!=="undefined"&&Window_Base.prototype){
        function bindDisplayOwner(win){
            try{if(win&&win.contents&&typeof win.contents==="object")win.contents._iaOwnerWindow=win;}catch(_){}
        }
        var baseInitialize=Window_Base.prototype.initialize;
        if(typeof baseInitialize==="function")Window_Base.prototype.initialize=function(){
            var out=baseInitialize.apply(this,arguments);bindDisplayOwner(this);return out;
        };
        var baseCreateContents=Window_Base.prototype.createContents;
        if(typeof baseCreateContents==="function")Window_Base.prototype.createContents=function(){
            var out=baseCreateContents.apply(this,arguments);bindDisplayOwner(this);return out;
        };
        hookSurfaceConversion(Window_Base.prototype,false);
        ["drawText","drawTextEx"].forEach(function(method){
            var original=Window_Base.prototype[method];
            if(typeof original!=="function")return;
            Window_Base.prototype[method]=function(){
                if(inputFormActive()||surfaceDepth)return original.apply(this,arguments);
                var args=Array.prototype.slice.call(arguments),identity=!!this._iaNameSurface;
                if(!identity&&!identityDrawDepth&&!this._iaOwnSurface&&typeof args[0]==="string"&&isAmbientWindow(this)){
                    surfaceDepth++;
                    try{return ambientDraw(this,method,args,original);}finally{surfaceDepth--;}
                }
                try{
                    if(typeof args[0]==="string"&&!identityDrawDepth&&!this._iaOwnSurface){
                        if(!identity&&statusPresentationScope())args[0]=statusRenderValue(args[0]);
                        else if(!identity&&questSurface(this,args[0]))args[0]=questDraw(this,args[0]);
                        else if(!identity&&isAmbientSurface(this,args[0]))args[0]=projectCaption(args[0]);
                        else {var bookLabel=!identity?questCachedLabel(args[0]):null;
                            if(bookLabel===null&&csvWindowEligible(this))bookLabel=csvProjectDisplay(args[0],csvWindowChoice(this),true);
                            if(bookLabel===null&&!identity)bookLabel=nativeDisplayProjection(args[0],csvWindowChoice(this)?"choice":"surface",this.contents);
                            args[0]=bookLabel!==null?bookLabel:translatedNativeLabel(args[0],identity);}
                        if(!identity&&!statusPresentationScope()&&!isQuestWindow(this)&&typeof Window_Message!=="undefined"&&!(this instanceof Window_Message)&&
                           !(typeof Scene_Name!=="undefined"&&typeof SceneManager!=="undefined"&&SceneManager._scene instanceof Scene_Name)&&
                           languageFor(args[0])==="en"){
                            var cachedEnglish=readyText("en",args[0]);
                            if(cachedEnglish!==null)args[0]=cachedEnglish;
                        }
                    }
                }catch(_){state.errors++;}
                if(identity)identityDrawDepth++;
                surfaceDepth++;
                try{return original.apply(this,args);}
                finally{surfaceDepth--;if(identity)identityDrawDepth--;}
            };
        });
    }
    hookSpecificSurfaces();
    if(!hookGalvCaptionFactory()&&!isMZ)hookCaptionInterpreter();
    if(isMZ)hookMZPresentation();
    // The author's name window is created as a subwindow of Window_Message.
    // Mark that instance, not an arbitrary class or all Japanese short labels.
    if(typeof Window_Message!=="undefined"&&Window_Message.prototype){
        hookSurfaceConversion(Window_Message.prototype,true);
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
        var bitmapReplayDepth=0,bitmapNativeDepth=0,bitmapJobs=[],bitmapPollScheduled=false;
        function bitmapTextRect(bitmap,args){
            var x=Number(args[1]),y=Number(args[2]),mw=Number(args[3]),lh=Number(args[4]);
            if(!isFinite(x)||!isFinite(y)||!integer(bitmap.width)||!integer(bitmap.height)||
               bitmap.width<1||bitmap.height<1)return null;
            if(!isFinite(mw)||mw<=0||mw>bitmap.width)mw=bitmap.width-x;
            if(!isFinite(lh)||lh<=0||lh>bitmap.height)lh=Math.max(16,Number(bitmap.fontSize)||24)+8;
            var fontSize=Math.max(8,Number(bitmap.fontSize)||24),outline=Math.max(0,Number(bitmap.outlineWidth)||0);
            var baseline=Math.round(y+lh/2+fontSize*0.35);
            var pad=Math.min(12,Math.max(2,Math.ceil(outline)+2));
            var left=Math.max(0,Math.floor(x-pad)),top=Math.max(0,Math.floor(baseline-fontSize-outline-3));
            var right=Math.min(bitmap.width,Math.ceil(x+mw+pad));
            var bottom=Math.min(bitmap.height,Math.ceil(baseline+outline+4));
            var w=right-left,h=bottom-top;
            if(w<=0||h<=0||w*h>131072)return null;
            return {x:left,y:top,w:w,h:h};
        }
        function bitmapOverlap(a,b){
            return !!a&&!!b&&a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
        }
        function disposeBitmapJob(job){
            if(!job||job.disposed)return;
            job.valid=false;job.disposed=true;
            var list=job.bitmap&&job.bitmap._iaDrawJobs;
            if(list){var at=list.indexOf(job);if(at>=0)list.splice(at,1);}
            var globalAt=bitmapJobs.indexOf(job);if(globalAt>=0)bitmapJobs.splice(globalAt,1);
            if(job.backup&&typeof job.backup.destroy==="function"){
                try{job.backup.destroy();}catch(_){}
            }
            job.backup=null;
        }
        function restoreBitmapJob(job){
            if(!job||!job.valid||!job.bitmap||!job.backup)return;
            var b=job.bitmap,r=job.rect;
            if(b.width!==job.width||b.height!==job.height||
               typeof b.clearRect!=="function"||typeof b.blt!=="function")return;
            var opacity=b.paintOpacity;
            bitmapReplayDepth++;
            try{
                b.paintOpacity=255;
                b.clearRect(r.x,r.y,r.w,r.h);
                b.blt(job.backup,0,0,r.w,r.h,r.x,r.y);
            }catch(_){state.errors++;}
            finally{
                if(opacity!==undefined)b.paintOpacity=opacity;
                bitmapReplayDepth--;
            }
        }
        function invalidateBitmapJobs(bitmap,rect,restore){
            if(bitmapReplayDepth||!bitmap||!bitmap._iaDrawJobs)return;
            bitmap._iaDrawJobs.slice().forEach(function(job){
                if(!rect||bitmapOverlap(job.rect,rect)){
                    if(restore)restoreBitmapJob(job);
                    disposeBitmapJob(job);
                }
            });
        }
        function captureBitmapJob(bitmap,args,source,raw){
            if(!bitmap||bitmapJobs.length>=64||typeof Bitmap!=="function"||
               typeof bitmap.blt!=="function"||typeof bitmap.clearRect!=="function")return null;
            var rect=bitmapTextRect(bitmap,args);if(!rect)return null;
            invalidateBitmapJobs(bitmap,rect,false);
            var backup=null;
            try{
                backup=new Bitmap(rect.w,rect.h);
                if(!backup||typeof backup.blt!=="function")return null;
                bitmapReplayDepth++;
                backup.blt(bitmap,rect.x,rect.y,rect.w,rect.h,0,0);
            }catch(_){
                if(backup&&typeof backup.destroy==="function")try{backup.destroy();}catch(__){}
                return null;
            }finally{bitmapReplayDepth--;}
            var style={};
            nativeStyleKeys.forEach(function(k){if(bitmap[k]!==undefined)style[k]=bitmap[k];});
            var job={
                bitmap:bitmap,backup:backup,rect:rect,width:bitmap.width,height:bitmap.height,
                source:source,original:raw,args:args.slice(),draw:bitmapDraw,style:style,
                deadline:Date.now()+30000,valid:true,disposed:false,
                scene:typeof SceneManager!=="undefined"?SceneManager._scene:null,formEpoch:formEpoch
            };
            if(!bitmap._iaDrawJobs)bitmap._iaDrawJobs=[];
            bitmap._iaDrawJobs.push(job);bitmapJobs.push(job);
            return job;
        }
        function replayBitmapJob(job,translated){
            if(!job||!job.valid||!job.bitmap||!job.backup)return false;
            var b=job.bitmap,r=job.rect;
            if(b.width!==job.width||b.height!==job.height||
               typeof b.clearRect!=="function"||typeof b.blt!=="function")return false;
            var current={};
            nativeStyleKeys.forEach(function(k){if(b[k]!==undefined)current[k]=b[k];});
            bitmapReplayDepth++;
            try{
                b.paintOpacity=255;
                b.clearRect(r.x,r.y,r.w,r.h);
                b.blt(job.backup,0,0,r.w,r.h,r.x,r.y);
                nativeStyleKeys.forEach(function(k){if(job.style[k]!==undefined)b[k]=job.style[k];});
                var args=job.args.slice();args[0]=translated;
                withQuestGlyphs(b,translated,function(){return job.draw.apply(b,args);});
                state.shown++;
                return true;
            }catch(_){state.errors++;return false;}
            finally{
                nativeStyleKeys.forEach(function(k){if(current[k]!==undefined)b[k]=current[k];});
                bitmapReplayDepth--;
            }
        }
        function pollBitmapJobs(){
            bitmapPollScheduled=false;
            var now=Date.now();
            bitmapJobs.slice().forEach(function(job){
                if(!job.valid||!job.bitmap||job.bitmap._iaOwnerWindow||job.bitmap.width!==job.width||job.bitmap.height!==job.height||
                   inputFormActive()||job.formEpoch!==formEpoch||
                   (typeof SceneManager!=="undefined"&&SceneManager._scene!==job.scene)){
                    disposeBitmapJob(job);return;
                }
                var translated=null;
                try{translated=readyText(job.source,job.original);}catch(_){}
                if(typeof translated==="string"){
                    if(validTranslation(job.source,job.original,translated,false))replayBitmapJob(job,translated);
                    disposeBitmapJob(job);
                }else if(now>=job.deadline||rejectedKeys.get(job.source+"\u0000"+job.original)===Infinity){
                    disposeBitmapJob(job);
                }
            });
            if(bitmapJobs.length&&!bitmapPollScheduled){
                bitmapPollScheduled=true;setTimeout(pollBitmapJobs,100);
            }
        }
        function scheduleBitmapPoll(){
            if(bitmapPollScheduled||!bitmapJobs.length)return;
            bitmapPollScheduled=true;setTimeout(pollBitmapJobs,80);
        }
        function hookBitmapMutator(name,rectFor){
            var original=Bitmap.prototype[name];
            if(typeof original!=="function"||original._iaBitmapMutationWrapped)return;
            var wrapped=function(){
                if(!bitmapReplayDepth){
                    var rect=null;
                    try{rect=rectFor?rectFor(this,arguments):null;}catch(_){}
                    invalidateBitmapJobs(this,rect,false);
                    dropSurfaceGroup(this);
                }
                return original.apply(this,arguments);
            };
            wrapped._iaBitmapMutationWrapped=true;
            Bitmap.prototype[name]=wrapped;
        }
        function rectArgs(args){
            var x=Number(args[0]),y=Number(args[1]),w=Number(args[2]),h=Number(args[3]);
            return isFinite(x)&&isFinite(y)&&isFinite(w)&&isFinite(h)&&w>0&&h>0?
                {x:x,y:y,w:w,h:h}:null;
        }
        hookBitmapMutator("clearRect",function(bitmap,args){return rectArgs(args);});
        hookBitmapMutator("fillRect",function(bitmap,args){return rectArgs(args);});
        hookBitmapMutator("gradientFillRect",function(bitmap,args){return rectArgs(args);});
        hookBitmapMutator("strokeRect",function(bitmap,args){return rectArgs(args);});
        hookBitmapMutator("drawCircle",function(bitmap,args){
            var x=Number(args[0]),y=Number(args[1]),r=Number(args[2]);
            return isFinite(x)&&isFinite(y)&&isFinite(r)&&r>0?{x:x-r,y:y-r,w:r*2,h:r*2}:null;
        });
        hookBitmapMutator("blt",function(bitmap,args){
            var x=Number(args[5]),y=Number(args[6]),w=Number(args[7]),h=Number(args[8]);
            if(!isFinite(w)||w<=0)w=Number(args[3]);
            if(!isFinite(h)||h<=0)h=Number(args[4]);
            return isFinite(x)&&isFinite(y)&&isFinite(w)&&isFinite(h)&&w>0&&h>0?
                {x:x,y:y,w:w,h:h}:null;
        });
        ["clear","fillAll","destroy","resize"].forEach(function(name){
            hookBitmapMutator(name,function(){return null;});
        });

        // Direct Canvas calls bypass Bitmap.drawText. Bind only the contexts
        // of actual RPG Bitmap objects, never the global Canvas prototype.
        // Late replacement is a bounded pixel-verified native redraw, not
        // a new visible layer. The original surface must still be identical.
        var nevCanvasPlugins=Object.create(null),surfaceGroups=[],surfacePoll=false;
        if(isMZ&&typeof $plugins!=="undefined"&&Array.isArray($plugins)){
            $plugins.forEach(function(p){
                if(p&&p.status&&/^NEV_[A-Za-z0-9_]+$/.test(p.name))nevCanvasPlugins[p.name]=true;
            });
        }
        var nevCanvasEnabled=Object.keys(nevCanvasPlugins).length>0;
        var canvasStyles=["font","textAlign","textBaseline","direction","fillStyle","strokeStyle",
            "globalAlpha","globalCompositeOperation","lineWidth","lineCap","lineJoin","miterLimit",
            "shadowColor","shadowBlur","shadowOffsetX","shadowOffsetY","filter","fontKerning",
            "fontStretch","fontVariantCaps","letterSpacing","wordSpacing","textRendering"];
        function surfaceStyle(o,keys){
            var style={};keys.forEach(function(k){if(o[k]!==undefined)style[k]=o[k];});return style;
        }
        function pixelEqual(a,b){
            if(!a||!b||a.width!==b.width||a.height!==b.height||a.data.length!==b.data.length)return false;
            for(var i=0;i<a.data.length;i++)if(a.data[i]!==b.data[i])return false;
            return true;
        }
        function dropGroup(group){
            if(!group||group.disposed)return;
            group.disposed=true;
            if(group.bitmap&&group.bitmap._iaSurfaceGroup===group)group.bitmap._iaSurfaceGroup=null;
            var index=surfaceGroups.indexOf(group);if(index>=0)surfaceGroups.splice(index,1);
            group.before=group.after=null;group.ops=[];
        }
        function dropSurfaceGroup(bitmap){if(bitmap)dropGroup(bitmap._iaSurfaceGroup);}
        function rawContext(bitmap){
            if(!nevCanvasEnabled||!bitmap||!integer(bitmap.width)||!integer(bitmap.height)||
               bitmap.width<1||bitmap.height<1||bitmap.width*bitmap.height>262144)return null;
            try{
                var c=bitmap.context;
                return c&&typeof c.getImageData==="function"&&typeof c.putImageData==="function"?c:null;
            }catch(_){return null;}
        }
        function groupCurrent(group){
            return !group.disposed&&group.bitmap._iaSurfaceGroup===group&&
                group.bitmap.width===group.width&&group.bitmap.height===group.height&&
                !group.bitmap._iaOwnerWindow&&group.bitmap.context===group.ctx&&
                typeof SceneManager!=="undefined"&&SceneManager._scene===group.scene&&
                !inputFormActive()&&group.formEpoch===formEpoch;
        }
        function groupPixels(group){return group.ctx.getImageData(0,0,group.width,group.height);}
        function prepareSurfaceGroup(bitmap,ctx,source){
            if(!ctx||bitmapReplayDepth||bitmapNativeDepth||inputFormActive()||
               bitmap._iaOwnerWindow||typeof SceneManager==="undefined"||!SceneManager._scene)return null;
            var group=bitmap._iaSurfaceGroup;
            try{
                if(group&&(!groupCurrent(group)||group.ctx!==ctx||group.ops.length>=24||
                   !pixelEqual(group.after,groupPixels(group)))){dropGroup(group);group=null;}
                if(group)return group;
                if(!source||surfaceGroups.length>=4||Date.now()<(bitmap._iaSurfaceCooldown||0))return null;
                group={bitmap:bitmap,ctx:ctx,scene:SceneManager._scene,formEpoch:formEpoch,
                    width:bitmap.width,height:bitmap.height,deadline:Date.now()+30000,ops:[],disposed:false};
                group.before=groupPixels(group);group.after=group.before;
                bitmap._iaSurfaceGroup=group;surfaceGroups.push(group);
                return group;
            }catch(_){if(group)dropGroup(group);return null;}
        }
        function finishSurfaceGroup(group,op){
            if(!group||group.disposed)return;
            try{group.ops.push(op);group.after=groupPixels(group);}
            catch(_){dropGroup(group);return;}
            if(!surfacePoll){surfacePoll=true;setTimeout(pollSurfaceGroups,80);}
        }
        function canvasArgs(args,value,limit){
            var result=args.slice();result[0]=value;
            if(isFinite(limit)&&limit>0)result[3]=limit;
            return result;
        }
        function replaySurfaceGroup(group,values){
            var stage=null;
            bitmapReplayDepth++;
            try{
                if(!groupCurrent(group)||!pixelEqual(group.after,groupPixels(group)))return false;
                stage=new Bitmap(group.width,group.height);
                var sc=stage.context;
                if(!sc||typeof sc.putImageData!=="function"||typeof sc.getImageData!=="function")return false;
                function render(translated){
                    sc.putImageData(group.before,0,0);
                    group.ops.forEach(function(op,i){
                        var value=translated?values[i]:null;
                        if(op.method==="bitmap"){
                            nativeStyleKeys.forEach(function(k){if(op.style[k]!==undefined)stage[k]=op.style[k];});
                            var a=op.args.slice();if(value!==null&&value!==undefined)a[0]=value;
                            withQuestGlyphs(stage,a[0],function(){return bitmapDraw.apply(stage,a);});
                        }else{
                            sc.save();
                            try{
                                canvasStyles.forEach(function(k){if(op.style[k]!==undefined)sc[k]=op.style[k];});
                                var a=value!==null&&value!==undefined?canvasArgs(op.args,value,op.limit):op.args;
                                sc[op.method].apply(sc,a);
                            }finally{sc.restore();}
                        }
                    });
                    return sc.getImageData(0,0,group.width,group.height);
                }
                // A missing clip, transform, gradient or intervening paint
                // must cause rejection, not deletion of the game's pixels.
                if(!pixelEqual(render(false),group.after))return false;
                var replacement=render(true);
                if(!groupCurrent(group)||!pixelEqual(group.after,groupPixels(group)))return false;
                group.ctx.putImageData(replacement,0,0);
                var b=group.bitmap;
                if(b._baseTexture&&typeof b._baseTexture.update==="function")b._baseTexture.update();
                else if(typeof b._setDirty==="function")b._setDirty();
                state.shown++;return true;
            }catch(_){state.errors++;return false;}
            finally{bitmapReplayDepth--;if(stage&&typeof stage.destroy==="function")try{stage.destroy();}catch(_){}}
        }
        function pollSurfaceGroups(){
            surfacePoll=false;
            surfaceGroups.slice().forEach(function(group){
                try{
                    if(!groupCurrent(group)){dropGroup(group);return;}
                    var missing=false,changed=false,values=group.ops.map(function(op){
                        if(!op.source)return null;
                        var ready=readyText(op.source,op.args[0]);
                        if(typeof ready==="string"&&validTranslation(op.source,op.args[0],ready,true)){
                            changed=true;return ready;
                        }
                        if(rejectedKeys.get(op.source+"\u0000"+op.args[0])!==Infinity)missing=true;
                        return null;
                    });
                    if(missing&&Date.now()<group.deadline)return;
                    if(changed)replaySurfaceGroup(group,values);
                    dropGroup(group);
                }catch(_){dropGroup(group);}
            });
            if(surfaceGroups.length&&!surfacePoll){surfacePoll=true;setTimeout(pollSurfaceGroups,100);}
        }
        function canvasUiSource(raw){
            if(typeof raw!=="string"||raw.length>240||!raw.trim()||actorNames[raw]||
               /[\r\n\\\x1b<>{}\[\]]/.test(raw)||csvExecutableSyntax(raw))return null;
            var value=raw.trim(),word=value.toLowerCase();
            if(!(displayUiWords[word]||
                /^(?:press|click|tap|hold|move|drag|select|choose|wait|open|close|return|use|keep|release|match|find)\s+\S/i.test(value)||
                /^(?:game over|try again|time left|new game|game paused|game complete|next round|total score|round complete|time remaining)$/i.test(value)))return null;
            // Only enabled, identified author UI plugins; exclude puzzle
            // answers, login strings, editable labels and named characters.
            var matches=String(new Error().stack||"").match(/\bNEV_[A-Za-z0-9_]+(?=\.js(?::|\?))/g)||[];
            if(!matches.some(function(name){return nevCanvasPlugins[name]&&
                !/(?:WifiLogin|WordScramble|Signature|ClueNote|Sport|PicturePosHelper|Tinker|Message|DialogUI)/i.test(name);}))return null;
            return displaySource(raw,"surface")==="en"?"en":null;
        }
        function canvasCanStage(ctx){
            try{
                var m=ctx.getTransform();
                return m.a===1&&m.b===0&&m.c===0&&m.d===1&&m.e===0&&m.f===0&&
                    ctx.globalCompositeOperation==="source-over"&&
                    typeof ctx.fillStyle==="string"&&typeof ctx.strokeStyle==="string";
            }catch(_){return false;}
        }
        function bindCanvasContext(bitmap,ctx){
            if(!nevCanvasEnabled||!ctx||ctx._iaCanvasBound)return ctx;
            try{
                Object.defineProperty(ctx,"_iaCanvasBound",{value:true});
                ["fillText","strokeText"].forEach(function(method){
                    var original=ctx[method];if(typeof original!=="function")return;
                    ctx[method]=function(){
                        if(this!==ctx||bitmapReplayDepth||bitmapNativeDepth||identityDrawDepth||surfaceDepth||
                           bitmap._iaOwnerWindow||inputFormActive())return original.apply(this,arguments);
                        var args=Array.prototype.slice.call(arguments),source=canvasUiSource(args[0]),limit=null;
                        if(source){
                            try{
                                var natural=Number(ctx.measureText(args[0]).width),given=Number(args[3]);
                                limit=isFinite(given)&&given>0?given:natural;
                                var value=readyText(source,args[0]);
                                if(value===null)value=englishLabel(args[0]);
                                if(typeof value==="string"&&value!==args[0]){
                                    args=canvasArgs(args,value,limit);source=null;
                                    if(method==="fillText")state.shown++;
                                }else if(value===null)firstViewRequest(source,args[0]);
                                else source=null;
                            }catch(_){source=null;}
                        }
                        var group=null;
                        if(canvasCanStage(ctx)&&rawContext(bitmap)===ctx)group=prepareSurfaceGroup(bitmap,ctx,source);
                        else dropSurfaceGroup(bitmap);
                        if(bitmap._iaDrawJobs)invalidateBitmapJobs(bitmap,null,false);
                        var style=group?surfaceStyle(ctx,canvasStyles):null,out;
                        try{out=original.apply(ctx,args);}
                        catch(e){dropGroup(group);throw e;}
                        if(group)finishSurfaceGroup(group,{method:method,args:args,source:source,style:style,limit:limit});
                        return out;
                    };
                });
            }catch(_){}
            return ctx;
        }
        if(nevCanvasEnabled){
            var contextDescriptor=Object.getOwnPropertyDescriptor(Bitmap.prototype,"context");
            if(contextDescriptor&&contextDescriptor.configurable&&typeof contextDescriptor.get==="function"){
                Object.defineProperty(Bitmap.prototype,"context",{
                    configurable:true,enumerable:contextDescriptor.enumerable,
                    get:function(){return bindCanvasContext(this,contextDescriptor.get.call(this));}
                });
            }
        }
        function callBitmapDraw(bitmap,args){
            bitmapNativeDepth++;
            try{return withQuestGlyphs(bitmap,args[0],function(){return bitmapDraw.apply(bitmap,args);});}
            finally{bitmapNativeDepth--;}
        }
        Bitmap.prototype.drawText=function(){
            if(bitmapReplayDepth||inputFormActive()||
               (typeof Window_Message!=="undefined"&&this._iaOwnerWindow instanceof Window_Message))return callBitmapDraw(this,arguments);
            var args=Array.prototype.slice.call(arguments),raw=typeof args[0]==="string"?args[0]:null;
            if(raw&&!identityDrawDepth&&statusPresentationScope()){
                args[0]=statusRenderValue(raw);
                return callBitmapDraw(this,args);
            }
            if(raw&&visuQuestBitmapScope(this)){
                args[0]=visuQuestBitmapText(this,raw);
                return callBitmapDraw(this,args);
            }
            if(raw&&!identityDrawDepth&&ultraHudScope()){
                args[0]=ultraHudRender(raw);return callBitmapDraw(this,args);
            }
            var direct=!!(raw&&!surfaceDepth&&!identityDrawDepth&&!this._iaOwnerWindow),job=null,source=null,group=null;
            if(!bitmapReplayDepth&&this._iaDrawJobs)invalidateBitmapJobs(this,bitmapTextRect(this,args),false);
            if(!direct)dropSurfaceGroup(this);
            try{
                if(!identityDrawDepth&&raw&&raw.length>=1){
                    var label=questCachedLabel(raw);
                    if(label===null)label=csvPlainLabel(raw);
                    if(label===null)label=nativeDisplayProjection(raw,"surface",this);
                    args[0]=label!==null?label:translatedNativeLabel(raw,false);
                    if(direct&&label===null&&args[0]===raw){
                        source=displaySource(raw,"surface");
                        if(source&&readyText(source,raw)!==null)source=null;
                    }
                }
            }catch(_){state.errors++;}
            var bitmap=this,ctx=direct?rawContext(bitmap):null;
            if(ctx)group=prepareSurfaceGroup(bitmap,ctx,source);
            else if(direct&&source&&!nevCanvasEnabled)job=captureBitmapJob(bitmap,args,source,raw);
            var style=group?surfaceStyle(bitmap,nativeStyleKeys):null,out;
            try{out=callBitmapDraw(bitmap,args);}catch(e){dropGroup(group);if(job)disposeBitmapJob(job);throw e;}
            if(group)finishSurfaceGroup(group,{method:"bitmap",args:args,source:source,style:style});
            if(job)scheduleBitmapPoll();
            return out;
        };
        var measure=Bitmap.prototype.measureTextWidth;
        if(typeof measure==="function")Bitmap.prototype.measureTextWidth=function(text){
            if(inputFormActive())return measure.apply(this,arguments);
            var bitmap=this,args=Array.prototype.slice.call(arguments),label=null;
            if(!identityDrawDepth&&statusPresentationScope()){args[0]=statusRenderValue(text);return measure.apply(this,args);}
            if(visuQuestBitmapScope(bitmap)){args[0]=visuQuestBitmapText(bitmap,text);return measure.apply(this,args);}
            if(!identityDrawDepth&&ultraHudScope()){args[0]=ultraHudRender(text);return measure.apply(this,args);}
            try{
                label=csvPlainLabel(text);
                if(label===null)label=nativeDisplayProjection(text,"surface",bitmap);
            }catch(_){}
            if(label!==null)args[0]=label;
            return withQuestGlyphs(bitmap,args[0],function(){return measure.apply(bitmap,args);});
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
    if(tsv.detected)text=text.replace(/(?:\\|\x1b)[.|]/g,"");
    // Resolve only the CSV dialect's leading, color-delimited actor name.
    // No event variable, script or actual actor record is modified.
    if(tableStats.root){
        var head=/^((?:\\|\x1b)c\[\d{1,3}\]\[)(?:\\|\x1b)n\[(\d{1,5})\](\](?:\\|\x1b)c\[\d{1,3}\]\r?\n)/i.exec(text);
        if(head){
            if(typeof $gameActors==="undefined"||!$gameActors||typeof $gameActors.actor!=="function")return null;
            var actor=$gameActors.actor(Number(head[2])),name=actor&&typeof actor.name==="function"?actor.name():null;
            if(typeof name!=="string"||!name.trim()||name.length>100||/[\r\n\\\x1b<>\[\]]/.test(name))return null;
            text=head[1]+name+head[3]+text.slice(head[0].length);
        }
    }
    var re=/<\/?wordwrap>|\\n[cr]?<[^\\<>\r\n]{1,75}>|(?:\\|\x1b)(?:ALIGN\[(?:left|center|right)\]|A[CLR](?![A-Za-z])|c\[\d{1,3}\]|m\[[A-Za-z0-9 _\-]{1,60}\]|i\[\d{1,4}\])|\r?\n|<br>/gi;
    var parts=[],flat="",at=0,m,color=null,seen=false,alignment=null;
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
        // NEV_DialogUI processes alignment while rendering, after createTextState.
        // Only a leading whole-message alignment is safe for a late repaint.
        var align=/^(?:\\|\x1b)(?:A([CLR])|ALIGN\[(left|center|right)\])$/i.exec(code);
        if(align){
            if(seen)return null;
            var mode=align[2]?align[2].toLowerCase():({C:"center",L:"left",R:"right"})[align[1].toUpperCase()];
            if(alignment&&alignment!==mode)return null;
            alignment=mode;continue;
        }
        if(/^(?:\r?\n|<br>)$/i.test(code)){parts.push({text:"\n",color:color});flat+="\n";continue;}
        var icon=/^(?:\\|\x1b)i\[(\d{1,4})\]$/i.exec(code);
        if(icon){var id=Number(icon[1]);if(id>4095)return null;
            parts.push({text:"\uFFFC",color:color,icon:id});flat+="\uFFFC";seen=true;continue;}
        color=formatColor(code);if(color===null)return null;
    }
    if(!prose(text.slice(at))||!flat.trim())return null;
    return {parts:parts,flat:flat,alignment:alignment};
}
function plainCompare(text){return text.replace(/\s+/g," ").trim();}
var nativeStyleKeys=["fontFace","fontSize","fontBold","fontItalic","textColor","outlineColor","outlineWidth","paintOpacity"];
function snapshotMessage(win,ticket){
    ticket.formEpoch=formEpoch;
    var ts=win._textState,b=win.contents;
    if(!ts||!b||typeof ts.text!=="string"||!integer(ts.index)||ts.index!==0||
       !integer(b.width)||!integer(b.height)||b.width>4096||b.height>2048||
       typeof b.clearRect!=="function"||typeof b.blt!=="function"||
       (typeof win.textColor!=="function"&&!(isMZ&&typeof ColorManager!=="undefined"&&typeof ColorManager.textColor==="function"))||
       (isMZ&&ts.rtl))return;
    var original=nativeRenderParts(ticket.visualOriginal||ticket.displayed),native=nativeRenderParts(ts.text);
    if(!original||!native||plainCompare(original.flat)!==plainCompare(native.flat))return;
    // Native plugin conversion can change a macro or text alignment.
    // Require the same visible color runs, not merely the same words.
    function signature(parsed){
        return parsed.parts.filter(function(x){return x.text.trim();})
            .map(function(x){return String(x.color)+":"+plainCompare(x.text)+(x.icon!==undefined?":"+x.icon:"");}).join("\u0002");
    }
    if(signature(original)!==signature(native))return;
    var x=typeof ts.x==="number"?ts.x:ts.left,y=ts.y,h=ts.height;
    if(original.alignment&&native.alignment&&original.alignment!==native.alignment)return;
    var alignment=original.alignment||native.alignment||
        (Array.isArray(ts._lineOffsets)&&/^(?:left|center|right)$/.test(win._textAlignment||"")?win._textAlignment:null);
    var rightPad=0;
    if(alignment){
        var pad=typeof win.itemPadding==="function"?Number(win.itemPadding()):0;
        if(!isFinite(pad)||pad<0||pad>64)return;
        rightPad=pad;
        var faceKnown=typeof ticket.message.faceName==="function",hasFace=faceKnown&&!!ticket.message.faceName();
        var baseX=typeof ts._baseX==="number"&&isFinite(ts._baseX)?ts._baseX:x;
        // createTextState runs before MZ applies the portrait margin.
        // Do not clear the face if an author's alignment starts inside it.
        if(hasFace&&baseX<x&&original.alignment)return;
        x=Math.max(x,baseX);
        if(original.alignment&&faceKnown&&!hasFace&&typeof win.itemPadding==="function")x=pad;
    }
    if(!isFinite(x)||!isFinite(y)||!isFinite(h)||x<0||y<0||h<8||h>128||
       x>=b.width||y>=b.height)return;
    var style={};
    nativeStyleKeys.forEach(function(k){if(b[k]!==undefined)style[k]=b[k];});
    ticket.geometry={bitmap:b,x:Math.floor(x),y:Math.floor(y),line:Math.ceil(h),
        width:b.width,height:b.height,style:style,original:native.flat,align:alignment,rightPad:rightPad};
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
        width=geometry.width-left-(geometry.rightPad||0),height=geometry.height-top,ops=[],x=0,y=0;
    if(parsed.alignment&&parsed.alignment!==geometry.align)return null;
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
            var r=w.runs[k],c=r.color===null?geometry.style.textColor:nativeTextColor(win,r.color);
            if(typeof c!=="string")return null;
            ops.push({text:r.text,x:x,y:y,w:Math.max(1,Math.ceil(lengths[k])+4),advance:lengths[k],color:c,icon:r.icon});
            x+=lengths[k];
        }
    }
    if(geometry.align==="center"||geometry.align==="right"){
        var rowWidths=Object.create(null);
        ops.forEach(function(op){rowWidths[op.y]=Math.max(rowWidths[op.y]||0,op.x+op.advance);});
        ops.forEach(function(op){var free=Math.max(0,width-rowWidths[op.y]);op.x+=Math.floor(geometry.align==="center"?free/2:free);});
    }
    return ops.length?ops:null;
}
function replaceNativeMessage(win,ticket){
    if(inputFormActive()||(ticket.formEpoch!==undefined&&ticket.formEpoch!==formEpoch))return false;
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
    if(inputFormActive()||(ticket.formEpoch!==undefined&&ticket.formEpoch!==formEpoch)){hideLate(win);return;}
    if(typeof SceneManager==="undefined"||!ticket.scene||SceneManager._scene!==ticket.scene||
       typeof $gameMessage==="undefined"||$gameMessage!==ticket.message||
       !$gameMessage.hasText()||$gameMessage.allText()!==ticket.displayed){
        hideLate(win);return;
    }
    if(!ticket.result||ticket.drawn||!win.pause||win._textState||
       (typeof win.isAnySubWindowActive==="function"&&win.isAnySubWindowActive())||
       (typeof $gameMessage.isChoice==="function"&&$gameMessage.isChoice()))return;
    ticket.drawn=true;
    if(ticket.pages<=1&&replaceNativeMessage(win,ticket)){state.shown++;lateStats.shown++;if(ticket.tsv){tsv.shown++;tsv.late++;}}
    else lateStats.unsupported++;
}
// R6: defer native message and choice presentation, not the game loop.
// All asynchronous results go into the existing validated cache.
var FIRST_VIEW_LIMIT=8000,FIRST_VIEW_OFFLINE=1500;
function firstViewRequest(source,text){
    if(!source||typeof text!=="string"||!text||remNativeSpanishText(text)||externalLocalizationReference(text))return;
    addPrefetch(text,true,source);
    var key=source+"\u0000"+text;
    // The message/choice currently blocking presentation bypasses disk-cache
    // warmup and the background-prefetch cap. translate() still deduplicates
    // requests and enforces its hard foreground concurrency limit.
    if(!state.connected||csvLiveRequests.has(key)||rejectedKeys.get(key)>Date.now()){
        nextPrefetch();return;
    }
    if(csvLiveRequests.size>=96){nextPrefetch();return;}
    csvLiveRequests.set(key,true);
    requestVisible(source,text).then(function(){
        csvLiveRequests.delete(key);nextPrefetch();
    },function(){
        csvLiveRequests.delete(key);state.errors++;nextPrefetch();
    });
    nextPrefetch();
}
function choiceDisplay(win,raw,requestMissing){
    if(inputFormActive()||identityDrawDepth||typeof raw!=="string"||actorNames[raw])return null;
    var entries=scriptVariableEntries(raw);
    if(entries.length)return scriptVariableRender(raw,entries,requestMissing);
    if(tsvRef(raw)&&tsv.valid){
        var locale=tsvProbeLocale(win);
        if(locale)return tsvTranslatedKeys(raw,locale,requestMissing);
    }
    var externalReady=iavraReadyValue(raw,requestMissing);
    if(externalReady!==null)return externalReady;
    var projected=csvProjectDisplay(raw,true,requestMissing);
    if(tsvExcluded(raw))return null;
    var source=displaySource(raw,"choice");if(!source)return null;
    var value=readyText(source,raw);
    if(value!==null)return value;
    if(requestMissing)firstViewRequest(source,raw);
    return null;
}
function firstViewMissing(win,raw,choice){
    if(typeof raw!=="string"||!raw.trim()||raw.length>1800||actorNames[raw]||remNativeSpanishText(raw)||csvExecutableSyntax(raw))return false;
    var remFallback=remNativeFallback(raw);
    if(remFallback){
        if(readyText("en",remFallback)!==null||rejectedKeys.get("en\u0000"+remFallback)===Infinity)return false;
        firstViewRequest("en",remFallback);return true;
    }
    var externalKey=iavraResolveText(raw);
    if(externalKey){
        if(readyText(externalKey.source,externalKey.text)!==null)return false;
        if(rejectedKeys.get(externalKey.source+"\u0000"+externalKey.text)===Infinity)return false;
        firstViewRequest(externalKey.source,externalKey.text);return true;
    }
    if(iavra.detected&&iavra.loading&&iavraHasReference(raw))return true;
    if(tsv.detected&&tsvRef(raw)){
        tsvPrioritize(raw,true);
        if(!tsv.valid)return !tsv.done;
        var locale=tsvProbeLocale(win);
        if(locale){
            if(tsvResolveKeys(raw,locale)===null)return false;
            return tsvTranslatedKeys(raw,locale,true)===null;
        }
        // No confirmed locale: preserve the native localization path.
        // Never substitute an unrelated language column to satisfy the wait.
        return false;
    }
    if(!choice){
        var scripted=scriptMessagePlan(raw);
        if(scripted){
            if(authoredRead(scripted,true)!==null)return false;
            return rejectedKeys.get(scripted.source+"\u0000"+scripted.body)!==Infinity;
        }
    }
    var entries=scriptVariableEntries(raw);
    if(entries.length)return scriptVariableRender(raw,entries,true)===null;
    if(choice&&choiceDisplay(win,raw,true)!==null)return false;
    if(choice&&(externalTables()||isMZ)){
        var variable=/^(?:\\|\x1b)v\[(\d{1,6})\]$/i.exec(raw);
        if(variable&&typeof $gameVariables!=="undefined"&&$gameVariables&&typeof $gameVariables.value==="function"){
            var value=$gameVariables.value(Number(variable[1]));
            if(typeof value!=="string"||actorNames[value]||!languageFor(value)||csvExecutableSyntax(value))return false;
            raw=value;
        }
    }
    var source=displaySource(raw,choice?"choice":"message");if(!source)return false;
    if(readyText(source,raw)!==null||(tableStats.root&&csvKnownReady(raw)!==null))return false;
    if(rejectedKeys.get(source+"\u0000"+raw)===Infinity)return false;
    firstViewRequest(source,raw);
    if(!choice&&raw.indexOf("\n")>=0){
        raw.split(/\r?\n/).forEach(function(line){
            if(hasProse(source,line)&&readyText(source,line)===null)
                firstViewRequest(source,line);
        });
    }
    return true;
}
function firstViewWait(win){
    if(inputFormActive()||win.pause||win._textState||typeof win.isAnySubWindowActive==="function"&&win.isAnySubWindowActive())return false;
    var m=typeof $gameMessage!=="undefined"?$gameMessage:null;
    if(!m)return false;
    var raw=typeof m.allText==="function"?m.allText():"";
    var choices=typeof m.choices==="function"?m.choices():m._choices;
    if(!Array.isArray(choices))choices=[];
    if(!raw&&!choices.length)return false;
    // First presentation is gated for MV and MZ. Large inventories only pause
    // background prefetch; they never disable the request for visible text.
    var missing=raw&&firstViewMissing(win,raw,false);
    for(var j=0;j<choices.length;j++)if(firstViewMissing(win,choices[j],true))missing=true;
    if(!missing){win._iaFirstGate=null;return false;}
    var now=Date.now(),g=win._iaFirstGate;
    if(!g){g={started:now};win._iaFirstGate=g;}
    var viewLimit=FIRST_VIEW_LIMIT;
    var offlineLimit=FIRST_VIEW_OFFLINE;
    if(now-g.started>=viewLimit||(!state.connected&&now-g.started>=offlineLimit)){
        win._iaFirstGate=null;return false;
    }
    return true;
}
function hookFirstView(proto){
    if(typeof proto.updateWait!=="function"||typeof proto.canStart!=="function")return;
    var wait=proto.updateWait;
    proto.updateWait=function(){
        if(wait.apply(this,arguments))return true;
        try{return firstViewWait(this);}catch(_){state.errors++;return false;}
    };
    if(typeof Game_Message!=="undefined"&&typeof Game_Message.prototype.clear==="function"){
        var clear=Game_Message.prototype.clear;
        Game_Message.prototype.clear=function(){
            var out=clear.apply(this,arguments);this._iaFirstGeneration=(this._iaFirstGeneration||0)+1;return out;
        };
    }
}
// 111_InputForm creates two DOM nodes. Stop bubbling after the author's
// own handlers, never preventDefault (editing, Enter and IME must work).
var formEpoch=0,formWasOpen=false;
function inputFormNodes(){
    if(typeof document==="undefined"||!document||typeof document.getElementById!=="function")return null;
    var input=document.getElementById("_111_input"),submit=document.getElementById("_111_submit");
    return input?{input:input,submit:submit}:null;
}
function builtinNameInputActive(){
    var scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
    if(!scene)return false;
    if(typeof Scene_Name!=="undefined"&&scene instanceof Scene_Name)return true;
    var edit=scene._editWindow||scene._nameEditWindow;
    var input=scene._inputWindow||scene._nameInputWindow;
    if(typeof Window_NameEdit!=="undefined"&&edit instanceof Window_NameEdit)return true;
    if(typeof Window_NameInput!=="undefined"&&input instanceof Window_NameInput)return true;
    return false;
}
function inputFormActive(){
    if(builtinNameInputActive())return true;
    if(typeof Input!=="undefined"&&Input.form_mode===true)return true;
    return !!inputFormNodes();
}
function hookBuiltinNameInputScene(){
    if(typeof Scene_Name==="undefined"||!Scene_Name.prototype)return;
    ["start","terminate"].forEach(function(method){
        var original=Scene_Name.prototype[method];
        if(typeof original!=="function"||original._iaNameInputSceneWrapped)return;
        var wrapped=function(){
            formEpoch++;
            if(method==="start")formWasOpen=true;
            try{return original.apply(this,arguments);}
            finally{if(method==="terminate")formWasOpen=false;}
        };
        wrapped._iaNameInputSceneWrapped=true;
        Scene_Name.prototype[method]=wrapped;
    });
}
function protectInputForm(){
    var nodes=inputFormNodes(),active=!!nodes||inputFormActive();
    if(active!==formWasOpen){formWasOpen=active;formEpoch++;}
    if(!nodes)return;
    [nodes.input,nodes.submit].forEach(function(node){
        if(!node||node._iaKeyboardIsolated||typeof node.addEventListener!=="function")return;
        node._iaKeyboardIsolated=true;
        ["keydown","keyup","keypress"].forEach(function(type){
            node.addEventListener(type,function(event){event.stopPropagation();},false);
        });
    });
    if(nodes.submit&&String(nodes.submit.type).toLowerCase()==="submit"&&nodes.submit.value==="決定")
        nodes.submit.value="Aceptar";
}
function iaChoiceValues(message){
    var values=[];
    try{values=message&&typeof message.choices==="function"?message.choices():message&&message._choices;}catch(_){}
    return Array.isArray(values)?values.slice():[];
}
function iaChoiceProjection(win,raw){
    var values=raw.slice(),waiting=false;
    for(var i=0;i<raw.length;i++){
        if(typeof raw[i]!=="string")continue;
        var external=iavraResolveText(raw[i]);
        if(external){
            var externalReady=readyText(external.source,external.text);
            if(externalReady!==null){values[i]=externalReady;continue;}
            values[i]=external.text;
            if(firstViewMissing(win,raw[i],true))waiting=true;
            continue;
        }
        var ready=choiceDisplay(win,raw[i],false);
        if(typeof ready==="string"){values[i]=ready;continue;}
        if(firstViewMissing(win,raw[i],true))waiting=true;
    }
    return {values:values,waiting:waiting};
}
function iaRunNativeChoiceStart(win,original,args,message,values){
    var oldChoices=message._choices;
    var hadOwnChoices=Object.prototype.hasOwnProperty.call(message,"choices");
    var oldChoicesMethod=message.choices;
    var projected=values.slice();
    try{
        message._choices=projected;
        if(typeof oldChoicesMethod==="function")message.choices=function(){return projected;};
        win._iaChoiceNativeStart=true;
        return original.apply(win,args);
    }finally{
        win._iaChoiceNativeStart=false;
        message._choices=oldChoices;
        if(hadOwnChoices)message.choices=oldChoicesMethod;
        else if(typeof oldChoicesMethod==="function")delete message.choices;
    }
}
function hookChoiceFirstView(){
    if(typeof Window_ChoiceList==="undefined"||!Window_ChoiceList.prototype)return;
    var proto=Window_ChoiceList.prototype,original=proto.start;
    if(typeof original!=="function"||original._iaFirstViewChoiceWrapped)return;
    var wrapped=function(){
        if(this._iaChoiceNativeStart||inputFormActive())return original.apply(this,arguments);
        var message=typeof $gameMessage!=="undefined"?$gameMessage:null;
        var raw=message?iaChoiceValues(message):[];
        if(!message||!raw.length||raw.length>24)return original.apply(this,arguments);
        var initial=iaChoiceProjection(this,raw);
        if(!initial.waiting)return iaRunNativeChoiceStart(this,original,arguments,message,initial.values);
        var key=JSON.stringify(raw),generation=message._iaFirstGeneration||0;
        var existing=this._iaChoiceGate;
        if(existing&&existing.message===message&&existing.key===key&&existing.generation===generation&&!existing.done)return;
        var gate={message:message,key:key,generation:generation,raw:raw.slice(),
            scene:typeof SceneManager!=="undefined"?SceneManager._scene:null,
            started:Date.now(),done:false,args:Array.prototype.slice.call(arguments)};
        this._iaChoiceGate=gate;
        var self=this;
        function poll(){
            if(self._iaChoiceGate!==gate||gate.done)return;
            var current=typeof $gameMessage!=="undefined"?$gameMessage:null;
            var currentChoices=current?iaChoiceValues(current):[];
            var currentScene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
            if(current!==gate.message||currentScene!==gate.scene||
               current&&(current._iaFirstGeneration||0)!==gate.generation||
               JSON.stringify(currentChoices)!==gate.key){
                gate.done=true;self._iaChoiceGate=null;return;
            }
            var projectedNow=iaChoiceProjection(self,gate.raw);
            var elapsed=Date.now()-gate.started;
            var limit=state.connected?FIRST_VIEW_LIMIT:FIRST_VIEW_OFFLINE;
            if(!projectedNow.waiting||elapsed>=limit){
                gate.done=true;self._iaChoiceGate=null;
                return iaRunNativeChoiceStart(self,original,gate.args,gate.message,projectedNow.values);
            }
            setTimeout(poll,40);
        }
        setTimeout(poll,0);
    };
    wrapped._iaFirstViewChoiceWrapped=true;
    proto.start=wrapped;
}
function hookInputForm(){
    if(typeof Game_Interpreter==="undefined"||!Game_Interpreter.prototype||
       typeof Game_Interpreter.prototype._inputForm!=="function")return;
    var original=Game_Interpreter.prototype._inputForm;
    Game_Interpreter.prototype._inputForm=function(){
        var out=original.apply(this,arguments);
        try{protectInputForm();}catch(_){state.errors++;}
        return out;
    };
}

// R7: explicitly authored MZ display fields. Never execute a script
// during inventory or translate an entire script, filename, or variable ID.
var authoredDisplay=new Map(),scriptLocale="",scriptSystem=false,scriptProfile=false;
var scriptStats={dialogues:0,pictures:0,shown:0};
function enabledTextPicture(){
    return isMZ&&typeof $plugins!=="undefined"&&Array.isArray($plugins)&&$plugins.some(function(p){return p&&p.status&&p.name==="TextPicture";});
}
// Additional display-variable contracts, enabled only after the primary
// script dialect has been proven. Never change the actual variable values.
var displayVariableNames=null;
var displayFieldNames={19:"ITEM Name Text",64:"Description TEXT",140:"NPC Name",241:"Quiz Question Line 1",
    242:"Answer1",243:"Answer2",244:"Answer3",245:"Answer4",247:"Quiz Question Line 2",
    248:"Quiz Question Line 3",249:"Quiz Question Line 4",266:"Blueprint Description",271:"Blueprint Name 1",
    272:"Blueprint Name 2",273:"Blueprint Name 3",274:"Blueprint Name 4",275:"Blueprint Title"};
var genericNpcRoles={"Stranger":"Desconocido","Employee":"Empleado","Receptionist":"Recepcionista",
    "Executive":"Ejecutivo","Patron":"Cliente","Patient":"Paciente","Resident":"Residente","Customer":"Cliente",
    "Technician":"Técnico","Volunteer":"Voluntario","Fisherman":"Pescador","Bartender":"Camarero",
    "Lab Worker":"Trabajador de laboratorio","Dock Worker":"Estibador","Shop Manager":"Encargado de tienda",
    "Mysterious Man":"Hombre misterioso","Lost Man":"Hombre perdido","Director":"Director",
    "Clerk":"Dependiente","Shopper":"Comprador","Housekeeper":"Encargado de limpieza",
    "Protestor":"Manifestante","Parishioner":"Feligrés","Influencer":"Influencer"};
var displayLiteralProof=new Map(),itemDataRef=null,itemDisplayProof=new Set();
function profileField(id){
    var names=typeof $dataSystem!=="undefined"&&$dataSystem&&Array.isArray($dataSystem.variables)?
        $dataSystem.variables:displayVariableNames;
    return scriptProfileActive()&&names&&Object.prototype.hasOwnProperty.call(displayFieldNames,id)&&names[id]===displayFieldNames[id];
}
function profileItemField(id){return id===19||id===64||id===266||(id>=271&&id<=275);}
function plainDisplayValue(value){
    return typeof value==="string"&&!!value.trim()&&value.length<=1800&&!/[\\\x1b<>{}\u0000\uFFFD]/.test(value)&&!csvExecutableSyntax(value);
}
function displayVariableSource(id,value){
    if(!plainDisplayValue(value)||actorNames[value])return null;
    // Quiz answer names and proper nouns are not blindly translated.
    if(id>=242&&id<=245&&/^[A-Z][a-z]+(?:[ -][A-Z][a-z]+){0,3}$/.test(value)&&!languageFor(value))return null;
    var source=authoredSource(value,true);
    if(source)return source;
    // A proven item label may be a single word. Identity variables never
    // enter this route. It still passes the existing model/cache validator.
    return profileItemField(id)&&/^[A-Za-z][A-Za-z' -]{1,60}$/.test(value)?"en":null;
}
function rememberDisplayLiteral(cmd,priority){
    var a=cmd.parameters;
    if(a.length!==5||a[0]!==a[1]||a[2]!==0||a[3]!==4||!profileField(a[0])||
       typeof a[4]!=="string"||a[4].length>4000)return;
    var value;
    try{value=JSON.parse(a[4]);}catch(_){return;}
    if(!plainDisplayValue(value))return;
    var id=a[0],key=id+"\u0000"+value;
    if(displayLiteralProof.size<10000)displayLiteralProof.set(key,true);
    if(id!==140){
        var source=displayVariableSource(id,value);
        if(source)authoredRemember(source,value,priority);
    }
}
function knownItemDisplay(value){
    if(typeof $dataItems==="undefined"||!Array.isArray($dataItems))return false;
    if(itemDataRef!==$dataItems){
        itemDataRef=$dataItems;itemDisplayProof.clear();
        $dataItems.forEach(function(row){
            if(!row)return;
            ["name","description"].forEach(function(k){if(plainDisplayValue(row[k])&&itemDisplayProof.size<30000)itemDisplayProof.add(row[k]);});
        });
    }
    return itemDisplayProof.has(value);
}
function scriptVariableEntry(id){
    if(!profileField(id)||typeof $gameVariables==="undefined"||!$gameVariables||typeof $gameVariables.value!=="function")return null;
    var value=$gameVariables.value(id);
    if(!plainDisplayValue(value)||actorNames[value])return null;
    if(id===140){
        if(!Object.prototype.hasOwnProperty.call(genericNpcRoles,value)||genericNpcRoles[value]===value)return null;
        return {body:value,source:"en",prefix:"",suffix:"",fixed:genericNpcRoles[value]};
    }
    if(profileItemField(id)&&!knownItemDisplay(value)&&!displayLiteralProof.has(id+"\u0000"+value))return null;
    var source=displayVariableSource(id,value);
    return source?{source:source,body:value,prefix:"",suffix:""}:null;
}
function scriptVariableEntries(raw){
    if(!isMZ||typeof raw!=="string"||raw.length>1800||!/\\v\[/i.test(raw)||!scriptProfileActive())return [];
    var entries=[],seen=Object.create(null);
    raw.replace(/\\v\[(\d{1,6})\]/gi,function(token,n){
        var id=Number(n);if(seen[id])return token;seen[id]=true;
        var entry=scriptVariableEntry(id);
        if(entry){entry.id=id;entries.push(entry);}
        return token;
    });
    return entries;
}
function scriptVariableRender(raw,entries,requestMissing){
    if(!entries.length)return null;
    var translated=Object.create(null),missing=false;
    entries.forEach(function(entry){
        var value=authoredRead(entry,requestMissing);
        // Inserting a variable into the native raw message must not
        // introduce new controls (unlike a variable expanded after escape parsing).
        if(value===null||!plainDisplayValue(value))missing=true;
        else translated[entry.id]=value;
    });
    var base=raw,source=languageFor(raw);
    if(source&&hasProse(source,raw)){
        base=readyText(source,raw);
        if(base===null){missing=true;if(requestMissing)firstViewRequest(source,raw);}
    }
    if(missing)return null;
    return base.replace(/\\v\[(\d{1,6})\]/gi,function(token,n){
        return Object.prototype.hasOwnProperty.call(translated,Number(n))?translated[Number(n)]:token;
    });
}
function scriptVariableKey(raw){
    return scriptVariableEntries(raw).map(function(e){return [e.id,e.body];});
}

function scriptSystemContract(data){
    var v=data&&data.variables;
    return isMZ&&Array.isArray(v)&&v[21]==="MESSAGE HOLDER"&&v[25]==="MESSAGE HOLDER"&&v[26]==="SYNTAX HOLDER";
}
function scriptEventContract(data){
    if(!Array.isArray(data))return false;
    return data.some(function(e){
        if(!e||!Array.isArray(e.list))return false;
        var lines=e.list;
        var read=lines.some(function(c,i){
            if(c.code!==355||!c.parameters||c.parameters[0]!=='var slice = $gameVariables.value(21).indexOf(".");')return false;
            var want=["var message = $gameVariables.value(21).slice(slice + 1);","var syntax = $gameVariables.value(21).slice(0,slice);","$gameVariables.setValue(25, message);","$gameVariables.setValue(26, syntax);"];
            return want.every(function(s,j){var n=lines[i+j+1];return n&&n.code===655&&n.parameters&&n.parameters[0]===s;});
        });
        return read&&lines.some(function(c){return c.code===401&&c.parameters&&/^\\v\[25\](?:\\Wait\[\d+\])?$/i.test(c.parameters[0]);});
    });
}
function scriptProfileActive(){
    if(!isMZ)return false;
    if(scriptProfile)return true;
    if(typeof $dataSystem!=="undefined"&&scriptSystemContract($dataSystem)&&
       typeof $dataCommonEvents!=="undefined"&&$dataCommonEvents){
        if(scriptEventContract($dataCommonEvents)){scriptProfile=true;scriptLocale=$dataSystem.locale||"";displayVariableNames=$dataSystem.variables;}
    }
    return scriptProfile;
}
function authoredSource(text,declared){
    if(typeof text!=="string"||!text.trim()||text.length>1800||actorNames[text]||
       csvExecutableSyntax(text)||/[\u0000\uFFFD]|^\s*(?:\/[A-Za-z]|\/\/|[=$@#])|(?:\\|\x1b)(?:js|eval|script)(?:\b|\[)|<script\b/i.test(text))return null;
    var prose=visibleProse(text).trim();
    if(!prose||/^[A-Za-z0-9_./-]+\.(?:js|json|png|jpg|webm|ogg|mp4)$/i.test(prose))return null;
    if(isJapanese(prose))return "ja";
    var source=languageFor(text);
    if(source)return source;
    var english=declared||/^en(?:[_-]|$)/i.test(scriptLocale)||
        (typeof $dataSystem!=="undefined"&&$dataSystem&&/^en(?:[_-]|$)/i.test($dataSystem.locale||""));
    return english&&/[A-Za-z]{2}/.test(prose)&&(/[.!?,…]/.test(prose)||/[A-Za-z]\s+[A-Za-z]/.test(prose))&&!/^[A-Z0-9_ -]+$/.test(prose)?"en":null;
}
function authoredRemember(source,text,priority){
    if(!source)return;
    authoredDisplay.set(text,source);
    addPrefetch(text,priority,source);
}
function authoredRead(plan,requestMissing){
    if(!plan)return null;
    if(typeof plan.fixed==="string")return plan.prefix+plan.fixed+plan.suffix;
    if(!authoredDisplay.has(plan.body))authoredDisplay.set(plan.body,plan.source);
    var translated=readyText(plan.source,plan.body);
    if(translated!==null&&validTranslation(plan.source,plan.body,translated,true))
        return plan.prefix+translated+plan.suffix;
    if(requestMissing)firstViewRequest(plan.source,plan.body);
    return null;
}
function scriptDialogueBody(value){
    if(typeof value!=="string"||value.length>1850)return null;
    var m=/^\s*[A-Za-z0-9!@#%<>{}^]{1,48}\.([\s\S]+)$/.exec(value);
    return m&&m[1].trim()?m[1]:null;
}
function scriptDialoguePlan(body,suffix){
    if(typeof body!=="string"||/(?:^|\s)\/[A-Za-z]/.test(body))return null;
    // This authored token is substituted with actor 1 by the verified
    // common-event dialect. Reuse the engine's protected actor escape;
    // the chosen player's name never enters OPUS or the translation key.
    var canonical=body.replace(/1Hero/g,"\\N[1]"),source=authoredSource(canonical,true);
    return source?{source:source,body:canonical,prefix:"",suffix:suffix||""}:null;
}
function scriptMessagePlan(raw){
    if(!isMZ||typeof raw!=="string"||!/^\\v\[25\](?:\\Wait\[\d+\])?$/i.test(raw)||!scriptProfileActive()||
       typeof $gameVariables==="undefined"||!$gameVariables||typeof $gameVariables.value!=="function")return null;
    var original=scriptDialogueBody($gameVariables.value(21)),current=$gameVariables.value(25);
    if(original===null||typeof current!=="string")return null;
    if(original!==current){
        if(original.indexOf("1Hero")<0||typeof $gameActors==="undefined"||!$gameActors||typeof $gameActors.actor!=="function")return null;
        var actor=$gameActors.actor(1),name=actor&&typeof actor.name==="function"?actor.name():null;
        if(typeof name!=="string"||!name||name.length>100||/[\r\n\\\x1b<>]/.test(name)||
           original.split("1Hero").join(name)!==current)return null;
    }
    return scriptDialoguePlan(original,raw.replace(/^\\v\[25\]/i,""));
}
function scriptLiteral(raw){
    if(typeof raw!=="string"||raw.length>4000)return null;
    // A single literal statement only. JSON.parse decodes the quoted
    // string; never evaluate concatenation, comments, template literals,
    // conditionals, nested commands or arbitrary JavaScript.
    var m=/^\s*\$gameVariables\.setValue\(\s*21\s*,\s*("(?:[^"\\\r\n]|\\.)*")\s*\)\s*;?\s*$/.exec(raw);
    if(!m)return null;
    try{return scriptDialogueBody(JSON.parse(m[1]));}catch(_){return null;}
}
function picturePlan(raw){
    if(typeof raw!=="string"||raw.length>1800||!raw.trim()||tsvRef(raw))return null;
    var prefix="",body=raw;
    // Only explicitly defined display variables for the verified dialect;
    // names, money, counters and generic game variables are NOT translated.
    var dynamic=/^((?:\\(?:[A-Za-z]{1,12}\[[^\]\r\n]{1,120}\]|[A-Za-z]{1,12}<[^>\r\n]{1,120}>|[{}]))*)\\v\[(\d{1,6})\]$/i.exec(raw);
    if(dynamic){
        var entry=scriptVariableEntry(Number(dynamic[2]));
        if(!entry)return null;
        entry.prefix=dynamic[1];return entry;
    }else if(/(?:\\|\x1b)[VP]\[\d+\]/i.test(raw))return null;
    // An explicit speaker label belongs to the picture, not the model.
    var speaker=/^((?:\\N\[\d+\]|[A-Z][A-Za-z0-9'’ -]{0,35}):[ \t]+)([\s\S]+)$/.exec(body);
    if(speaker){prefix+=speaker[1];body=speaker[2];}
    var source=authoredSource(body,false);
    return source?{source:source,body:body,prefix:prefix,suffix:""}:null;
}
// R13: use only documented phone presentation commands and explicit fields.
function phoneEnabled(){return pluginEnabled(/^PKD_PhoneMenu(?:_?Pro)?$/i);}
function explicitUiPlan(raw){
    if(typeof raw!=="string"||!raw.trim()||raw.length>1800||actorNames[raw]||
       actorNames[raw.trim()]||externalLocalizationReference(raw)||tsvExcluded(raw)||
       csvExecutableSyntax(raw)||/[\u0000\uFFFD]|(?:\\|\x1b)(?:js|eval|script)(?:\b|\[)|<script\b/i.test(raw)||
       /(?:^|[^\\A-Za-z])(?:[vngpi]\[[^\]]*\])/i.test(raw)||
       /^\s*(?:[$@#=]|\/\/)|\b(?:build|version)\s+\d/i.test(raw))return null;
    var prose=visibleProse(raw).trim();
    if(!prose||!/[A-Za-z\u3041-\u30fa\u3400-\u9fff]{2}/.test(prose))return null;
    var labels={"hehe":"Jeje","haha":"Jaja","messages":"Mensajes","navigate":"Navegar",
        "close":"Cerrar","confirm":"Confirmar","main menu":"Menú principal",
        "select scene":"Seleccionar escena","turn page":"Pasar página"};
    if(Object.prototype.hasOwnProperty.call(labels,prose.toLowerCase())&&prose===raw.trim())
        return {body:raw,source:"en",prefix:"",suffix:"",fixed:raw.replace(prose,labels[prose.toLowerCase()])};
    var source=authoredSource(raw,false)||displaySource(raw,"surface");
    var en=/^en(?:[_-]|$)/i.test(scriptLocale)||
        (typeof $dataSystem!=="undefined"&&$dataSystem&&/^en(?:[_-]|$)/i.test($dataSystem.locale||""));
    // Explicit English display fields can contain short noun phrases.
    // Never expand this fallback to arbitrary scripts or unrecognized names.
    if(!source&&en&&/[A-Za-z]{2}\s+[A-Za-z]{2}/.test(prose)&&
       !/[áéíóúüñ¿¡]/i.test(prose)&&!/^[A-Z0-9_ -]+$/.test(prose)&&!/[{}=<>$@]/.test(prose))
        source="en";
    return source?{source:source,body:raw,prefix:"",suffix:""}:null;
}
var phoneListMemo=typeof WeakMap==="function"?new WeakMap():null;
function phoneList(list){
    if(!phoneEnabled()||!Array.isArray(list)||list.length>30000)return false;
    if(phoneListMemo&&phoneListMemo.has(list))return phoneListMemo.get(list);
    var yes=list.some(function(c){
        return c&&c.code===355&&c.parameters&&typeof c.parameters[0]==="string"&&
            /^\s*this\.(?:phoneSetWaitFor|setAnswerForChoice|phoneSwitchToDefaultMessages|phoneSwitchBackToMessages)\s*\(/.test(c.parameters[0]);
    });
    if(phoneListMemo)phoneListMemo.set(list,yes);
    return yes;
}
function phoneAnswer(raw){
    if(typeof raw!=="string"||raw.length>4000)return null;
    var m=/^(\s*this\.setAnswerForChoice\(\s*[1-9]\d{0,2}\s*,\s*)("(?:[^"\\\r\n]|\\.)*")(\s*\)\s*;?\s*)$/.exec(raw);
    if(!m)return null;
    var value;try{value=JSON.parse(m[2]);}catch(_){return null;}
    var plan=explicitUiPlan(value);if(!plan)return null;
    return {plan:plan,head:m[1],tail:m[3]};
}
function rememberUi(plan,priority){
    if(plan&&typeof plan.fixed!=="string")authoredRemember(plan.source,plan.body,priority);
}
function readUi(plan,requestMissing){
    if(!plan)return null;
    if(typeof plan.fixed==="string")return plan.fixed;
    if(stableDisplay(plan.body,false)===plan.body)return plan.body;
    return authoredRead(plan,requestMissing);
}
function scanPhoneList(list,priority){
    if(!phoneList(list))return;
    // Collect all authored names before inventorying visible text.
    if(isMZ)list.forEach(function(c){if(c&&c.code===101&&c.parameters)protectMZName(c.parameters[4]);});
    for(var i=0;i<list.length;i++){
        var c=list[i];if(!c||!Array.isArray(c.parameters))continue;
        if(c.code===401)rememberUi(explicitUiPlan(c.parameters[0]),priority);
        else if(c.code===102&&Array.isArray(c.parameters[0]))
            c.parameters[0].forEach(function(v){rememberUi(explicitUiPlan(v),priority);});
        else if(c.code===355&&(!list[i+1]||list[i+1].code!==655)){
            var answer=phoneAnswer(c.parameters[0]);if(answer)rememberUi(answer.plan,priority);
        }
    }
}
function phoneCommandPlan(interpreter){
    var list=interpreter._list,index=interpreter._index,c=list&&list[index];
    if(!phoneList(list)||!c||!Array.isArray(c.parameters)||
       (typeof interpreter.phoneSetWaitFor!=="function"&&typeof interpreter.setAnswerForChoice!=="function"))return null;
    var entries=[];
    if(c.code===101){
        for(var at=index+1;at<list.length&&list[at]&&list[at].code===401&&at<=index+64;at++){
            var plan=list[at].parameters&&explicitUiPlan(list[at].parameters[0]);
            if(plan)entries.push({at:at,plan:plan});
        }
    }else if(c.code===102&&Array.isArray(c.parameters[0])){
        c.parameters[0].forEach(function(raw,choice){
            var plan=explicitUiPlan(raw);if(plan)entries.push({at:index,choice:choice,plan:plan});
        });
    }else if(c.code===355&&(!list[index+1]||list[index+1].code!==655)){
        var a=phoneAnswer(c.parameters[0]);if(a)entries.push({at:index,answer:a,plan:a.plan});
    }
    return entries.length?{list:list,index:index,entries:entries}:null;
}
var phoneHooked=typeof WeakSet==="function"?new WeakSet():null;
function hookPhoneExecute(proto){
    if(!proto||typeof proto.executeCommand!=="function"||
       (phoneHooked&&phoneHooked.has(proto))||proto.executeCommand._iaPhoneHook)return;
    var execute=proto.executeCommand;
    var wrapped=function(){
        var job=null;
        try{if(!inputFormActive())job=phoneCommandPlan(this);}catch(_){state.errors++;}
        if(!job){this._iaPhoneGate=null;return execute.apply(this,arguments);}
        var waiting=false,changed=false,values=job.entries.map(function(entry){
            var value=readUi(entry.plan,true);
            if(value===null){
                if(rejectedKeys.get(entry.plan.source+"\u0000"+entry.plan.body)!==Infinity)waiting=true;
            }else if(value!==entry.plan.body)changed=true;
            return value;
        });
        if(waiting){
            var now=Date.now(),g=this._iaPhoneGate,scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
            if(!g||g.list!==job.list||g.index!==job.index||g.scene!==scene)
                g=this._iaPhoneGate={list:job.list,index:job.index,scene:scene,started:now};
            if(now-g.started<(state.connected?FIRST_VIEW_LIMIT:FIRST_VIEW_OFFLINE))return false;
        }
        this._iaPhoneGate=null;
        if(!changed)return execute.apply(this,arguments);
        var projected=job.list.slice(),copies=Object.create(null);
        job.entries.forEach(function(entry,i){
            var value=values[i];if(value===null||value===entry.plan.body)return;
            var at=entry.at,c=projected[at];
            if(!copies[at]){
                var copy={};Object.keys(c).forEach(function(k){if(k!=="__proto__")copy[k]=c[k];});
                copy.parameters=c.parameters.slice();projected[at]=copy;copies[at]=true;
            }
            var params=projected[at].parameters;
            if(entry.choice!==undefined){
                if(params[0]===job.list[at].parameters[0])params[0]=params[0].slice();
                params[0][entry.choice]=value;
            }else if(entry.answer){
                params[0]=entry.answer.head+JSON.stringify(value).replace(/\u2028/g,"\\u2028").replace(/\u2029/g,"\\u2029")+entry.answer.tail;
            }else params[0]=value;
        });
        // Only transient native dispatch. No persistent source-list changes.
        this._list=projected;
        try{return execute.apply(this,arguments);}
        finally{
            if(this._list===projected)this._list=job.list;
            if(projected[job.index]&&this._params===projected[job.index].parameters)
                this._params=job.list[job.index].parameters;
        }
    };
    wrapped._iaPhoneHook=true;proto.executeCommand=wrapped;
    if(phoneHooked)phoneHooked.add(proto);
}
function hookPhoneInterpreter(){
    if(!phoneEnabled()||typeof Game_Interpreter==="undefined"||!Game_Interpreter.prototype)return;
    hookPhoneExecute(Game_Interpreter.prototype);
    var setup=Game_Interpreter.prototype.setup;
    if(typeof setup==="function")Game_Interpreter.prototype.setup=function(list){
        var out=setup.apply(this,arguments);
        if(phoneList(list)){
            try{hookPhoneExecute(Object.getPrototypeOf(this));scanPhoneList(list,true);nextPrefetch();}
            catch(_){state.errors++;}
        }
        return out;
    };
}
function phoneDrawLabel(raw){
    if(!phoneEnabled()||typeof raw!=="string"||raw.length>160||identityDrawDepth||inputFormActive())return null;
    var m=/^(.{1,100}) is typing([ .…]*)$/.exec(raw);
    if(raw!=="Messages"&&(!m||!actorNames[m[1]]))return null;
    if(!/\bPKD_PhoneMenu(?:_?Pro)?\.js(?::|\?)/i.test(String(new Error().stack||"")))return null;
    return raw==="Messages"?"Mensajes":m[1]+" está escribiendo"+m[2];
}
var statusBios=new Map(),statusTextVariables=new Map(),statusProjectionDepth=0;
var statusPendingAssignments=new Map(),statusPendingCount=0;
function statusPluginEnabled(){return isMZ&&pluginEnabled(/^StatusMenuTesting3$/);}
function statusPresentationScope(){
    if(!statusPluginEnabled()||identityDrawDepth||inputFormActive())return false;
    if(statusProjectionDepth)return true;
    var scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
    return !!(scene&&typeof Scene_Status!=="undefined"&&scene instanceof Scene_Status)||
        /\bStatusMenuTesting3\.js(?::|\?)/.test(String(new Error().stack||""));
}
function statusTag(row){
    if(!row||typeof row.note!=="string"||row.note.length>32768)return null;
    var m=/<StatusText:([ \t]*)([^<>]{1,1800})>/i.exec(row.note);
    if(!m||!m[2].trim()||/<StatusText:/i.test(row.note.slice(m.index+m[0].length)))return null;
    return {match:m,raw:m[2]};
}
function statusRemember(raw){
    if(statusBios.has(raw))return statusBios.get(raw);
    var source=authoredSource(raw,true);
    if(!source||raw.length>1800||statusBios.size>=4096)return null;
    var parts=[],at=0,m;
    // Long prose: independent complete sentences prevent truncated
    // biographies and allow exact reassembly before the author's wrapping.
    if(raw.length>240&&!/[\r\n\\<>]/.test(raw)){
        var separator=/[.!?]([ \t]+)(?=[A-Z])/g;
        while((m=separator.exec(raw))!==null){
            var end=m.index+1,segment=raw.slice(at,end);
            if(segment.length<12||/^(?:Mr|Mrs|Ms|Dr|St)\.$/.test(segment.trim()))continue;
            parts.push({text:segment,space:m[1]});at=end+m[1].length;
        }
    }
    parts.push({text:raw.slice(at),space:""});
    if(parts.length>10||parts.some(function(p){return !p.text.trim()||!hasProse(source,p.text);}))parts=[{text:raw,space:""}];
    var plan={source:source,raw:raw,parts:parts};statusBios.set(raw,plan);
    parts.forEach(function(p){authoredRemember(source,p.text,false);});
    return plan;
}
function statusBiographyReady(raw,requestMissing){
    var plan=statusBios.get(raw);if(!plan)return null;
    var out="",missing=false;
    plan.parts.forEach(function(p){
        var value=readyText(plan.source,p.text);
        if(value===null){missing=true;if(requestMissing)firstViewRequest(plan.source,p.text);}
        else out+=value+p.space;
    });
    return !missing&&validTranslation(plan.source,raw,out,true)?out:null;
}
function scanStatusActor(row){
    if(!statusPluginEnabled())return;
    var tag=statusTag(row);if(!tag)return;
    statusRemember(tag.raw);
    var id=/<StatusTextVariable:[ \t]*(\d{1,6})[ \t]*>/i.exec(row.note);
    if(id&&Number(id[1])>0&&!statusTextVariables.has(Number(id[1]))){
        var n=Number(id[1]);statusTextVariables.set(n,new Set());
        var deferred=statusPendingAssignments.get(n);
        if(deferred){
            statusPendingAssignments.delete(n);statusPendingCount-=deferred.size;
            deferred.forEach(function(v){rememberStatusVariable(n,v);});
        }
    }
}
function rememberStatusVariable(id,value){
    if(!statusTextVariables.has(id)||typeof value!=="string"||value.length>1800)return;
    var plan=statusRemember(value);
    if(plan)statusTextVariables.get(id).add(value);
}
function scanStatusAssignment(cmd){
    if(!statusPluginEnabled()||!cmd||cmd.code!==122||!Array.isArray(cmd.parameters))return;
    var a=cmd.parameters;
    if(!integer(a[0])||a[0]<=0||a[0]!==a[1]||a[2]!==0||a[3]!==4||
       typeof a[4]!=="string"||a[4].length>4096)return;
    try{
        var value=JSON.parse(a[4]);
        if(typeof value!=="string"||!value.trim()||value.length>1800)return;
        if(statusTextVariables.has(a[0]))rememberStatusVariable(a[0],value);
        else if(statusPendingCount<2048){
            // The initial map is scanned before Actors.json. Defer only
            // bounded literal assignments until an actor note proves its ID.
            // Never submit an unverified variable's content to the engine.
            var set=statusPendingAssignments.get(a[0]);
            if(!set){set=new Set();statusPendingAssignments.set(a[0],set);}
            if(!set.has(value)){set.add(value);statusPendingCount++;}
        }
    }catch(_){}
}
function statusRenderValue(raw){
    if(typeof raw!=="string")return raw;
    var m=/^(Age|Height|Bust|Waist|Hips)([ \t]*:[ \t]*(?:\d{1,4}(?:[.,]\d{1,3})?(?:[ \t]*(?:cm|kg))?|\?)?)?$/.exec(raw);
    if(m){
        var labels={Age:"Edad",Height:"Altura",Bust:"Busto",Waist:"Cintura",Hips:"Caderas"};
        return labels[m[1]]+(m[2]||"");
    }
    var value=statusBiographyReady(raw,true);return value===null?raw:value;
}
function statusActorProjection(row){
    var tag=statusTag(row);if(!tag)return row;
    var shown=statusBiographyReady(tag.raw,true);
    if(shown===null||shown===tag.raw||/[<>\\\r\n\u0000]/.test(shown))return row;
    var clone=Object.assign({},row),m=tag.match;
    clone.note=row.note.slice(0,m.index)+"<StatusText:"+m[1]+shown+">"+row.note.slice(m.index+m[0].length);
    if(row.meta&&typeof row.meta==="object"){
        clone.meta=Object.assign({},row.meta);
        if(typeof row.meta.StatusText==="string"&&row.meta.StatusText.trim()===tag.raw.trim()){
            var lead=(row.meta.StatusText.match(/^[ \t]*/)||[""])[0];
            clone.meta.StatusText=lead+shown;
        }
    }
    return clone;
}
function statusRows(){
    return typeof $dataActors!=="undefined"&&Array.isArray($dataActors)?$dataActors:null;
}
function prepareStatusScene(){
    var rows=statusRows();if(!rows)return true;
    var id=null;
    try{var actor=typeof $gameParty!=="undefined"&&$gameParty&&typeof $gameParty.menuActor==="function"?$gameParty.menuActor():null;
        if(actor&&typeof actor.actorId==="function")id=actor.actorId();}catch(_){}
    var ready=true;
    rows.forEach(function(row){
        if(!row)return;
        scanStatusActor(row);
        var tag=statusTag(row);
        if(tag&&(id===null||row.id===id)&&statusBiographyReady(tag.raw,true)===null)ready=false;
    });
    return ready;
}
function hookStatusPresentation(){
    if(!statusPluginEnabled())return;
    if(typeof Scene_Status!=="undefined"&&Scene_Status.prototype){
        var p=Scene_Status.prototype;
        ["create","start","refresh","refreshActor","onActorChange"].forEach(function(method){
            var native=p[method];if(typeof native!=="function")return;
            p[method]=function(){
                if(statusProjectionDepth||inputFormActive())return native.apply(this,arguments);
                var rows=statusRows(),shadow=rows;
                if(rows){
                    rows.forEach(scanStatusActor);
                    shadow=rows.map(function(row){return row?statusActorProjection(row):row;});
                }
                statusProjectionDepth++;
                if(rows)$dataActors=shadow;
                try{return native.apply(this,arguments);}
                finally{if(rows&&$dataActors===shadow)$dataActors=rows;statusProjectionDepth--;}
            };
        });
        if(typeof SceneManager!=="undefined"&&typeof SceneManager.changeScene==="function"){
            var change=SceneManager.changeScene;
            SceneManager.changeScene=function(){
                var next=this._nextScene;
                if(next instanceof Scene_Status&&!inputFormActive()){
                    var ready=prepareStatusScene(),now=Date.now(),gate=this._iaStatusFirstView;
                    if(!gate||gate.scene!==next)gate=this._iaStatusFirstView={scene:next,started:now};
                    if(!ready&&now-gate.started<(state.connected?FIRST_VIEW_LIMIT:FIRST_VIEW_OFFLINE))return;
                }
                this._iaStatusFirstView=null;
                return change.apply(this,arguments);
            };
        }
    }
    // Late callbacks may use the actor accessor outside scene creation.
    // Only the identified author presentation stack can see a shadow.
    if(typeof Game_Actor!=="undefined"&&Game_Actor.prototype&&typeof Game_Actor.prototype.actor==="function"){
        var readActor=Game_Actor.prototype.actor;
        Game_Actor.prototype.actor=function(){
            var row=readActor.apply(this,arguments);
            if(statusProjectionDepth||!statusPluginEnabled()||inputFormActive()||
               !/\bStatusMenuTesting3\.js(?::|\?)/.test(String(new Error().stack||"")))return row;
            scanStatusActor(row);return statusActorProjection(row);
        };
    }
    if(typeof Game_Variables!=="undefined"&&Game_Variables.prototype&&typeof Game_Variables.prototype.value==="function"){
        var value=Game_Variables.prototype.value;
        Game_Variables.prototype.value=function(id){
            var raw=value.apply(this,arguments);
            if(!statusPluginEnabled()||typeof raw!=="string"||!statusTextVariables.has(id)||
               !statusTextVariables.get(id).has(raw)||inputFormActive()||
               (!statusProjectionDepth&&!/\bStatusMenuTesting3\.js(?::|\?)/.test(String(new Error().stack||""))))return raw;
            return statusRenderValue(raw);
        };
    }
}
/* HUD Maker: only explicit static TextData.Text.Text, Type 0.
   Do not inspect evaluated HUD functions or variable fields. */
var ultraHudTexts=new Map();
function ultraHudEnabled(){return isMZ&&pluginEnabled(/^SRD_HUDMakerUltra(?:Pro)?$/);}
function ultraHudScope(){
    return ultraHudEnabled()&&!identityDrawDepth&&!inputFormActive()&&
        /\bSRD_(?:HUDMakerUltra(?:Pro)?|UltraBase)\.js(?::|\?)/.test(String(new Error().stack||""));
}
function ultraHudFixed(raw){
    if(typeof raw!=="string")return null;
    var m=/^Day ([0-9]{1,4})$/.exec(raw);if(m)return "Día "+m[1];
    var labels={Weekend:"Fin de semana",Noon:"Mediodía",Afternoon:"Tarde",Evening:"Atardecer",Night:"Noche",Morning:"Mañana"};
    return Object.prototype.hasOwnProperty.call(labels,raw)?labels[raw]:null;
}
function ultraHudRender(raw){
    var label=ultraHudFixed(raw);if(label!==null)return label;
    var source=ultraHudTexts.get(raw);if(!source)return raw;
    var shown=readyText(source,raw);
    if(shown===null){firstViewRequest(source,raw);return raw;}
    return shown;
}
function scanUltraHud(data){
    if(!ultraHudEnabled()||!data||!Array.isArray(data.Data))return;
    var count=0;
    function node(n,depth){
        if(!n||typeof n!=="object"||depth>24||++count>20000)return;
        var field=n.TextData&&n.TextData.Text;
        if(field&&field.Type===0&&typeof field.Text==="string"&&ultraHudFixed(field.Text)===null){
            var raw=field.Text,source=authoredSource(raw,true);
            if(source){ultraHudTexts.set(raw,source);authoredRemember(source,raw,false);}
        }
        if(Array.isArray(n.Children))n.Children.forEach(function(child){node(child,depth+1);});
    }
    data.Data.forEach(function(group){if(group&&Array.isArray(group.HUD))group.HUD.forEach(function(n){node(n,0);});});
}
function notificationPlan(params){
    if(!isMZ||!Array.isArray(params)||!params[3]||typeof params[3]!=="object"||Array.isArray(params[3]))return null;
    if(params[0]==="Hendrix_Pictures_UI_Creator"&&params[1]==="ShowText"&&pluginEnabled(/^Hendrix_Pictures_UI_Creator$/)){
        if(params[3].textVocabulary)return null;
        var picture=explicitUiPlan(params[3].text);
        if(picture)picture.field="text";
        return picture;
    }
    if(params[0]==="VisuMZ_4_GabWindow"&&params[1]==="GabTextOnly"&&pluginEnabled(/^VisuMZ_4_GabWindow$/)){
        var rawGab=boundedQuestJson(params[3]["Text:json"],16384);
        var gab=explicitUiPlan(rawGab);
        if(gab){gab.field="Text:json";gab.json=true;}
        return gab;
    }
    if(params[0]!=="LL_InfoPopupWIndow"||params[1]!=="showMessage"||!pluginEnabled(/^LL_InfoPopupWIndow$/))return null;
    var raw=params[3].messageText;
    if(typeof raw!=="string"||!raw.trim()||raw.length>1800||
       /(?:\\|\x1b)(?:js|eval|script)(?:\b|\[)|<script\b/i.test(raw))return null;
    var source=authoredSource(raw,false)||displaySource(raw,"surface");
    return source?{source:source,body:raw,prefix:"",suffix:"",field:"messageText"}:null;
}
var notificationDispatchDepth=0;
function hookNotificationMZ(){
    if(!isMZ||!pluginEnabled(/^(?:LL_InfoPopupWIndow|Hendrix_Pictures_UI_Creator|VisuMZ_4_GabWindow)$/))return;
    if(typeof Game_Interpreter!=="undefined"&&Game_Interpreter.prototype&&
       typeof Game_Interpreter.prototype.command357==="function"){
        var p=Game_Interpreter.prototype,native357=p.command357;
        p.command357=function(params){
            var plan=notificationPlan(params);
            if(!plan||inputFormActive()){
                this._iaNoticeGate=null;
                return native357.apply(this,arguments);
            }
            var shown=readUi(plan,true),raw=plan.body;
            if(shown===null){
                var now=Date.now(),g=this._iaNoticeGate,
                    scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
                if(!g||g.list!==this._list||g.index!==this._index||g.scene!==scene||g.params!==params||g.raw!==raw)
                    g=this._iaNoticeGate={list:this._list,index:this._index,scene:scene,params:params,raw:raw,started:now};
                var permanentlyRejected=rejectedKeys.get(plan.source+"\u0000"+raw)===Infinity;
                if(!permanentlyRejected&&now-g.started<(state.connected?FIRST_VIEW_LIMIT:FIRST_VIEW_OFFLINE))return false;
            }
            this._iaNoticeGate=null;
            if(shown===null)return native357.apply(this,arguments);
            var copy=params.slice(),fields={};
            Object.keys(params[3]).forEach(function(k){if(k!=="__proto__")fields[k]=params[3][k];});
            fields[plan.field]=plan.json?JSON.stringify(shown):shown;copy[3]=fields;
            var args=Array.prototype.slice.call(arguments);args[0]=copy;
            notificationDispatchDepth++;
            try{return native357.apply(this,args);}finally{notificationDispatchDepth--;}
        };
    }
    // Support script-originated plugin calls when their translations are
    // already available. Never replay a command to refresh an expired toast.
    if(typeof PluginManager!=="undefined"&&typeof PluginManager.callCommand==="function"){
        var call=PluginManager.callCommand;
        PluginManager.callCommand=function(self,name,command,fields){
            if(notificationDispatchDepth||inputFormActive())return call.apply(this,arguments);
            var plan=notificationPlan([name,command,"",fields]),shown=plan?readUi(plan,true):null;
            if(shown===null)return call.apply(this,arguments);
            var args=Array.prototype.slice.call(arguments),copy={};
            Object.keys(fields).forEach(function(k){if(k!=="__proto__")copy[k]=fields[k];});
            copy[plan.field]=plan.json?JSON.stringify(shown):shown;args[3]=copy;return call.apply(this,args);
        };
    }
}
function scriptScanCommand(cmd,next,priority){
    if(!isMZ||!cmd||!Array.isArray(cmd.parameters))return;
    var a=cmd.parameters,plan=null;
    if(cmd.code===357){
        var notice=notificationPlan(a);
        if(notice){rememberUi(notice,priority);return;}
    }
    if(cmd.code===122){scanStatusAssignment(cmd);rememberDisplayLiteral(cmd,priority);return;}
    if(cmd.code===357&&enabledTextPicture()&&a[0]==="TextPicture"&&a[1]==="set"&&a[3]&&typeof a[3].text==="string"){
        // Dynamic pictures are handled at presentation, not against
        // arbitrary variable values during the static inventory.
        if(!/(?:\\|\x1b)[VP]\[\d+\]/i.test(a[3].text))plan=picturePlan(a[3].text);
        if(plan)scriptStats.pictures++;
    }else if(cmd.code===355&&scriptProfileActive()&&(!next||next.code!==655)){
        var body=scriptLiteral(a[0]);if(body!==null)plan=scriptDialoguePlan(body,"");
        if(plan)scriptStats.dialogues++;
    }
    if(plan)authoredRemember(plan.source,plan.body,priority);
}
function hookAuthoredMZ(){
    hookPhoneInterpreter();
    if(!isMZ)return;
    hookNotificationMZ();hookStatusPresentation();
    if(typeof Game_Interpreter!=="undefined"&&Game_Interpreter.prototype&&typeof Game_Interpreter.prototype.setup==="function"){
        var setup=Game_Interpreter.prototype.setup;
        Game_Interpreter.prototype.setup=function(list){
            var out=setup.apply(this,arguments);
            if(Array.isArray(list))try{
                for(var i=0;i<Math.min(list.length,256);i++)scriptScanCommand(list[i],list[i+1],true);
                nextPrefetch();
            }catch(_){state.errors++;}
            return out;
        };
    }
    if(!enabledTextPicture()||typeof Sprite_Picture==="undefined"||!Sprite_Picture.prototype||
       typeof Sprite_Picture.prototype.updateBitmap!=="function"||typeof Sprite_Picture.prototype.picture!=="function")return;
    var update=Sprite_Picture.prototype.updateBitmap;
    Sprite_Picture.prototype.updateBitmap=function(){
        var pic=null,raw=null,projected=null;
        try{
            pic=this.picture();
            if(!inputFormActive()&&pic&&pic._name===""&&typeof pic.mzkp_text==="string"&&pic.mzkp_text){
                raw=pic.mzkp_text;
                var plan=picturePlan(raw);
                if(plan){
                    var key=JSON.stringify([raw,plan.prefix,plan.body,plan.fixed||""]),ticket=this._iaPictureProjection,now=Date.now();
                    if(!ticket||ticket.pic!==pic||ticket.key!==key)
                        ticket=this._iaPictureProjection={pic:pic,key:key,checked:0,out:null};
                    if(!ticket.checked||now-ticket.checked>=100){
                        ticket.checked=now;ticket.out=authoredRead(plan,true);
                    }
                    projected=ticket.out;
                    if(typeof projected!=="string"||projected===raw)projected=null;
                }else this._iaPictureProjection=null;
            }else this._iaPictureProjection=null;
        }catch(_){state.errors++;projected=null;}
        if(projected===null)return update.apply(this,arguments);
        // The existing TextPicture sprite recomputes dimensions and
        // replaces its own bitmap when its display string changes. The
        // saved Game_Picture retains the original text, all timing, IDs
        // and animation state. No callbacks repaint expired pictures.
        var before=this.mzkp_text;pic.mzkp_text=projected;identityDrawDepth++;
        try{
            var result=update.apply(this,arguments);
            if(this.mzkp_text===projected&&before!==projected){scriptStats.shown++;state.shown++;}
            return result;
        }finally{
            identityDrawDepth--;
            if(pic.mzkp_text===projected)pic.mzkp_text=raw;
        }
    };
}

function bindNativeMessageBitmap(win){
    try{if(win&&win.contents&&typeof win.contents==="object")win.contents._iaOwnerWindow=win;}catch(_){}
}
function hookMessages(){
    if(typeof Window_Message==="undefined"||!Window_Message.prototype)return;
    var proto=Window_Message.prototype,original=proto.startMessage;
    if(typeof original!=="function")return;
    hookFirstView(proto);
    // Scope the projection to the one native startMessage invocation.
    // A game may bypass our draw/convert hooks and call allText directly.
    if(typeof Game_Message!=="undefined"&&Game_Message.prototype&&typeof Game_Message.prototype.allText==="function"){
        var nativeAllText=Game_Message.prototype.allText;
        Game_Message.prototype.allText=function(){
            var raw=nativeAllText.apply(this,arguments),scope=tsvProjection;
            if(scope&&scope.message===this&&raw===scope.raw){scope.used=true;return scope.text;}
            return raw;
        };
    }
    proto.startMessage=function(){
        hideLate(this);this._iaSourceMessage=null;
        if(inputFormActive()){identityDrawDepth++;try{return original.apply(this,arguments);}finally{identityDrawDepth--;bindNativeMessageBitmap(this);}}
        var projection=null;
        try{
            if(typeof $gameMessage!=="undefined"&&$gameMessage&&$gameMessage.hasText&&$gameMessage.hasText()){
                var rawText=$gameMessage.allText(),externalEntry=iavraResolveText(rawText);
                var text=externalEntry?externalEntry.text:rawText;
                var source=externalEntry?externalEntry.source:languageFor(text),keys=tsvRawMessage();
                this._iaSourceMessage=text;
                var scripted=scriptMessagePlan(keys);
                if(scripted){
                    var projected=authoredRead(scripted,true);
                    if(projected!==null)projection={message:$gameMessage,raw:rawText,text:projected,used:false,scripted:true};
                    source=null;
                }
                var entries=!scripted?scriptVariableEntries(keys):[];
                if(entries.length){
                    var fieldText=scriptVariableRender(keys,entries,true);
                    if(fieldText!==null)projection={message:$gameMessage,raw:rawText,text:fieldText,used:false,scripted:true};
                    source=null;
                }
                if(!scripted&&!entries.length&&tsv.detected&&tsvRef(keys)){
                    var resolved=tsvMessageEntry(keys,text);
                    var locale=resolved?resolved.source:tsvProbeLocale(this);
                    if(locale)tsv.language=locale;
                    tsvPrioritize(keys,true);
                    var localized=locale?tsvTranslatedKeys(keys,locale,true):null;
                    if(localized!==null)projection={message:$gameMessage,raw:rawText,text:localized,used:false};
                    // Never replace the game's reference array.
                    source=null;
                }
                if(externalEntry&&!scripted&&!entries.length&&source){
                    var externalCached=readyText(source,text);
                    projection={message:$gameMessage,raw:rawText,text:externalCached!==null?externalCached:text,
                        used:false,iavra:true,translated:externalCached!==null&&externalCached!==text};
                    if(externalCached===null){
                        if(state.connected)requestVisible(source,text).then(function(){},function(){state.errors++;});
                        else addPrefetch(text,true,source);
                    }
                    source=null;
                }
                if(source){
                    var old=readyText(source,text);
                    if(old===null&&tableStats.root)old=csvKnownReady(text);
                    if(typeof old==="string"&&old!==text){
                        $gameMessage._texts=old.split("\n");state.shown++;
                    }else{
                        var partial=readyIndependentLines(source,text);
                        if(partial!==null)$gameMessage._texts=partial.split("\n");
                        var win=this,ticket=null;
                        if((source==="en"||tableStats.root||isMZ)&&nativeRenderParts(text)){
                            ticket={message:$gameMessage,displayed:$gameMessage.allText(),original:text,source:source,
                                scene:typeof SceneManager!=="undefined"?SceneManager._scene:null,
                                result:null,drawn:false,pages:0,geometry:null};
                            win._iaLateTicket=ticket;lateStats.requested++;
                        }
                        if(tableStats.root||isMZ){addPrefetch(text,true,source);nextPrefetch();}
                        if(state.connected&&(!tableStats.root||cacheReadDone))requestVisible(source,text).then(function(result){
                            if(ticket&&win._iaLateTicket===ticket&&typeof result==="string"&&result!==text&&
                               validTranslation(source,text,result,true))ticket.result=result;
                        },function(){state.errors++;});
                        else addPrefetch(text,true);
                    }
                }
            }
        }catch(_){state.errors++;}
        var out,previousProjection=tsvProjection;
        tsvProjection=projection;
        try{out=original.apply(this,arguments);}
        finally{tsvProjection=previousProjection;bindNativeMessageBitmap(this);}
        if(projection&&projection.used){
            if(projection.iavra){if(projection.translated){state.shown++;iavra.shown++;}}
            else{state.shown++;if(projection.scripted)scriptStats.shown++;else tsv.shown++;}
        }
        if(tsv.detected)try{tsvLateTicket(this);}catch(_){state.errors++;}
        if(this._iaLateTicket)try{snapshotMessage(this,this._iaLateTicket);}catch(_){hideLate(this);}
        return out;
    };
    var newPage=proto.newPage;
    if(typeof newPage==="function")proto.newPage=function(){
        var t=this._iaLateTicket;if(t)t.pages++;
        bindNativeMessageBitmap(this);
        try{return newPage.apply(this,arguments);}finally{bindNativeMessageBitmap(this);}
    };
    var update=proto.update;
    if(typeof update==="function")proto.update=function(){
        // Apply before native input consumes a final pause. No new window.
        bindNativeMessageBitmap(this);
        var ticket=this._iaLateTicket;
        if(ticket&&ticket.tsv&&!ticket.drawn){
            try{tsvRefreshTicket(this,ticket);}catch(_){state.errors++;}
            ticket=this._iaLateTicket;
        }
        if(ticket&&!ticket.tsv&&!ticket.result&&ticket.scene&&
           typeof SceneManager!=="undefined"&&SceneManager._scene===ticket.scene&&
           this.pause&&!this._textState){
            try{
                var source=ticket.source||"en",original=ticket.original||ticket.displayed;
                var candidate=readyText(source,original);
                if(candidate===null&&tableStats.root)candidate=csvKnownReady(original);
                if(typeof candidate==="string"&&candidate!==ticket.displayed&&validTranslation(source,original,candidate,true))ticket.result=candidate;
            }catch(_){}
        }
        try{displayLate(this);}catch(_){hideLate(this);state.errors++;}
        return update.apply(this,arguments);
    };
    var terminate=proto.terminateMessage;
    if(typeof terminate==="function")proto.terminateMessage=function(){hideLate(this);this._iaFirstGate=null;this._iaSourceMessage=null;return terminate.apply(this,arguments);};
    if(typeof Game_Message!=="undefined"&&Game_Message.prototype&&typeof Game_Message.prototype.add==="function"){
        var add=Game_Message.prototype.add;
        Game_Message.prototype.add=function(text){
            var out=add.apply(this,arguments);
            try{
                if(tsvRef(text))tsvPrioritize(text,true);
                var env=captionEnvelope(text);
                if(env)addPrefetch(env.body,true,captionSource(env.body));
                var source=typeof text==="string"?languageFor(text):null;
                if(source){
                    addPrefetch(text,true);
                    if(state.connected&&(!tableStats.root||cacheReadDone)&&pending.size<90)requestVisible(source,text).catch(function(){state.errors++;});
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
        if(inputFormActive()||!Array.isArray(choices)||!choices.length||choices.length>24)
            return original.apply(this,arguments);
        var translated=choices.slice(),changed=false;
        try{
            for(var i=0;i<choices.length;i++){
                if(tsvRef(choices[i])){tsvPrioritize(choices[i],true);continue;}
                var source=displaySource(choices[i],"choice");
                if(!source)continue;
                addPrefetch(choices[i],true,source);
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
        if(changed&&!isMZ&&!tsv.detected){args[0]=translated;state.shown++;}
        return original.apply(this,args);
    };
}
// Read-only full MV inventory. Never parse plugin source, save files, script
// commands, variable values, filenames, or event conditions as dialogue.
var prefetchedMap=null,discovered=new Map(),priorityQueue=[],prefetchQueue=[],priorityQueueAt=0,prefetchQueueAt=0;
var initialMapFile="",initialMapScanned=false,initialKeys=new Map(),collectInitial=false;
var scanStats={files:0,totalFiles:0,ready:0,rejected:0,skipped:0,done:false,limited:false};
var scanStarted=false,prefetchBusy=false;
var inkStats={detected:false,files:0,candidates:0,excluded:0};
var tableStats={files:0,candidates:0,root:false,rootDone:false,rootFiles:0,rootTotal:0,rootSkipped:0,authored:0};

// Explicit localization dialect: data/Languages.tsv with a Key and four
// named language columns. The game's identifiers are never neural input.
var tsv={detected:false,valid:false,done:false,loading:false,rows:0,conflicts:0,shown:0,
    keys:new Map(),display:new Map(),chinese:new Map(),visual:new Map(),priority:new Map(),language:"en",skippedRows:0,late:0,visu:false,probe:null,loose:new Map(),repairs:0};
// Explicit, read-only adapter for Iavra Localization Core. It follows the
// game's own File Path/Languages settings; it never crawls arbitrary folders,
// rewrites a catalog, changes the active language, or translates identity keys.
var iavra={
    detected:false,done:true,loading:false,template:"",languages:[],defaultLanguage:"en",
    prefix:"#{",suffix:"}",catalogs:{en:new Map(),ja:new Map()},textSources:new Map(),
    files:0,strings:0,skipped:0,shown:0
};
function iavraSourceForCode(value){
    var code=String(value||"").trim().toLowerCase().replace(/_/g,"-");
    if(/^(?:en|eng|english)(?:-[a-z0-9]+)?$/.test(code))return "en";
    if(/^(?:ja|jp|jpn|japanese)(?:-[a-z0-9]+)?$/.test(code))return "ja";
    return null;
}
function iavraEscapeRegex(value){
    var out="",special=".+*?^$()[]{}|\\";
    value=String(value);
    for(var i=0;i<value.length;i++){
        var ch=value.charAt(i);
        if(special.indexOf(ch)>=0)out+="\\";
        out+=ch;
    }
    return out;
}
function detectIavraLocalization(){
    iavra.done=true;
    if(typeof $plugins==="undefined"||!Array.isArray($plugins))return false;
    var plugin=null;
    for(var i=0;i<$plugins.length;i++){
        var p=$plugins[i];
        if(!p||!p.status)continue;
        if(/<Iavra Localization Core>/i.test(String(p.description||""))||
           /Iavra.*Localization.*Core/i.test(String(p.name||""))){plugin=p;break;}
    }
    if(!plugin)return false;
    var params=plugin.parameters||{},template=String(params["File Path"]||"").trim();
    var folder=String(params["Localization Folder"]||"").trim();
    if(folder)template=folder.replace(/\\/g,"/").replace(/\/+$/,"")+"/"+template.replace(/^[/\\]+/,"");
    template=template.replace(/\\/g,"/");
    if(template.split("{lang}").length!==2)return false;
    var rawLanguages=String(params["Languages"]||"en").trim(),languages=[];
    if(rawLanguages.charAt(0)==="["){
        try{var parsed=JSON.parse(rawLanguages);if(Array.isArray(parsed))languages=parsed.map(String);}catch(_){}
    }
    if(!languages.length)languages=rawLanguages.split(/[,;\s]+/);
    var entries=[],seen={};
    languages.forEach(function(code){
        code=String(code||"").trim();
        var source=iavraSourceForCode(code);
        if(!source||seen[source]||!/^[A-Za-z]{2,12}(?:[-_][A-Za-z0-9]{2,12})?$/.test(code))return;
        seen[source]=true;entries.push({code:code,source:source});
    });
    if(!entries.length)return false;
    var escape=String(params["Escape Code"]||"#{{key}}"),at=escape.indexOf("{key}");
    if(at<0||escape.indexOf("{key}",at+5)>=0)return false;
    var prefix=escape.slice(0,at),suffix=escape.slice(at+5);
    if(!prefix||!suffix||prefix.length>30||suffix.length>30||/[\r\n]/.test(prefix+suffix))return false;
    iavra.detected=true;iavra.done=false;iavra.template=template;iavra.languages=entries;
    iavra.defaultLanguage=iavraSourceForCode(languages[0])||entries[0].source;
    iavra.prefix=prefix;iavra.suffix=suffix;
    return true;
}
function iavraFile(code){
    if(!content||!iavra.template)return null;
    var relative=iavra.template.replace("{lang}",String(code)).replace(/\\/g,"/");
    if(!relative||relative.charAt(0)==="/"||/^[A-Za-z]:/.test(relative)||relative.indexOf("\u0000")>=0)return null;
    var parts=relative.split("/");
    if(parts.length<1||parts.length>12||parts.some(function(s){
        return !s||s==="."||s===".."||!/^[A-Za-z0-9_.-]{1,100}$/.test(s);
    }))return null;
    var current=content;
    try{
        for(var i=0;i<parts.length-1;i++){
            current=path.join(current,parts[i]);
            if(!directoryUnder(content,current))return null;
        }
        var file=path.join.apply(path,[content].concat(parts));
        if(!regularUnder(content,file,16*1024*1024))return null;
        return file;
    }catch(_){return null;}
}
function iavraSkipSegment(segment){
    return /^(?:names?|speakers?|actors?|characters?|npcs?|ids?|keys?|paths?|files?|filenames?|assets?|images?|audio|fonts?|icons?|codes?|scripts?|plugins?|switches?|variables?)$/i.test(segment);
}
function iavraCatalogText(source,text){
    if(typeof text!=="string"||!text.trim()||text.length>1800||actorNames[text]||
       externalLocalizationReference(text)||/[\u0000\uFFFD]/.test(text)||csvExecutableSyntax(text)||
       /(?:\\|\x1b)(?:js|eval|script)(?:\b|\[)|<script\b/i.test(text))return false;
    var prose=visibleProse(text).trim();
    if(!prose||prose.length>1600||/^[A-Z][0-9]{3,}$/i.test(prose)||
       /^[A-Za-z0-9_.-]+\.(?:png|ogg|js|json|csv|tsv|woff2?|ttf)$/i.test(prose))return false;
    if(source==="ja")return isJapanese(prose);
    return source==="en"&&/[A-Za-z]{2}/.test(prose)&&!isJapanese(prose);
}
function iavraRememberText(text,source){
    if(!iavra.textSources.has(text))iavra.textSources.set(text,source);
    else if(iavra.textSources.get(text)!==source)iavra.textSources.set(text,null);
}
function iavraIndexCatalog(data,source){
    var count=0,nodes=0,map=iavra.catalogs[source];
    function walk(value,prefix,depth){
        if(++nodes>50000||depth>12)return;
        if(typeof value==="string"){
            if(prefix&&prefix.length<=300&&iavraCatalogText(source,value)){
                map.set(prefix,value);iavraRememberText(value,source);iavra.strings++;count++;
                addPrefetch(value,false,source);
            }
            return;
        }
        if(Array.isArray(value)){
            for(var i=0;i<value.length&&i<10000;i++)walk(value[i],prefix?prefix+"."+i:String(i),depth+1);
            return;
        }
        if(value&&typeof value==="object"){
            Object.keys(value).forEach(function(key){
                if(!/^[A-Za-z0-9_-]{1,100}$/.test(key)||iavraSkipSegment(key))return;
                walk(value[key],prefix?prefix+"."+key:key,depth+1);
            });
        }
    }
    walk(data,"",0);
    return count;
}
function loadIavraCatalogs(done){
    if(!iavra.detected){iavra.done=true;if(typeof done==="function")done();return;}
    if(iavra.done){if(typeof done==="function")done();return;}
    if(iavra.loading)return;
    iavra.loading=true;
    var at=0;
    function finish(){
        iavra.loading=false;iavra.done=true;
        if(typeof done==="function")done();
    }
    function next(){
        if(at>=iavra.languages.length){finish();return;}
        var entry=iavra.languages[at++],file=iavraFile(entry.code);
        if(!file){iavra.skipped++;setTimeout(next,0);return;}
        fs.readFile(file,"utf8",function(err,raw){
            if(err||typeof raw!=="string"||raw.length>16*1024*1024){
                iavra.skipped++;setTimeout(next,0);return;
            }
            try{
                var data=JSON.parse(raw.replace(/^\uFEFF/,""));
                if(!data||typeof data!=="object"||Array.isArray(data))throw Error("invalid localization catalog");
                if(!iavraIndexCatalog(data,entry.source))iavra.skipped++;
                iavra.files++;
            }catch(_){iavra.skipped++;}
            setTimeout(next,0);
        });
    }
    next();
}
function iavraActiveSource(){
    var code="";
    try{
        if(typeof IAVRA!=="undefined"&&IAVRA){
            var api=IAVRA.I18N||(IAVRA.MasterLocalization&&IAVRA.MasterLocalization.I18N);
            if(api){
                code=typeof api.language==="function"?api.language():api.language||api.currentLanguage||"";
                if(!code&&typeof api.getLanguage==="function")code=api.getLanguage();
            }
        }
    }catch(_){}
    return iavraSourceForCode(code)||iavra.defaultLanguage||"en";
}
function iavraReferencePattern(){
    return new RegExp(iavraEscapeRegex(iavra.prefix)+"([A-Za-z0-9_.-]{1,300})"+
        iavraEscapeRegex(iavra.suffix)+"|«([A-Za-z0-9_-]+(?:\\.[A-Za-z0-9_-]+)+)»","g");
}
function iavraKeyValid(key){
    return typeof key==="string"&&key.length<=300&&
        /^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$/.test(key)&&
        !/(?:^|\.)(?:__proto__|prototype|constructor)(?:\.|$)/i.test(key);
}
function iavraHasReference(text){
    if(typeof text!=="string"||!iavra.detected)return false;
    var pattern=iavraReferencePattern();return pattern.test(text);
}
function iavraResolveText(text){
    if(typeof text!=="string"||!iavra.detected||!iavra.done||!iavraHasReference(text))return null;
    var preferred=iavraActiveSource(),order=preferred==="ja"?["ja","en"]:["en","ja"];
    for(var n=0;n<order.length;n++){
        var source=order[n],map=iavra.catalogs[source],complete=true,found=false;
        if(!map)continue;
        var pattern=iavraReferencePattern();
        var value=text.replace(pattern,function(token,a,b){
            var key=a||b;
            if(!iavraKeyValid(key)||!map.has(key)){complete=false;return token;}
            found=true;return map.get(key);
        });
        if(complete&&found&&value!==text)return {source:source,text:value};
    }
    return null;
}
function iavraReadyValue(text,requestMissing){
    var entry=iavraResolveText(text);if(!entry)return null;
    var ready=readyText(entry.source,entry.text);
    if(ready!==null)return ready;
    if(requestMissing)firstViewRequest(entry.source,entry.text);
    return null;
}
function iavraDisplayValue(text,requestMissing){
    var entry=iavraResolveText(text);if(!entry)return null;
    var ready=readyText(entry.source,entry.text);
    if(ready!==null)return ready;
    if(requestMissing)firstViewRequest(entry.source,entry.text);
    return entry.text;
}

function externalTables(){return tableStats.root||tsv.detected||iavra.detected;}
function tsvRef(text){return typeof text==="string"&&/(?:\\|\x1b)tl\{[^{}\r\n]{1,300}\}/i.test(text);}
function tsvNormal(text){
    return text.replace(/\r\n/g,"\n").replace(/\x1b(?=[A-Za-z{}!.,|^<>$])/g,"\\");
}
function tsvEntry(text){
    if(!tsv.detected||typeof text!=="string")return null;
    return tsv.display.get(tsvNormal(text))||null;
}
function tsvExcluded(text){
    if(tsvRef(text))return true;
    if(!tsv.valid||tsvEntry(text))return false;
    // This table explicitly declares Chinese separately. Never infer
    // Japanese from bare Han characters or from a localization key.
    return tsv.keys.has(text)||tsv.chinese.has(text)||
        (/[\u3400-\u9fff]/.test(text)&&!/[\u3041-\u3096\u30a1-\u30fa\uff66-\uff9d]/.test(text))||
        /^[A-Z][0-9]{3,}$/i.test(text);
}
function detectTsv(){
    if(!content)return;
    var dir=path.join(content,"data"),file=path.join(dir,"Languages.tsv");
    if(!directoryUnder(content,dir)||!regularUnder(dir,file,4*1024*1024))return;
    tsv.detected=true;tsv.visu=tsvVisuEnabled();
    MAX_CACHE_ENTRIES=Math.max(MAX_CACHE_ENTRIES,150000);
    CACHE_LIMIT=Math.max(CACHE_LIMIT,128*1024*1024);
}
function tsvCandidate(source,text){
    if(typeof text!=="string"||!text.trim()||text.length>1800||actorNames[text]||
       tsvRef(text)||csvExecutableSyntax(text)||/[\u0000\uFFFD]/.test(text)||
       /^\s*(?:\/\/|[#=$@+])/i.test(text)||
       /(?:\\|\x1b)(?:js|eval|script)(?:\b|\[)|<script\b/i.test(text))return false;
    var prose=visibleProse(text).trim();
    if(!prose||/^[A-Za-z0-9_]+\.(?:png|ogg|js|json|csv|tsv)$/i.test(prose)||
       /^[A-Z][0-9]{3,}$/i.test(prose))return false;
    return source==="en"?/[A-Za-z]{2}/.test(prose)&&!isJapanese(prose):isJapanese(prose);
}
// A loader can wrap a sentence before handing it to the message window.
 // Normalize ONLY whitespace outside native escape codes, never spelling,
 // punctuation, variables, or controls. Conflicting aliases stay unusable.
function tsvVisualKey(text){
    return protectedParts(tsvNormal(text)).map(function(p){
        return p.locked&&!/^\r?\n$/.test(p.value)?p.value:p.value.replace(/\s+/g," ");
    }).join("").replace(/ +/g," ").trim();
}
// Select the actual language of the native localization system. Do not
// compare unrelated language columns' pause counts. Only probe a plain,
// unique, side-effect-free cell in the confirmed Message Core dialect.
var tsvProjection=null;
function tsvVisuEnabled(){
    if(typeof $plugins==="undefined"||!Array.isArray($plugins))return false;
    return $plugins.some(function(p){
        if(!p||!p.status||p.name!=="VisuMZ_1_MessageCore")return false;
        try{
            var o=JSON.parse((p.parameters||{})["Localization:struct"]||"{}");
            return o["Enable:eval"]==="true"&&o["LangFiletype:str"]==="tsv"&&o["TsvFilename:str"]==="Languages.tsv";
        }catch(_){return false;}
    });
}
function tsvSurfaceKey(text){
    return tsvVisualKey(tsvNormal(text).replace(/\\([cvnpi])\[/gi,function(_,code){return "\\"+code.toLowerCase()+"[";}).replace(/\\[.|]/g,"").replace(/<\/?wordwrap>/gi,"").replace(/<br>/gi,"\n"));
}
function tsvProbeLocale(win){
    if(!tsv.valid||!tsv.probe||!tsv.visu||!win||typeof win.convertEscapeCharacters!=="function")return null;
    var value;
    identityDrawDepth++;
    try{value=win.convertEscapeCharacters("\\tl{"+tsv.probe[0]+"}");}
    catch(_){return null;}
    finally{identityDrawDepth--;}
    if(typeof value!=="string")return null;
    var key=tsvSurfaceKey(value),matches=[];
    for(var i=1;i<5;i++)if(tsvSurfaceKey(tsv.probe[i])===key)matches.push(i);
    if(matches.length!==1)return null;
    return matches[0]===1?"en":matches[0]===4?"ja":null;
}
function tsvRawMessage(){
    if(typeof $gameMessage==="undefined"||!$gameMessage)return "";
    var raw=$gameMessage._texts;
    return Array.isArray(raw)&&raw.every(function(x){return typeof x==="string";})?raw.join("\n"):$gameMessage.allText();
}
function tsvResolveKeys(raw,source){
    var complete=true,found=false;
    var value=tsvNormal(raw).replace(/\\tl\{([^{}\r\n]{1,300})\}/gi,function(token,key){
        var row=tsv.keys.get(key),cell=row&&row[source==="en"?1:4];
        if(!cell||!tsvCandidate(source,cell)){complete=false;return token;}
        found=true;return cell;
    });
    return complete&&found?value:null;
}
function tsvTranslatedKeys(raw,source,request){
    var complete=true,changed=false;
    var value=tsvNormal(raw).replace(/\\tl\{([^{}\r\n]{1,300})\}/gi,function(token,key){
        var row=tsv.keys.get(key),cell=row&&row[source==="en"?1:4],entry=cell&&tsvEntry(cell);
        if(!entry||entry.source!==source){complete=false;return token;}
        var out=tsvReady(entry,request);
        if(out===null){complete=false;return token;}
        changed=true;return out;
    });
    return changed&&complete?value:null;
}
// Match native-resolved values to the original, declared localization
// template without translating the name or modifying any game state.
function tsvHasDynamic(text){
    return typeof text==="string"&&/(?:\\|\x1b)[NVP]\[\d{1,5}\]/i.test(text);
}
function tsvExpandDynamic(text){
    var failed=false,expanded=tsvNormal(text).replace(/\\([NVP])\[(\d{1,5})\]/gi,function(token,type,id){
        var value,actor,number=Number(id);type=type.toUpperCase();
        try{
            if(type==="V"&&typeof $gameVariables!=="undefined"&&$gameVariables&&typeof $gameVariables.value==="function")
                value=$gameVariables.value(number);
            else if(type==="N"&&typeof $gameActors!=="undefined"&&$gameActors&&typeof $gameActors.actor==="function"){
                actor=$gameActors.actor(number);if(actor&&typeof actor.name==="function")value=actor.name();
            }else if(type==="P"&&typeof $gameParty!=="undefined"&&$gameParty&&typeof $gameParty.members==="function"){
                actor=$gameParty.members()[number-1];if(actor&&typeof actor.name==="function")value=actor.name();
            }
        }catch(_){failed=true;return token;}
        if(typeof value!=="string"&&typeof value!=="number"){failed=true;return token;}
        value=String(value);
        if(value.length>160||/[\u0000-\u001f\\<>{}]/.test(value)){failed=true;return token;}
        return value;
    });
    return failed?null:expanded;
}
function tsvMatchSurface(template,visual){
    if(tsvSurfaceKey(template)===tsvSurfaceKey(visual))return true;
    if(tsvHasDynamic(template)&&!tsvHasDynamic(visual)){
        var expanded=tsvExpandDynamic(template);
        return expanded!==null&&tsvSurfaceKey(expanded)===tsvSurfaceKey(visual);
    }
    return false;
}
// Author repetitions are not neural hallucinations. Require matching
// repeated complete utterances at the corresponding sentence positions.
function tsvAuthoredRepeat(original,result,composed){
    if(!composed||!tsv.detected)return false;
    function units(text){
        return protectedParts(text).filter(function(p){return !p.locked;})
            .map(function(p){return p.value;}).join(" ")
            .split(/[.!?。！？…]+/).map(function(v){
                return (v.toLowerCase().match(/[a-záéíóúüñà-ÿ\u3041-\u30fa\u3400-\u9fff]+/g)||[]).join(" ");
            }).filter(Boolean);
    }
    var a=units(original),b=units(result);
    if(a.length!==b.length||a.length<2)return false;
    var repeats=0;
    for(var i=1;i<b.length;i++){
        if(b[i]===b[i-1]&&b[i].split(" ").length>=3){
            if(a[i]!==a[i-1])return false;
            repeats++;
        }
    }
    return repeats>0;
}
function tsvJoinPlan(plan,translated){
    var out=[];
    for(var i=0;i<plan.length;i++){
        var value=translated[i],part=plan[i];
        if(!part.locked){
            if(part.lower)value=value.replace(/^[A-ZÁÉÍÓÚÜÑ]/,function(c){return c.toLowerCase();});
            if(i&&dynamicValue(plan[i-1].value)){
                var punctuation=/^[,;:]/.exec(part.value);
                if(punctuation&&!/^[,;:]/.test(value))value=punctuation[0]+" "+value;
            }
        }
        out.push(value);
    }
    return joinNativeParts(out);
}

function tsvAdaptNative(visual,result){
    var raw=tsvNormal(visual),out=tsvNormal(result);
    if(tsvHasDynamic(out)&&!tsvHasDynamic(raw)){
        out=tsvExpandDynamic(out);
        if(out===null)return null;
    }
    function standardCase(v){return v.replace(/\\([cvnpi])\[/gi,function(_,c){return "\\"+c.toLowerCase()+"[";});}
    // The author's layout may have consumed or removed timing markers.
    // Do not add a missing pause back after native conversion. Preserve
    // every actual non-layout control and every numeric argument.
    function signature(v){
        return protectedParts(v).filter(function(p){
            return p.locked&&!/^(?:\r?\n|<\/?wordwrap>|<br>)$/i.test(p.value);
        }).map(function(p){return p.value;}).join("\u0002");
    }
    if(!/\\[.|]/.test(raw))out=out.replace(/\\[.|]/g,"");
    if(signature(standardCase(raw))!==signature(standardCase(out))||numbersIn(raw)!==numbersIn(out))return null;
    var front=/^<wordwrap>/i.exec(raw),back=/<\/wordwrap>$/i.exec(raw);
    if(front&&!/^<wordwrap>/i.test(out))out=front[0]+out;
    if(back&&!/<\/wordwrap>$/i.test(out))out+=back[0];
    if(visual.indexOf("\x1b")>=0&&visual.indexOf("\\")<0)out=out.replace(/\\(?=[A-Za-z{}!.,|^<>$])/g,"\x1b");
    return out;
}
function tsvResolvedProjection(raw,visual,request){
    if(!tsv.valid||typeof raw!=="string"||typeof visual!=="string"||
       raw.length>1800||visual.length>1800||identityDrawDepth||actorNames[visual])return null;
    var entry=tsvMessageEntry(raw,visual);
    if(!entry)return null;
    var result=tsvRef(raw)?tsvTranslatedKeys(raw,entry.source,request):null;
    if(result===null)result=tsvReady(entry,request);
    return result===null?null:tsvAdaptNative(visual,result);
}

// Repair incomplete translations only for proven English table cells.
// Keep punctuation/control bytes and all intervening whitespace. A full
// cached translation with reasonable coverage still wins.
function tsvEnglishPlan(source,text){
    if(source!=="en"||!tsv.valid||!tsvEntry(text)||actorNames[text]||
       approvedKeys.has(source+"\u0000"+text))return null;
    var pieces=[],count=0;
    protectedParts(text).forEach(function(chunk){
        if(chunk.locked){pieces.push({value:chunk.value,locked:true});return;}
        var value=chunk.value,at=0,m,re=/[.!?]+[ \t]+(?=[A-Z])/g;
        function push(segment){
            var ws=/^([ \t]*)([\s\S]*?)([ \t]*)$/.exec(segment);
            if(ws&&/[A-Za-z]{2}/.test(ws[2])&&!actorNames[ws[2]]){
                if(ws[1])pieces.push({value:ws[1],locked:true});
                pieces.push({value:ws[2],locked:false});count++;
                if(ws[3])pieces.push({value:ws[3],locked:true});
            }else if(segment)pieces.push({value:segment,locked:true});
        }
        while((m=re.exec(value))!==null){
            var end=m.index+m[0].replace(/[ \t]+$/,"").length;
            if(/\b(?:Mr|Mrs|Ms|Dr|St|Prof|vs|etc)\.$/i.test(value.slice(at,end)))continue;
            push(value.slice(at,end));pieces.push({value:value.slice(end,re.lastIndex),locked:true});at=re.lastIndex;
        }
        push(value.slice(at));
    });
    // A bounded, comma-terminated English possessive after an RPG
    // placeholder can be assembled as "the noun" + " de " + placeholder.
    // No model is allowed to translate or invent the placeholder itself.
    for(var i=0;i+1<pieces.length;i++){
        if(!dynamicValue(pieces[i].value)||pieces[i+1].locked)continue;
        var tail=/^['’]s[ \t]+([A-Za-z][A-Za-z -]{1,49})([,;:])([ \t]*)([\s\S]*)$/.exec(pieces[i+1].value);
        if(!tail)continue;
        var preceding=i>0&&!pieces[i-1].locked?pieces[i-1].value:
            i>1&&!pieces[i-2].locked?pieces[i-2].value:"";
        var replacement=[{value:"the "+tail[1].trim(),locked:false,lower:!!preceding&&!/[.!?]$/.test(preceding)},
            {value:" de ",locked:true},pieces[i],{value:tail[2]+(tail[3]||" "),locked:true}];
        if(tail[4]){replacement.push({value:tail[4],locked:false});count++;}
        pieces.splice.apply(pieces,[i,2].concat(replacement));i+=replacement.length-1;
    }
    return count>=2&&count<=16?pieces:null;
}
function tsvCoverageSuspect(text,result,plan){
    if(!plan||typeof result!=="string")return false;
    var sw=(visibleProse(text).match(/[A-Za-z]+(?:'[A-Za-z]+)?/g)||[]).length;
    var visible=visibleProse(result),tw=(visible.match(/[A-Za-zÀ-ÖØ-öø-ÿ]+/g)||[]).length;
    // A markedly shortened result with fewer sentence/utterance endings
    // than the source is not evidence of a complete translation.
    var endings=function(v){return (v.match(/[.!?]+(?=\s|$)/g)||[]).length;};
    return sw>=4&&tw<sw*0.82&&endings(visible)<plan.filter(function(p){return !p.locked&&/[.!?]+$/.test(p.value);}).length;
}
function tsvPlanReady(source,text,plan){
    var pieces=[];
    for(var i=0;i<plan.length;i++){
        var p=plan[i],v=p.locked?p.value:readyText(source,p.value);
        if(v===null)return null;pieces.push(v);
    }
    var joined=tsvJoinPlan(plan,pieces);
    return acceptCache(source,text,joined,true,true)?cache.get(source+"\u0000"+text):null;
}
function tsvPlanTranslate(source,text,plan,priority){
    return Promise.all(plan.map(function(p){
        return p.locked?Promise.resolve(p.value):translatePreservingControls(source,p.value,true,priority);
    })).then(function(parts){
        if(parts.some(function(p){return p===null;})){
            var retry=0;
            parts.forEach(function(p,i){if(p===null){
                var at=rejectedKeys.get(source+"\u0000"+plan[i].value);
                if(at&&at!==Infinity&&at>Date.now())retry=Math.max(retry,at);
            }});
            if(retry)rejectedKeys.set(source+"\u0000"+text,retry);
            return null;
        }
        var joined=tsvJoinPlan(plan,parts);
        return acceptCache(source,text,joined,true,true)?cache.get(source+"\u0000"+text):null;
    });
}

function tsvRegister(source,text){
    if(!tsvCandidate(source,text))return null;
    var entry={source:source,text:text},key=tsvNormal(text);
    csvSetUnique(tsv.display,key,entry,function(a,b){return a.source===b.source&&a.text===b.text;});
    csvSetUnique(tsv.visual,tsvVisualKey(text),entry,function(a,b){return a.source===b.source&&a.text===b.text;});
    csvSetUnique(tsv.loose,tsvSurfaceKey(text),entry,function(a,b){return a.source===b.source&&a.text===b.text;});
    return entry;
}
function tsvRead(done){
    if(tsv.done){done();return;}
    if(tsv.loading)return;
    tsv.loading=true;
    var dir=path.join(content,"data"),file=path.join(dir,"Languages.tsv");
    function finish(ok){
        tsv.done=true;tsv.loading=false;
        if(ok)scanStats.files++;else scanStats.skipped++;
        done();
    }
    if(!regularUnder(dir,file,4*1024*1024)){finish(false);return;}
    fs.readFile(file,"utf8",function(err,raw){
        if(err||typeof raw!=="string"||Buffer.byteLength(raw,"utf8")>4*1024*1024){finish(false);return;}
        try{
            // This TSV dialect is literal tabs and line endings, not
            // RFC-4180 quoting. Require all five columns for every row.
            var lines=raw.replace(/^\uFEFF/,"").split(/\r?\n/);
            var header=(lines.shift()||"").split("\t").map(function(s){return s.trim().toLowerCase();});
            if(header.join("\t")!=="key\tenglish\tchinese(simplified)\tchinese(traditional)\tjapanese"||
               lines.length>20000){finish(false);return;}
            var records=[];
            for(var i=0;i<lines.length;i++){
                if(!lines[i].trim())continue;
                var cells=lines[i].split("\t");
                if(cells.length!==5){tsv.skippedRows++;continue;}
                if(cells[0]&&cells[0].length<=300&&!/[{}\u0000]/.test(cells[0]))records.push(cells);
            }
            // Conflicting keys are not guessed; exact already-resolved
            // display values can still be translated independently.
            records.forEach(function(c){
                if(c[2])tsv.chinese.set(c[2],true);
                if(c[3])tsv.chinese.set(c[3],true);
                csvSetUnique(tsv.keys,c[0],c,function(a,b){return a.join("\t")===b.join("\t");});
            });
            tsv.keys.forEach(function(v){if(!v)tsv.conflicts++;});
            var entries=[];
            records.forEach(function(c){
                var en=tsvRegister("en",c[1]),ja=tsvRegister("ja",c[4]);
                if(en)entries.push(en);
                if(ja)entries.push(ja);
                // Bilingual reuse is safe only when the native codes and
                // numbers match exactly; otherwise translate each column.
                if(en&&ja&&csvControlSignature(en.text)===csvControlSignature(ja.text)&&numbersIn(en.text)===numbersIn(ja.text)){
                    csvSetUnique(csvAlternate,"ja\u0000"+ja.text,en,function(a,b){return a.source===b.source&&a.text===b.text;});
                }
            });
            if(!records.length){finish(false);return;}
            if(tsv.visu){
                records.some(function(c){
                    if(tsv.keys.get(c[0])!==c||!/^[A-Za-z][0-9]+$/.test(c[0]))return false;
                    var vals=c.slice(1);
                    if(vals.some(function(v){return v.length<2||v.length>100||/[\\<>\[\]{}$%\u0000-\u001f]/.test(v);})||
                       vals.some(function(v,i){return vals.indexOf(v)!==i;}))return false;
                    tsv.probe=c;return true;
                });
            }
            tsv.rows=records.length;tsv.valid=true;
            // Map/title can have become active before the asynchronous
            // table read completed. Replay its keys before bulk inference.
            tsv.priority.forEach(function(live,key){tsvQueueKey(key,live);});
            tsv.priority.clear();
            if(typeof $dataMap!=="undefined"&&$dataMap)scanMap($dataMap,true);
            // Establish the entire provenance index before scheduling.
            // Queue English first, then Japanese; actual visible requests
            // are prioritized by the existing foreground scheduler.
            entries.sort(function(a,b){return a.source===b.source?0:a.source==="en"?-1:1;});
            var at=0;
            function slice(){
                var end=Math.min(at+180,entries.length);
                for(;at<end;at++){
                    var e=entries[at];
                    if(tsvEntry(e.text)&&tsvEntry(e.text).source===e.source){
                        addPrefetch(e.text,false,e.source);
                        tableStats.candidates++;
                    }
                }
                if(at<entries.length){setTimeout(slice,0);return;}
                finish(true);nextPrefetch();
            }
            slice();
        }catch(_){state.errors++;finish(false);}
    });
}
function tsvKeyEntries(key){
    var row=tsv.keys.get(key);
    if(!row)return [];
    return [tsvEntry(row[1]),tsvEntry(row[4])].filter(Boolean);
}
function tsvRequest(entry){
    if(!entry||actorNames[entry.text])return;
    addPrefetch(entry.text,true,entry.source);
    if(state.connected&&cacheReadDone&&readyText(entry.source,entry.text)===null)
        csvRequestLive(entry.source,entry.text);
    nextPrefetch();
}
function tsvQueueKey(key,live){
    var entries=tsvKeyEntries(key);
    if(!entries.length)return;
    var preferred=entries.filter(function(e){return e.source===tsv.language;})[0]||entries[0];
    if(live)tsvRequest(preferred);
    else addPrefetch(preferred.text,true,preferred.source);
}
function tsvPrioritize(text,live){
    if(!tsv.detected||!tsvRef(text))return;
    text.replace(/(?:\\|\x1b)tl\{([^{}\r\n]{1,300})\}/gi,function(token,key){
        if(!tsv.valid){
            if(tsv.priority.size<20000||tsv.priority.has(key))tsv.priority.set(key,!!live||!!tsv.priority.get(key));
        }else tsvQueueKey(key,!!live);
        return token;
    });
}
function tsvReady(entry,request){
    if(!entry||actorNames[entry.text])return null;
    var out=readyText(entry.source,entry.text);
    if(typeof out==="string"&&validTranslation(entry.source,entry.text,out,true))return out;
    if(request)tsvRequest(entry);
    return null;
}
function tsvProject(text,request){
    if(!tsv.detected||typeof text!=="string"||text.length>1800||identityDrawDepth||
       actorNames[text]||csvExecutableSyntax(text))return null;
    var normal=tsvNormal(text),out=null;
    if(tsvRef(normal)){
        var failed=false,changed=false;
        // Resolve only explicit lookup references. All populated columns
        // must agree on the control/number signature before bypassing the
        // author's lookup; otherwise let the author resolve it first.
        out=normal.replace(/\\tl\{([^{}\r\n]{1,300})\}/gi,function(token,key){
            var row=tsv.keys.get(key),entries=tsvKeyEntries(key);
            if(!row||!entries.length){failed=true;return token;}
            var chosen=entries[0],sig=csvControlSignature(chosen.text),nums=numbersIn(chosen.text);
            if(row.slice(1).some(function(v){return v&&(csvControlSignature(v)!==sig||numbersIn(v)!==nums);})){
                if(request)tsvQueueKey(key,true);
                failed=true;return token;
            }
            var translated=null;
            entries.sort(function(a,b){return a.source===b.source?0:a.source===tsv.language?-1:1;});
            for(var i=0;i<entries.length&&translated===null;i++)translated=tsvReady(entries[i],false);
            if(translated===null&&request)tsvRequest(entries[0]);
            if(translated===null){failed=true;return token;}
            changed=true;return translated;
        });
        if(failed||!changed)return null;
    }else{
        out=tsvReady(tsvEntry(normal),request);
        if(out===null)return null;
    }
    // Maintain the phase of escape conversion used by native windows.
    if(text.indexOf("\x1b")>=0&&text.indexOf("\\")<0)out=out.replace(/\\(?=[A-Za-z{}!.,|^<>$])/g,"\x1b");
    return out===text?null:out;
}
// Check what the author's own loader actually resolved, including two
// lookup keys in a message and visual line breaks introduced by wrapping.
// Only a positively matched native message is eligible for this adapter.
function tsvMessageEntry(raw,visual){
    if(!tsv.valid||typeof visual!=="string"||visual.length>1800||tsvRef(visual))return null;
    var exact=tsvEntry(visual),key=tsvSurfaceKey(visual);
    // With explicit raw references, require the actual loader output to
    // match that key's selected column, not an unrelated global alias.
    if(tsvRef(raw)){
        var matches=[];
        ["en","ja"].forEach(function(source){
            var candidate=tsvResolveKeys(raw,source);
            if(candidate&&tsvMatchSurface(candidate,visual)&&tsvCandidate(source,candidate))matches.push({source:source,text:candidate});
        });
        if(matches.length!==1)return null;
        var found=matches[0];
        if(!tsvEntry(found.text))tsvRegister(found.source,found.text);
        tsv.language=found.source;return found;
    }
    var alias=exact||tsv.visual.get(tsvVisualKey(visual))||tsv.loose.get(key);
    if(alias){tsv.language=alias.source;return alias;}
    return null;
}
function tsvTicketCurrent(win,t){
    return !!t&&win._iaLateTicket===t&&typeof SceneManager!=="undefined"&&SceneManager._scene===t.scene&&
        typeof $gameMessage!=="undefined"&&$gameMessage===t.message&&$gameMessage.hasText()&&
        $gameMessage.allText()===t.displayed&&
        (!t.entry||!tsvHasDynamic(t.entry.text)||tsvMatchSurface(t.entry.text,t.visualOriginal));
}
function tsvEarlyPaint(win,t){
    var ts=win._textState;
    if(inputFormActive()||t.formEpoch!==formEpoch||!ts||!t.result||ts.index!==0||ts.rtl||ts.buffer||ts.text!==t.visualOriginal||!tsvTicketCurrent(win,t))return false;
    var result=tsvAdaptNative(ts.text,t.result);
    if(result===null||!nativeRenderParts(result))return false;
    ts.text=result;state.shown++;tsv.shown++;hideLate(win);
    return true;
}
function tsvRefreshTicket(win,t){
    if(inputFormActive()||t.formEpoch!==formEpoch||!tsvTicketCurrent(win,t))return;
    var entry=t.entry||tsvMessageEntry(t.rawKeys||t.displayed,t.visualOriginal);
    if(!entry)return;
    t.entry=entry;t.original=entry.text;t.source=entry.source;
    var result=tsvRef(t.rawKeys||t.displayed)?tsvTranslatedKeys(t.rawKeys||t.displayed,entry.source,false):null;
    if(result===null)result=tsvReady(entry,false);
    if(result!==null&&result!==entry.text){
        t.result=tsvAdaptNative(t.visualOriginal,result);
        if(t.result!==null)tsvEarlyPaint(win,t);
    }else if(!t.lastRequest||Date.now()-t.lastRequest>=500){
        t.lastRequest=Date.now();tsvRequest(entry);
    }
}
function tsvLateTicket(win){
    if(!tsv.detected||win._iaLateTicket||!win._textState||
       typeof $gameMessage==="undefined"||!$gameMessage||!$gameMessage.hasText())return;
    var text=win._textState.text,raw=$gameMessage.allText(),keys=tsvRawMessage();
    if(!nativeRenderParts(text))return;
    var entry=tsvMessageEntry(keys,text);
    if(!entry&&!tsvRef(keys))return;
    var scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
    if(!scene)return;
    var ticket={message:$gameMessage,displayed:raw,rawKeys:keys,visualOriginal:text,
        original:entry?entry.text:text,source:entry?entry.source:null,entry:entry,
        tsv:true,scene:scene,result:null,drawn:false,pages:1,geometry:null,formEpoch:formEpoch};
    win._iaLateTicket=ticket;lateStats.requested++;
    tsvRefreshTicket(win,ticket);
}

var csvKnown=new Map(),csvAuthored=new Map(),csvAlternate=new Map(),csvResolving=false,csvPreferred="en";
var csvRenderAliases=new Map(),csvNameTemplates=new Map(),csvNameCount=0,csvLiveRequests=new Map();
var csvUiStats={choices:0,drawn:0,overflow:0,rows:0};
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
    if(!source||questTexts.has(text))return;
    questTexts.set(text,source);questStats.fields++;
    addPrefetch(text,false,source);
    // Titles may be drawn by a custom book directly without their color code.
    var plain=text.replace(/^(?:<WordWrap>|\\c\[\d{1,3}\])+/gi,"").trim();
    if(plain!==text&&plain&&!/[\\<>\x1b]/.test(plain))registerQuestText(plain);
}
function questValues(value,depth){
    if(depth>5||value===null||value===undefined)return;
    if(Array.isArray(value)){value.forEach(function(v){questValues(v,depth+1);});return;}
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
var visuQuestScanned=false;
function boundedQuestJson(value,limit){
    if(typeof value!=="string"||value.length>limit||!value.trim())return null;
    try{return JSON.parse(value);}catch(_){return null;}
}
function registerVisuQuestField(raw,priority){
    if(typeof raw!=="string"||!raw.trim()||raw.length>1800||csvExecutableSyntax(raw)||
       /\[\[[A-Za-z]+\]\]|(?:\\|\x1b)(?:js|eval|script)\b/i.test(raw))return;
    var e=questEnvelope(raw),body=e.body;
    if(!body.trim()||actorNames[body]||visuQuestFixed(body)!==null)return;
    var source=languageFor(body);
    if(!source&&!isJapanese(body)&&/^[A-Za-z][A-Za-z0-9 .,'’!?:\/\-]{0,119}$/.test(body)&&!/[áéíóúüñ¿¡]/i.test(body))source="en";
    if(!source)return;
    if(!questTexts.has(body)){questTexts.set(body,source);questStats.fields++;}
    addPrefetch(body,priority,source);
    if(body.indexOf("\n")>=0)body.split(/\r?\n/).forEach(function(line){
        if(line!==body&&line.trim())registerVisuQuestField(line,priority);
    });
}
function scanVisuQuestParameters(){
    if(visuQuestScanned||!visuQuestEnabled()||typeof $plugins==="undefined")return;
    visuQuestScanned=true;
    var plugin=$plugins.filter(function(v){return v&&v.status&&v.name==="VisuMZ_2_QuestSystem";})[0],p=plugin&&plugin.parameters;
    if(!p)return;
    var active=Object.create(null),general=boundedQuestJson(p["General:struct"],262144);
    if(general&&typeof general==="object"&&!Array.isArray(general)){
        ["KnownQuests:arraystr","CompletedQuests:arraystr","FailedQuests:arraystr"].forEach(function(k){
            var keys=boundedQuestJson(general[k],65536);
            if(Array.isArray(keys))keys.slice(0,1000).forEach(function(key){if(typeof key==="string")active[key]=true;});
        });
        if(typeof general["TrackedQuest:str"]==="string")active[general["TrackedQuest:str"]]=true;
        ["CommandWindow_Known_Text:str","CommandWindow_Completed_Text:str","CommandWindow_Failed_Text:str",
         "EmptyTitleLabel:str","NoQuestListed:str","ButtonAssistPageUpDown:str","questButtonAssistActive:str",
         "ButtonAssistExpand:str","ButtonAssistCollapse:str"].forEach(function(k){registerVisuQuestField(general[k],true);});
        var empty=boundedQuestJson(general["LogEmpty:json"],32768);
        if(typeof empty==="string")registerVisuQuestField(empty,true);
        // LogFmt contains [[Title]] and other executable-format markers:
        // translate the visible headers at rendering, never that template.
    }
    var cats=boundedQuestJson(p["Categories:arraystruct"],4*1024*1024);
    if(!Array.isArray(cats)||cats.length>200)return;
    cats.forEach(function(encoded){
        var cat=boundedQuestJson(encoded,1024*1024);
        if(!cat||typeof cat!=="object"||Array.isArray(cat))return;
        registerVisuQuestField(cat["CategoryName:str"],true);
        var rows=boundedQuestJson(cat["Quests:arraystruct"],1024*1024);
        if(!Array.isArray(rows)||rows.length>2000)return;
        rows.forEach(function(encodedRow){
            var row=boundedQuestJson(encodedRow,65536);
            if(!row||typeof row!=="object"||Array.isArray(row))return;
            questStats.records++;
            var priority=!!active[row["Key:str"]];
            ["Title:str","Difficulty:str"].forEach(function(k){registerVisuQuestField(row[k],priority);});
            // From is an identity field. Translate generic place captions,
            // but not an arbitrary name of a quest giver or location.
            var loc=row["Location:str"];
            if(typeof loc==="string"&&/\b(?:castle|forest|village|town|city|garden|market|river|hall|library|temple|room|gate|school|park|station|bridge)\b/i.test(loc))
                registerVisuQuestField(loc,priority);
            ["Description:arrayjson","Objectives:arrayjson","Rewards:arrayjson","Subtext:arrayjson","Quotes:arrayjson"].forEach(function(k){
                var list=boundedQuestJson(row[k],65536);
                if(Array.isArray(list)&&list.length<=300)list.forEach(function(v){
                    var raw=boundedQuestJson(v,16384);
                    if(typeof raw==="string")registerVisuQuestField(raw,priority);
                });
            });
        });
    });
}
function scanQuestParameters(done){
    scanVisuQuestParameters();
    if(typeof $plugins==="undefined"||!Array.isArray($plugins)){done();return;}
    var tasks=[],taskAt=0;
    $plugins.forEach(function(plugin){
        if(!plugin||!plugin.status||!/^YEP_(?:QuestJournal|X_MoreQuests\d+)$/.test(plugin.name)||!plugin.parameters)return;
        Object.keys(plugin.parameters).forEach(function(k){
            if(/^Quest \d{1,5}$/.test(k))tasks.push(plugin.parameters[k]);
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
        while(taskAt<tasks.length&&cap--){
            var value=tasks[taskAt++];
            try{
                var entry=typeof value==="string"&&value.length<=65536?JSON.parse(value):value;
                if(!entry||typeof entry!=="object"||Array.isArray(entry))continue;
                questStats.records++;
                // Location is an identity field as well as a caption. Only
                // generic place labels and recognizable generic phrases are
                // translation candidates. A lone invented proper name stays.
                if(typeof entry.Location==="string"){
                    var loc=entry.Location.trim();
                    if(/\b(?:castle|forest|village|town|city|courtyard|garden|road|market|river|mountain|cave|hall|library|temple|inn|shop|tower|bridge|dungeon|room|gate|field|farm|harbor|port)\b/i.test(loc)&&
                       !Object.prototype.hasOwnProperty.call(questLabels,loc))questValues(entry.Location,0);
                }
                ["Title","Type","Difficulty","Description","Objectives List","Rewards List","Subtext"].forEach(function(k){
                    if(Object.prototype.hasOwnProperty.call(entry,k))questValues(entry[k],0);
                });
            }catch(_){}
        }
        nextPrefetch();
        if(taskAt<tasks.length)setTimeout(slice,0);else done();
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
    var stack=[{values:data.root,index:0,evalMode:false,tag:false}];
    function addContainer(v,mode,tag){
        if(Array.isArray(v))stack.push({values:v,index:0,evalMode:mode,tag:tag});
    }
    function slice(){
        var budget=700;
        while(stack.length&&budget--){
            var f=stack[stack.length-1];
            if(f.index>=f.values.length){stack.pop();continue;}
            var v=f.values[f.index++];
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
        if(stack.length){setTimeout(slice,0);return;}
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
function remNativeActive(){
    return remNative.detected&&typeof ConfigManager!=="undefined"&&
        typeof RemLanguageSP!=="undefined"&&ConfigManager.remLanguage===RemLanguageSP;
}
function remNativeSpanishText(raw){
    return typeof raw==="string"&&remNativeActive()&&remNative.spanish.has(raw);
}
function readRemCatalog(base,name){
    var file=path.join(base,name);
    if(!regularUnder(base,file,4*1024*1024))return null;
    var raw=fs.readFileSync(file,"utf8");
    if(typeof raw!=="string"||raw.length>4*1024*1024)return null;
    var doc=JSON.parse(raw.replace(/^\uFEFF/,""));
    if(!doc||typeof doc!=="object"||Array.isArray(doc)||Object.keys(doc).length>16000)return null;
    return doc;
}
function remCatalogLines(doc,key,field){
    if(!doc||!Object.prototype.hasOwnProperty.call(doc,key))return null;
    var v=doc[key],lines=v&&v[field];
    return Array.isArray(lines)&&lines.length<=256&&lines.every(function(line){
        return typeof line==="string"&&line.length<=4096&&!/[\u0000\uFFFD]/.test(line);
    })?lines:null;
}
function remIndexSpanish(text){
    if(typeof text==="string"&&text.trim()&&text.length<=1800&&remNative.spanish.size<60000){
        remNative.spanish.add(text);
    }
}
function remReadPairs(base,enFile,spFile,field,kind){
    var en=readRemCatalog(base,enFile),sp=readRemCatalog(base,spFile);
    if(!en||!sp)return false;
    var matched=0,valid=0;
    Object.keys(en).forEach(function(key){
        if(!/^[A-Za-z0-9_ -]{1,180}$/.test(key))return;
        var from=remCatalogLines(en,key,field);if(!from||!from.length)return;
        valid++;
        var to=remCatalogLines(sp,key,field),raw=from.join("\n");
        if(to&&to.length){
            matched++;
            var shown=to.join("\n");
            if(raw!==shown){
                remIndexSpanish(shown);
                if(from.length===to.length)to.forEach(function(line,i){if(line!==from[i])remIndexSpanish(line);});
                else to.forEach(function(line){if(from.indexOf(line)<0)remIndexSpanish(line);});
                return;
            }
        }
        // Some native entries really are untranslated. Only complete plain
        // English prose is eligible; never infer a name, key or custom macro.
        if(kind&&/^[A-Za-z][A-Za-z0-9 ,.'’!?;:()\-]{12,399}$/.test(raw)&&
           /[.!?]$/.test(raw)&&!/[áéíóúüñ¿¡]/i.test(raw)&&
           remNative.fallback.size<2000)
            remNative.fallback.set(kind+":"+key,raw);
    });
    return valid>0&&matched>0&&matched/valid>=0.75;
}
function detectRemNative(){
    if(isMZ||!content||typeof ConfigManager==="undefined"||typeof TextManager==="undefined"||
       typeof RemLanguageSP==="undefined"||typeof RemLanguageEN==="undefined"||
       !integer(RemLanguageSP)||!integer(RemLanguageEN)||RemLanguageSP===RemLanguageEN||
       typeof ConfigManager.applyData!=="function"||typeof TextManager.getLocalizedMapMappings!=="function"||
       typeof TextManager.getLocalizedDescriptionMappings!=="function"||
       typeof TextManager.remMiscMapText!=="function"||typeof TextManager.remMiscDescriptionText!=="function"||
       !["RemtairyTextManager","RemtairyTextManager_SP","RemtairyConfigManager","RemtairyMisc","RemtairyLines"].every(function(name){
           return typeof $plugins!=="undefined"&&Array.isArray($plugins)&&$plugins.some(function(p){return p&&p.status&&p.name===name;});
       }))return;
    try{
        var base=path.join(content,"loc");
        if(!directoryUnder(content,base))return;
        var maps=TextManager.getLocalizedMapMappings(),descs=TextManager.getLocalizedDescriptionMappings();
        if(!maps||!descs||typeof maps.has!=="function"||typeof descs.has!=="function"||
           !maps.has(RemLanguageSP)||!descs.has(RemLanguageSP))return;
        if(!remReadPairs(base,"RemMap_EN.json","RemMap_SP.json","text","MAP")||
           !remReadPairs(base,"RemDesc_EN.json","RemDesc_SP.json","text","DESC")||
           !remReadPairs(base,"RemLines.json","RemLines_SP.json","en",null)){
            remNative.spanish.clear();remNative.fallback.clear();return;
        }
        remNative.detected=true;
        // The authored difficulty event chooses language-specific pictures.
        // Before auto-selecting Spanish, ensure those variants actually
        // exist locally (ordinary PNG or RPG Maker encrypted PNG).
        var pics=path.join(content,"img","pictures");
        remNative.images=directoryUnder(content,pics)&&["easy","normal","hard"].every(function(mode){
            return [1,2].every(function(i){
                var name="difficulty_"+mode+i+"_SP";
                return [".png",".rpgmvp"].some(function(ext){return regularUnder(pics,path.join(pics,name+ext),64*1024*1024);});
            });
        });
    }catch(_){remNative.detected=false;remNative.images=false;remNative.spanish.clear();remNative.fallback.clear();}
}
function preferRemNativeSpanish(){
    if(!remNative.detected||remNative.configured)return;
    remNative.configured=true;
    // A Spanish-target translator may prefer the author's Spanish text for
    // an English-language boot. Never rewrite a voice setting or call save.
    // A later explicit language change is left entirely to the game.
    if(remNative.images&&ConfigManager.remLanguage===RemLanguageEN)
        ConfigManager.remLanguage=RemLanguageSP;
}
function remNativeFallback(raw){
    if(!remNativeActive()||typeof raw!=="string")return null;
    var m=/^(?:\\|\x1b)REM_(MAP|DESC)\[([A-Za-z0-9_]{1,180})\]$/i.exec(raw);
    if(!m)return null;
    var body=remNative.fallback.get(m[1].toUpperCase()+":"+m[2]);
    return body&&languageFor(body)==="en"?body:null;
}
function hookRemNative(){
    if(!remNative.detected)return;
    var apply=ConfigManager.applyData;
    ConfigManager.applyData=function(){
        var out=apply.apply(this,arguments);preferRemNativeSpanish();return out;
    };
    // Only these native text accessors, never the identifier, menu branch,
    // database object, loaded catalog or language mapping itself.
    [["remMiscMapText","MAP"],["remMiscDescriptionText","DESC"]].forEach(function(pair){
        var method=pair[0],native=TextManager[method];
        TextManager[method]=function(id){
            var raw=native.apply(this,arguments);
            if(!remNativeActive()||typeof id!=="string"||inputFormActive())return raw;
            var candidate=remNative.fallback.get(pair[1]+":"+id);
            if(!candidate||candidate!==raw||languageFor(raw)!=="en")return raw;
            var value=readyText("en",raw);
            if(value!==null)return value;
            firstViewRequest("en",raw);return raw;
        };
    });
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
function csvRows(raw,maxRows){
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
        }else cell+=ch;
    }
    if(quoted)return null;
    if(cell||row.length){row.push(cell);rows.push(row);}
    return rows;
}
// Explicit schemas for sheet-based localization (KNS/MEO and generic
// id/key language tables). Read-only: never execute a script column, change
// an event id, write a CSV, or switch the game's language/configuration.
function detectRootCsv(){
    if(!content)return false;
    var dir=path.join(content,"csv");
    if(!directoryUnder(content,dir))return false;
    // A root CSV directory is inventoried even without a known loader;
    // each file must still match an explicit display schema.
    tableStats.root=true;
    // Bounded larger inventory/cache only for the detected external tables.
    // Keep the in-memory translation cache bounded; candidate discovery has no fixed count ceiling.
    MAX_CACHE_ENTRIES=150000;CACHE_LIMIT=128*1024*1024;
    return true;
}
function csvNormalize(value){
    return value.replace(/\r\n/g,"\n").replace(/\\\\(?=(?:c|n|v|i|p|ce|g)\[)/gi,"\\");
}
function csvForms(value){
    if(typeof value!=="string"||!value.trim()||value.length>1800)return [];
    // The sheet dialect can use slash + newline to delimit display blocks.
    // They are not part of the emitted dialogue. Preserve all actual MV
    // escape codes inside each block, and never alter the source file.
    return csvNormalize(value).split(/\/\n/).filter(function(v){return v.trim();});
}
function csvExecutableSyntax(value){
    // Do not misclassify visible English such as "Let me out" as a JS
    // declaration. Require a declaration operator/terminator after the name.
    return typeof value==="string"&&(/\b(?:if|en|eval|set_mlog|setTimeout)\s*\(|\$(?:v|s|game\w*|data\w*)\s*[\[(]|\\(?:eval|script)\b/i.test(value)||
        /(?:^|\n)\s*(?:[\w.]+\s*=\s*[^=]|function\s+[A-Za-z_$][\w$]*\s*\(|(?:var|let|const)\s+[A-Za-z_$][\w$]*\s*(?:=|;|,))/i.test(value));
}
function csvCandidate(value,declared,allowNote){
    if(typeof value!=="string"||!value.trim()||value.length>1800||actorNames[value]||csvExecutableSyntax(value))return null;
    if((!allowNote&&/^\s*※/.test(value))||/^\s*(?:\/\/|[#=$@+])/i.test(value)||
       /\b(?:if|en)\s*\(|\$(?:v|s|game\w*|data\w*)\s*[\[(]|(?:^|\n)\s*[\w.]+\s*=\s*[^=]/i.test(value)||
       /\b(?:eval|set_mlog|setTimeout)\s*\(/i.test(value))return null;
    var prose=visibleProse(value).trim();
    if(isJapanese(prose))return "ja";
    return declared==="en"&&/[A-Za-z]{2}/.test(prose)&&!/^[A-Za-z0-9_]+\.(?:png|ogg|js|json|csv)$/i.test(prose)?"en":null;
}
function csvControlSignature(text){
    return protectedParts(text).filter(function(p){return p.locked;}).map(function(p){return p.value;}).join("\u0002");
}
function csvMark(source,text){
    csvKnown.set(text,source);
    var key=csvRenderKey(text);
    if(key&&key!==text){
        csvSetUnique(csvRenderAliases,key,{source:source,text:text},function(a,b){
            return a.source===b.source&&csvRenderKey(a.text)===csvRenderKey(b.text);
        });
    }
    // Index any authored database/script template, including multiline profiles.
    rememberNameTemplate(source,text);
}
function csvSetUnique(map,key,value,equals){
    if(map.has(key)){
        var old=map.get(key);
        if(old!==null&&!equals(old,value))map.set(key,null);
    }else map.set(key,value);
}
function csvSpanish(value){
    return typeof value==="string"&&!isJapanese(visibleProse(value))&&
        /[áéíóúüñ¿¡]|\b(?:el|la|los|las|de|del|que|para|con|una?|por|este|esta|soy|eres|está|estamos|hola|sí|gracias|puede|puedes|tienes)\b/i.test(visibleProse(value));
}
// Explicit Spanish column is stronger evidence than a stopword test for
// short labels. Reject identical values, code, and obvious English prose.
function csvExplicitSpanish(value,original){
    if(typeof value!=="string"||!value.trim()||value===original||csvExecutableSyntax(value)||isJapanese(visibleProse(value)))return false;
    if(csvSpanish(value))return true;
    var plain=visibleProse(value).trim();
    return /^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ -]{1,39}[.!:]?$/.test(plain)&&
        !/\b(?:the|you|your|with|this|that|and|from|please|would|should|what|when|here|there)\b/i.test(plain);
}
function csvRenderKey(text){
    if(typeof text!=="string"||!text.trim()||text.length>1800)return null;
    return csvNormalize(text).replace(/\\,/g,",").replace(/\x1b(?=[A-Za-z])/g,"\\").trim();
}
function csvRegisterKnown(source,text,es,allowNote){
    csvMark(source,text);
    if(csvExplicitSpanish(es,text)&&validTranslation(source,text,es,true)){
        var key=source+"\u0000"+text;
        if(!csvAuthored.has(key))tableStats.authored++;
        csvSetUnique(csvAuthored,key,es,function(a,b){return a===b;});
    }
    var lines=text.split("\n"),translated=typeof es==="string"?es.split("\n"):[];
    if(lines.length>1)lines.forEach(function(line,i){
        var lang=csvCandidate(line,source,allowNote);
        if(!lang)return;
        csvMark(lang,line);
        if(lines.length===translated.length&&csvExplicitSpanish(translated[i],line)&&validTranslation(lang,line,translated[i],true))
            csvSetUnique(csvAuthored,lang+"\u0000"+line,translated[i],function(a,b){return a===b;});
    });
}
function csvRegisterPair(japanese,english,spanish,priority,allowNote){
    var jp=csvForms(japanese),en=csvForms(english),es=csvForms(spanish);
    var primary=csvPreferred==="ja"?jp:en,alt=csvPreferred==="ja"?en:jp,
        primaryLang=csvPreferred,altLang=csvPreferred==="ja"?"en":"ja";
    if(!primary.length){primary=alt;primaryLang=altLang;alt=[];}
    // Register the bare label of a verified choice with a narrow trailing
    // condition. Do not evaluate, translate or reconstruct the expression.
    function bare(value){
        var m=/^(.+?)\s+(?:(?:if|en)\s*\([A-Za-z0-9_\s\[\]!<>=&|+\-*/%.]+\)\s*)+$/i.exec(value);
        return m?m[1]:value;
    }
    primary=primary.map(bare);alt=alt.map(bare);
    var records=[];
    primary.forEach(function(value,i){
        var source=csvCandidate(value,primaryLang,allowNote);
        records[i]=source?{source:source,text:value}:null;
        if(!source)return;
        var official=es.length===primary.length?es[i]:null;
        csvRegisterKnown(source,value,official,allowNote);
        tableStats.candidates++;
        addPrefetch(value,priority,source);
    });
    alt.forEach(function(other,i){
        var source=csvCandidate(other,altLang,allowNote);
        if(!source)return;
        var value=primary.length===alt.length?records[i]:null;
        if(value&&other===value.text)return;
        csvRegisterKnown(source,other,es.length===alt.length?es[i]:null,allowNote);
        if(value&&source!==value.source&&csvControlSignature(other)===csvControlSignature(value.text)&&numbersIn(other)===numbersIn(value.text)){
            var key=source+"\u0000"+other;
            csvSetUnique(csvAlternate,key,value,function(a,b){return a.source===b.source&&a.text===b.text;});
            if(csvAlternate.get(key)!==null)return;
        }
        // Unequal block counts, a rejected primary cell, or ambiguous
        // bilingual mapping must not silently discard the other language.
        tableStats.candidates++;addPrefetch(other,priority,source);
    });
}
function csvAlternateReady(source,text){
    if(typeof csvAlternate==="undefined"||csvResolving)return null;
    var alternate=csvAlternate.get(source+"\u0000"+text);
    if(!alternate)return null;
    csvResolving=true;
    try{
        var result=readyText(alternate.source,alternate.text);
        return typeof result==="string"&&validTranslation(source,text,result,true)?result:null;
    }finally{csvResolving=false;}
}
function rootCsvSchema(relative,rows){
    var h=rows[0]||[],name=relative.toLowerCase().replace(/\\/g,"/");
    function exact(index,pattern){return pattern.test((h[index]||"").trim());}
    if((name==="sheet.csv"||name==="commonsheet.csv")&&exact(2,/^日本語$/)&&exact(3,/^(?:英語|English)$/i))
        return {type:"sheet",start:1,width:h.length,groups:[[2,3,4]]};
    if(name==="logsheet.csv"&&exact(1,/^日本語$/)&&exact(2,/^(?:英語|English)$/i)&&exact(3,/^(?:Spanish|スペイン語)$/i))
        return {type:"log",start:1,width:h.length,groups:[[1,2,3]]};
    if(name==="questlist.csv"&&h.length===27&&exact(6,/^日本語$/)&&exact(13,/^English$/i)&&exact(20,/^Espanol$/i))
        return {type:"quest",start:2,width:27,groups:[[6,13,20],[7,14,21],[8,15,22],[9,16,23],[10,17,24],[11,18,25],[12,19,26]]};
    if(name==="db_npc.csv"&&exact(9,/^プロフィール\/JP$/)&&exact(10,/^プロフィール\/EN$/)&&exact(12,/^プロフィール\/SP$/))
        return {type:"npc",start:1,width:h.length,groups:[[9,10,12]]};
    if(/^db_(?:item|skill|armor|weapon|class|state)\.csv$/.test(name)&&exact(0,/^\$id=0$/)){
        var jp=h.indexOf("JPN_NAME"),en=h.indexOf("ENG_NAME"),es=h.indexOf("SPN_NAME");
        if(jp<0||en<0||es<0)return null;
        var groups=[[jp,en,es]];
        if(/^(?:DESCRIPT|DESCRIPTION)$/.test(h[jp+1]||"")&&h[jp+1]===h[en+1]&&h[en+1]===h[es+1])
            groups.push([jp+1,en+1,es+1]);
        return {type:"db",start:1,width:h.length,groups:groups};
    }
    if(/^common\/event_\d+\.csv$/.test(name)&&exact(0,/^0$/)&&exact(1,/^日本語$/)&&exact(2,/^English$/i))
        return {type:"numeric",start:1,width:h.length,groups:[[1,2,-1]]};
    // The legacy page tables have a Japanese section header followed by
    // integer line IDs and one or two language columns. Non-numeric rows
    // remain author annotations; ambiguous headerless pages stay excluded.
    if(/^maps\/map_\d+\/event_\d+\/page_\d+\.csv$/.test(name)&&
       (h.length===2||h.length===3)&&isJapanese(h[0])&&h.slice(1).every(function(v){return !v.trim();})&&
       rows.slice(1).some(function(r){return /^\d+$/.test(r[0]||"")&&isJapanese(r[1]||"");}))
        return {type:"numeric",start:1,width:h.length,groups:[[1,h.length===3?2:-1,-1]]};
    // Explicit legacy display layouts, only if filename and field
    // signatures agree. Numeric IDs, switches and asset names stay intact.
    if(name==="db_npcjob.csv"&&h.length===3&&h.every(function(v){return !v.trim();})&&
       rows[1]&&/^\d+$/.test(rows[1][0]))
        return {type:"numeric",start:1,width:3,groups:[[1,2,-1]]};
    if(name==="status.csv"&&h.length===3&&h[0]==="species"&&isJapanese(h[1])&&/^Species\s*:/i.test(h[2]))
        return {type:"generic",id:0,start:0,width:3,groups:[[1,2,-1]]};
    if(name==="npc/npc_misc.csv"&&h.length===3&&h[0]==="基本情報"&&h[1]==="Personal Information")
        return {type:"generic",id:0,start:0,width:3,groups:[[0,1,-1]]};
    if(name==="window_ero_status_simple.csv"&&h.length===2&&/^\d+$/.test(h[0])&&
       rows.every(function(row){return row.length===2&&(!row[0]||/^\d+$/.test(row[0]));}))
        return {type:"numeric",start:0,width:2,groups:[[-1,1,-1]]};
    if(name==="profile.csv"&&h.length===5&&h[0]==="Empty"&&h[1]==="0"&&h.slice(2).every(function(v){return !v.trim();}))
        return {type:"profile",start:1,width:5,groups:[[2,3,-1]]};
    if(/^(?:db_actor|db_enemy)\.csv$/.test(name)&&h.length===10&&h[0]==="$id=0"&&
       h[1]==="JPN_NAME"&&h[4]==="ENG_NAME"&&h[7]==="SPN_NAME"&&h[3]===h[6]&&h[6]===h[9]&&h[3]==="desc")
        return {type:"db",start:1,width:10,groups:[[3,6,9]]}; // descriptions only, never names
    // Only explicitly identified translation columns in other tables.
    // Exclude database IDs, developer variable names, raw maps, assets and
    // headerless/private profile data whose meaning is not established.
    if(/^(?:db_|maps\/|npc\/)/.test(name))return null;
    var lower=h.map(function(v){return v.trim().toLowerCase();}),id=lower.indexOf("key");
    if(id<0)id=lower.indexOf("id");
    var j=lower.indexOf("jp");if(j<0)j=lower.indexOf("ja");if(j<0)j=lower.indexOf("japanese");
    var e=lower.indexOf("en");if(e<0)e=lower.indexOf("english");
    var z=lower.indexOf("es");if(z<0)z=lower.indexOf("spanish");
    if(id<0||(j<0&&e<0))return null;
    return {type:"generic",id:id,start:1,width:h.length,groups:[[j,e,z]]};
}
function scanRootCsvFile(relative,raw,done){
    var rows=csvRows(raw.replace(/^\uFEFF/,"")),schema=rows&&rootCsvSchema(relative,rows);
    if(!schema){tableStats.rootSkipped++;scanStats.skipped++;done();return;}
    var at=schema.start,openText=false,mapId=0;
    var startMap=Number((initialMapFile.match(/\d+/)||["0"])[0]);
    function slice(){
        var end=Math.min(at+150,rows.length);
        for(;at<end;at++){
            var r=rows[at];csvUiStats.rows++;
            if(r.length!==schema.width)continue;
            var key=(r[0]||"").trim(),priority=schema.type!=="sheet"&&schema.type!=="numeric";
            if(schema.type==="sheet"){
                var m=/^\$map(\d+)$/.exec(key);
                if(m)mapId=Number(m[1]);
                if(key)openText=/^\$text\d+$/.test(key);
                if(!openText)continue;
                priority=(relative.toLowerCase()==="commonsheet.csv"||mapId===startMap);
            }else if(schema.type==="db"&&!/^\$id=[1-9]\d*$/.test(key))continue;
            else if(schema.type==="quest"&&!/^\$quest_id=[1-9]\d*$/.test(key))continue;
            else if(schema.type==="numeric"&&!/^\d+$/.test(key))continue;
            else if(schema.type==="npc"&&(!/^\d+$/.test(r[1])||!/^\d+$/.test(r[2])))continue;
            else if(schema.type==="log"&&(!key||!/^[A-Za-z0-9_.\/ ?\-]{1,120}$/.test(key)||/(?:^|\/)\.\.(?:\/|$)/.test(key)))continue;
            else if(schema.type==="profile"&&(!/^[A-Za-z0-9_.-]+$/.test(key)||!/^\d+$/.test(r[1])))continue;
            else if(schema.type==="generic"&&!r[schema.id])continue;
            schema.groups.forEach(function(g){
                var jp=r[g[0]],en=r[g[1]],es=r[g[2]];
                // Quest progress contains assignment keys. Inventory only
                // matching display values, never the assignment itself.
                if(schema.type==="quest"&&g[0]===10){
                    function progress(v){
                        var out=Object.create(null),id=null;
                        String(v||"").replace(/\r\n/g,"\n").split("\n").forEach(function(line){
                            var m=/^\s*\$progress(\d+)\s*=\s*(.*)$/.exec(line);
                            if(m){id=m[1];out[id]=m[2];}
                            else if(id!==null&&line.trim()&&!csvExecutableSyntax(line)&&!/^\s*\$/.test(line))out[id]+="\n"+line;
                            else if(line.trim())id=null;
                        });return out;
                    }
                    var a=progress(jp),b=progress(en),c=progress(es);
                    var ids=Object.keys(a).concat(Object.keys(b).filter(function(k){return !Object.prototype.hasOwnProperty.call(a,k);}));
                    ids.forEach(function(k){csvRegisterPair(a[k],b[k],c[k],priority,true);});
                }else csvRegisterPair(jp,en,es,priority,schema.type==="sheet"&&/^\$text\d+$/.test(key)||schema.type!=="sheet");
            });
        }
        nextPrefetch();
        if(at<rows.length){setTimeout(slice,0);return;}
        tableStats.files++;tableStats.rootFiles++;scanStats.files++;done();
    }
    slice();
}
function scanRootCsv(done){
    if(!tableStats.root){done();return;}
    var base=path.join(content,"csv"),dirs=[{path:base,depth:0}],dirAt=0,tasks=[],taskAt=0;
    function enumerate(){
        if(dirAt>=dirs.length){
            tableStats.rootTotal=tasks.length;scanStats.totalFiles+=tasks.length;
            // Main narrative and common events before generic databases.
            function order(v){
                var n=v.relative.toLowerCase();
                if(/^(?:erowindowtext|questlist|profile|status|db_class|db_actor|db_skill|db_npcjob)\.csv$/.test(n))return 0;
                if(n==="logsheet.csv")return 1;
                if(n==="commonsheet.csv")return 2;
                if(n==="sheet.csv")return 3;
                return 4;
            }
            tasks.sort(function(a,b){return order(a)-order(b)||a.relative.localeCompare(b.relative);});
            taskAt=0;next();return;
        }
        var d=dirs[dirAt++];
        fs.readdir(d.path,function(err,names){
            if(err){scanStats.skipped++;tableStats.rootSkipped++;enumerate();return;}
            names.sort().forEach(function(n){
                if(!/^[A-Za-z0-9_.-]{1,100}$/.test(n)||n==="."||n==="..")return;
                var full=path.join(d.path,n);
                if(/\.csv$/i.test(n)&&regularUnder(base,full,16*1024*1024))
                    tasks.push({file:full,relative:path.relative(base,full).replace(/\\/g,"/")});
                else if(directoryUnder(base,full))dirs.push({path:full,depth:d.depth+1});
            });
            enumerate();
        });
    }
    function next(){
        if(taskAt>=tasks.length){
            tableStats.rootDone=true;done();return;
        }
        var task=tasks[taskAt++];
        fs.readFile(task.file,"utf8",function(err,raw){
            if(err||typeof raw!=="string"||raw.indexOf("\uFFFD")>=0){scanStats.skipped++;tableStats.rootSkipped++;next();return;}
            try{scanRootCsvFile(task.relative,raw,next);}catch(_){scanStats.skipped++;tableStats.rootSkipped++;next();}
        });
    }
    enumerate();
}
// CSV choices may be generated directly by a custom script. Update ONLY a
// visible command's display label, never its index, enabled flag, callback,
// ext, symbol or $gameMessage. Native layout/selection remains authoritative.
function hookCsvChoiceLabels(){
    if(typeof Window_ChoiceList==="undefined"||!Window_ChoiceList.prototype)return;
    var p=Window_ChoiceList.prototype,update=p.update;
    function display(win,index,fn,args){
        var item=win._list&&win._list[index],raw=item&&item.name,translated=null;
        if(!inputFormActive()&&(csvWindowEligible(win)||csvWindowChoice(win))&&typeof raw==="string"){
            try{translated=choiceDisplay(win,raw,true);}catch(_){state.errors++;}
        }
        if(translated===null||translated===raw)return fn.apply(win,args);
        // Only the duration of the original paint/measure call. A script
        // reading the choice later sees its original name and ext.
        var out;
        item.name=translated;
        try{out=fn.apply(win,args);}
        finally{if(item.name===translated)item.name=raw;}
        (win._iaCsvPaint||(win._iaCsvPaint=[]))[index]={item:item,raw:raw,shown:translated};
        csvUiStats.choices++;return out;
    }
    if(typeof p.drawItem==="function"){
        var draw=p.drawItem;
        p.drawItem=function(index){return display(this,index,draw,arguments);};
    }
    var measureMethod=isMZ?"textSizeEx":"textWidthEx";
    if(typeof p[measureMethod]==="function"){
        var measure=p[measureMethod];
        p[measureMethod]=function(text){
            var args=Array.prototype.slice.call(arguments);
            if(!inputFormActive()&&(csvWindowEligible(this)||csvWindowChoice(this)))try{
                var out=choiceDisplay(this,text,true);if(out!==null)args[0]=out;
            }catch(_){state.errors++;}
            return measure.apply(this,args);
        };
    }
    // A subclass may override the conversion itself.
    hookSurfaceConversion(p,true);
    if(typeof update!=="function")return;
    p.update=function(){
        var out=update.apply(this,arguments);
        if(inputFormActive()||!(csvWindowEligible(this)||csvWindowChoice(this))||!this.active||this.openness===0||this._closing||
           !Array.isArray(this._list)||this._list.length>24||typeof this.redrawItem!=="function")return out;
        if((this._iaCsvChoiceTick=(this._iaCsvChoiceTick||0)+1)%4!==0)return out;
        var win=this,needsLayout=false,changes=[];
        try{
            this._list.forEach(function(item,i){
                var original=item&&item.name;
                if(typeof original!=="string")return;
                var translated=choiceDisplay(win,original,true);
                if(translated===null||translated===original)return;
                var last=win._iaCsvPaint&&win._iaCsvPaint[i];
                if(last&&last.item===item&&last.raw===original&&last.shown===translated)return;
                var rect=isMZ&&typeof win.itemLineRect==="function"?win.itemLineRect(i):
                    typeof win.itemRectForText==="function"?win.itemRectForText(i):null;
                if(rect&&mzChoiceWidth(win,translated)>rect.width)needsLayout=true;
                changes.push(i);
            });
            if(needsLayout){
                // Native placement uses translated width, and native paint
                // uses the same original list. Do not refresh the command
                // list, alter the selection, or add another window.
                if(typeof win.updatePlacement==="function"&&typeof win.createContents==="function"&&typeof win.drawAllItems==="function"){
                    win.updatePlacement();win.createContents();win.drawAllItems();
                    csvUiStats.drawn+=changes.length;
                }else csvUiStats.overflow++;
                return out;
            }
            changes.forEach(function(i){
                display(win,i,win.redrawItem,[i]);state.shown++;csvUiStats.drawn++;
            });
        }catch(_){state.errors++;}
        return out;
    };
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
        for(;at<end;at++){
            var row=rows[at],value=row[column];
            if(row.length!==header.length||!row[id]||typeof value!=="string"||/^\s*[=+@]/.test(value))continue;
            if(languageFor(value)){tableStats.candidates++;addPrefetch(value,false);}
        }
        if(at<rows.length){setTimeout(slice,0);return;}
        tableStats.files++;scanStats.files++;done();
    }
    slice();
}
function scanExtraSources(dataDir,done){
    var tasks=[],inkDir=path.join(dataDir,"ink"),localeDir=path.join(dataDir,"localization");
    var hudDir=path.join(dataDir,"plugin"),hudFile=path.join(hudDir,"UltraHUD.json");
    if(ultraHudEnabled()&&directoryUnder(dataDir,hudDir)&&regularUnder(hudDir,hudFile,2*1024*1024))
        tasks.push({file:hudFile,type:"ultra",base:hudDir});
    // main.json is a conventional compiled story, not a source script or
    // test/backup. Additional ambiguous formats are not guessed or executed.
    var main=path.join(inkDir,"main.json");
    if(directoryUnder(dataDir,inkDir)&&regularUnder(inkDir,main,20*1024*1024)){
        inkStats.detected=true;tasks.push({file:main,type:"ink",base:inkDir});
    }
    function run(){
        scanStats.totalFiles+=tasks.length;
        var taskAt=0;
        function next(){
            if(taskAt>=tasks.length){done();return;}
            var t=tasks[taskAt++];
            if(!regularUnder(t.base,t.file,t.type==="ink"?20*1024*1024:2*1024*1024)){
                scanStats.skipped++;setTimeout(next,0);return;
            }
            fs.readFile(t.file,"utf8",function(err,raw){
                if(err||typeof raw!=="string"){scanStats.skipped++;next();return;}
                try{
                    if(t.type==="ink")walkInkStory(JSON.parse(raw.replace(/^\uFEFF/,"")),next);
                    else if(t.type==="ultra"){scanUltraHud(JSON.parse(raw.replace(/^\uFEFF/,"")));next();}
                    else scanLocaleCsv(raw,next);
                }catch(_){scanStats.skipped++;next();}
            });
        }
        next();
    }
    if(directoryUnder(dataDir,localeDir)){
        fs.readdir(localeDir,function(err,names){
            if(!err)names.filter(function(n){return /^[A-Za-z0-9_.\-]{1,100}\.csv$/i.test(n);}).sort().forEach(function(n){
                tasks.push({file:path.join(localeDir,n),type:"csv",base:localeDir});
            });else scanStats.skipped++;
            run();
        });
    }else run();
}

function addPrefetch(text,priority,trustedLang){
    if(typeof text!=="string"||!text||remNativeSpanishText(text)||remNative.detected&&externalLocalizationReference(text))return;
    if(tsvRef(text)){if(priority)tsvPrioritize(text);return;}
    if(tsvExcluded(text))return;
    learnReadings(text);
    var catalogSource=iavra.textSources.has(text)?iavra.textSources.get(text):null;
    var source=authoredDisplay.get(text)||catalogSource||languageFor(text)||displaySource(text,"inventory")||
        (trustedLang==="en"&&/^[A-Za-z][A-Za-z0-9 .,\'!?\-]{0,79}$/.test(text)&&!actorNames[text]?"en":null);
    if(!source)return;
    rememberNameTemplate(source,text);
    var key=source+"\u0000"+text,item=discovered.get(key);
    if(collectInitial&&initialKeys.size<48)initialKeys.set(key,true);
    if(item){
        if(tsv.valid&&item.status==="ready"){
            var audit=tsvEnglishPlan(source,text),prior=cache.get(key);
            if(audit&&tsvCoverageSuspect(text,prior,audit)&&readyText(source,text)===null){
                item.status="queued";scanStats.ready=Math.max(0,scanStats.ready-1);
                item.priority=!!priority;(priority?priorityQueue:prefetchQueue).push(item);
            }
        }
        if(externalTables()&&item.status!=="ready"&&cacheReadDone&&readyText(source,text)!==null){markPrefetchReady(item);return;}
        if(priority&&item.status==="queued"&&!item.priority){
            item.priority=true;priorityQueue.push(item);
        }
        return;
    }
    item={source:source,text:text,status:"queued",priority:!!priority};
    discovered.set(key,item);
    if((!externalTables()||cacheReadDone)&&readyText(source,text)!==null){markPrefetchReady(item);return;}
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
    scanPhoneList(list,priority);
    for(var i=0;i<list.length;i++){
        var cmd=list[i];
        if(!cmd||!Array.isArray(cmd.parameters))continue;
        if(isMZ&&cmd.code===101){protectMZName(cmd.parameters[4]);literalSpeakerLabel(cmd.parameters[4]);continue;}
        // Only registered display fields and verified literal dialects.
        if(isMZ&&(cmd.code===357||cmd.code===355||cmd.code===122)){
            scriptScanCommand(cmd,list[i+1],priority);continue;
        }
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
            for(var j=0;j<parts.length;j++){
                addPrefetch(parts[j],priority);
                var caption=captionEnvelope(parts[j]);
                if(caption)addPrefetch(caption.body,priority,captionSource(caption.body));
            }
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
        if(isMZ){scriptLocale=data.locale||"";scriptSystem=scriptSystemContract(data);if(scriptSystem)displayVariableNames=data.variables;}
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
        if(scriptSystem&&scriptEventContract(data)){
            scriptProfile=true;
            if(prefetchedMap)scanMap(prefetchedMap,true);
        }
        // The CommonEvents file can contain hundreds of thousands of event
        // commands. Its command inventory is processed in small timer slices
        // by scanCommonEventsChunked so JSON parsing does not lead into one
        // more long synchronous walk on the game thread.
        return;
    }
    data.forEach(function(row){
        if(!row||typeof row!=="object")return;
        if(name==="Troops.json"){
            if(Array.isArray(row.pages))row.pages.forEach(function(p){if(p)scanCommands(p.list,false);});
            return;
        }
        if(name==="Actors.json"){
            if(typeof row.name==="string"&&row.name.length<=100)actorNames[row.name]=true;
            if(typeof row.nickname==="string"&&row.nickname.length<=100)actorNames[row.nickname]=true;
            addPrefetch(row.profile,true);scanStatusActor(row);return;
        }
        ["name","description","message1","message2","message3","message4"].forEach(function(k){
            if(typeof row[k]==="string")addPrefetch(row[k],false);
        });
    });
    if(name==="Actors.json")scanVisuQuestParameters();
}
// Parse a large top-level JSON array one entry at a time. JSON.parse(raw)
// would block MV's render/event loop for the full CommonEvents.json file.
// Each entry is still validated by the native JSON parser; only the array
// framing is incremental. The 5 ms / 64 KiB budget gives input and rendering
// a chance to run between slices.
function parseJsonArrayChunked(raw,done){
    if(typeof raw!=="string"){done(null);return;}
    var text=raw.charCodeAt(0)===0xFEFF?raw.slice(1):raw,
        length=text.length,at=0,depth=0,start=-1,items=[],
        inString=false,escaped=false,afterComma=false,opened=false,settled=false;
    function settle(result){if(settled)return;settled=true;done(result);}
    function whitespace(ch){return ch===" "||ch==="\t"||ch==="\r"||ch==="\n";}
    function finishItem(end){
        if(start<0)return false;
        items.push(JSON.parse(text.slice(start,end)));
        start=-1;depth=0;inString=false;escaped=false;afterComma=false;
        return true;
    }
    function complete(){
        while(at<length&&whitespace(text.charAt(at)))at++;
        settle(at===length?items:null);
    }
    function slice(){
        var began=Date.now(),scanned=0;
        try{
            if(!opened){
                while(at<length&&whitespace(text.charAt(at)))at++;
                if(text.charAt(at)!=="["){settle(null);return;}
                opened=true;at++;
            }
            while(at<length&&scanned<65536){
                if((scanned&1023)===0&&Date.now()-began>=5)break;
                var ch=text.charAt(at);
                if(start<0){
                    if(whitespace(ch)){at++;scanned++;continue;}
                    if(ch==="]"){
                        if(afterComma){settle(null);return;}
                        at++;complete();return;
                    }
                    if(ch===","){settle(null);return;}
                    start=at;depth=0;inString=false;escaped=false;afterComma=false;
                }
                if(inString){
                    if(escaped)escaped=false;
                    else if(ch==="\\")escaped=true;
                    else if(ch==='"')inString=false;
                }else if(ch==='"')inString=true;
                else if(ch==="{"||ch==="[")depth++;
                else if(ch==="}"||ch==="]"){
                    if(depth>0)depth--;
                    else if(ch==="]"){
                        if(!finishItem(at)){settle(null);return;}
                        at++;complete();return;
                    }else{settle(null);return;}
                }
                if(ch===","&&!inString&&depth===0){
                    if(!finishItem(at)){settle(null);return;}
                    at++;scanned++;afterComma=true;continue;
                }
                at++;scanned++;
            }
        }catch(_){settle(null);return;}
        if(at<length){setTimeout(slice,0);return;}
        settle(null);
    }
    slice();
}
function scanCommonEventsChunked(data,done){
    if(!Array.isArray(data)){done();return;}
    var deferred=Array.from(commonDeferred.entries()),deferredAt=0,at=0;
    commonDeferred.clear();
    function slice(){
        var started=Date.now(),worked=0;
        try{
            while(deferredAt<deferred.length&&worked<4&&Date.now()-started<5){
                var entry=deferred[deferredAt++];
                priorityCommon(entry[0],entry[1]);worked++;
            }
            while(at<data.length&&worked<12&&Date.now()-started<7){
                var row=data[at++];
                if(row&&typeof row==="object")scanCommands(row.list,false);
                worked++;
            }
        }catch(_){state.errors++;}
        if(deferredAt<deferred.length||at<data.length){
            setTimeout(slice,0);return;
        }
        done();
    }
    slice();
}
function startFullScan(){
    if(scanStarted||!content||(externalTables()&&!cacheReadDone)||(iavra.detected&&!iavra.done))return;
    if(tsv.detected&&!tsv.done){tsvRead(startFullScan);return;}
    scanStarted=true;
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
        scanStats.totalFiles=files.length+(tsv.detected?1:0);
        inkStats.detected=directoryUnder(dataDir,path.join(dataDir,"ink"))&&regularUnder(path.join(dataDir,"ink"),path.join(dataDir,"ink","main.json"),20*1024*1024);
        var fileAt=0;
        function step(){
            if(fileAt>=files.length){
                var finish=function(){scanQuestParameters(function(){scanExtraSources(dataDir,function(){scanStats.done=true;nextPrefetch();});});};
                if(tableStats.root&&!tableStats.rootDone){scanRootCsv(finish);return;}
                finish();return;
            }
            var name=files[fileAt++],file=path.join(dataDir,name);
            try{
                var st=fs.lstatSync(file);
                if(!st.isFile()||st.isSymbolicLink()||st.size>16*1024*1024)
                    throw Error("unsafe or oversized MV data");
            }catch(_){scanStats.skipped++;setTimeout(step,0);return;}
            fs.readFile(file,"utf8",function(err,raw){
                if(err||typeof raw!=="string"){scanStats.skipped++;setTimeout(step,0);return;}
                if(name==="CommonEvents.json"&&!isMZ){
                    scanStats.files++;
                    parseJsonArrayChunked(raw,function(data){
                        if(!Array.isArray(data)){scanStats.skipped++;nextPrefetch();setTimeout(step,0);return;}
                        try{
                            scanDatabase(name,data);
                            scanCommonEventsChunked(data,function(){
                                nextPrefetch();setTimeout(step,0);
                            });
                        }catch(_){
                            scanStats.skipped++;nextPrefetch();setTimeout(step,0);
                        }
                    });
                    return;
                }
                try{
                    var data=JSON.parse(raw.replace(/^\uFEFF/,""));
                    if(name==="System.json"&&data&&integer(data.startMapId)&&data.startMapId>0){
                        var first="Map"+("000"+data.startMapId).slice(-Math.max(3,String(data.startMapId).length))+".json";
                        initialMapFile=first;
                        var p=files.indexOf(first);
                        if(p>=0){
                            files.splice(p,1);
                            var commonIndex=files.indexOf("CommonEvents.json");
                            if(scriptSystemContract(data)&&commonIndex>=0)files.splice(commonIndex+1,0,first);
                            else files.splice(fileAt,0,first);
                        }
                    }
                    scanDatabase(name,data);
                    if(name==="CommonEvents.json"){
                        scanStats.files++;
                        scanCommonEventsChunked(data,function(){
                            nextPrefetch();setTimeout(step,0);
                        });
                        return;
                    }
                    scanStats.files++;
                    if(name==="System.json"&&data)csvPreferred=/^ja(?:[_-]|$)/i.test(data.locale||"")?"ja":"en";
                }catch(_){scanStats.skipped++;}
                nextPrefetch();
                if(name==="System.json"&&tableStats.root&&!tableStats.rootDone){scanRootCsv(function(){setTimeout(step,0);});return;}
                setTimeout(step,0);
            });
        }
        step();
    });
}
function collectMapText(){
    if(typeof $dataMap==="undefined"||!$dataMap||prefetchedMap===$dataMap)return;
    prefetchedMap=$dataMap;scanMap($dataMap,true);nextPrefetch();
}
function markPrefetchReady(item){
    if(!item||item.status==="ready")return;
    if(item.status==="rejected")scanStats.rejected=Math.max(0,scanStats.rejected-1);
    item.status="ready";scanStats.ready++;
}
function markPrefetchRejected(item){
    if(item.status==="ready"||item.status==="rejected")return;
    item.status="rejected";scanStats.rejected++;
}
function deferPrefetch(item,retryAt){
    if(item.status==="ready")return;
    item.status="deferred";
    setTimeout(function(){
        if(item.status!=="deferred")return;
        item.status="queued";(item.priority?priorityQueue:prefetchQueue).push(item);nextPrefetch();
    },Math.min(60000,Math.max(1500,(retryAt||Date.now()+1500)-Date.now()+30)));
}
// A single scheduler survives all native scene transitions. Large projects
// keep foreground text responsive by pausing bulk prefetch while a map or
// battle is active; visible messages still use requestVisible directly.
function activeGameplayScene(){
    var scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
    return !!scene&&(
        (typeof Scene_Map!=="undefined"&&scene instanceof Scene_Map)||
        (typeof Scene_Battle!=="undefined"&&scene instanceof Scene_Battle));
}
function takePriorityPrefetch(){
    while(priorityQueueAt<priorityQueue.length){
        var item=priorityQueue[priorityQueueAt++];
        if(priorityQueueAt>=priorityQueue.length){priorityQueue=[];priorityQueueAt=0;}
        if(item&&item.status==="queued")return item;
    }
    priorityQueue=[];priorityQueueAt=0;return null;
}
function takeBackgroundPrefetch(){
    while(prefetchQueueAt<prefetchQueue.length){
        var item=prefetchQueue[prefetchQueueAt++];
        if(prefetchQueueAt>=prefetchQueue.length){prefetchQueue=[];prefetchQueueAt=0;}
        if(item&&item.status==="queued")return item;
    }
    prefetchQueue=[];prefetchQueueAt=0;return null;
}
function hasQueuedPrefetch(){
    return priorityQueueAt<priorityQueue.length||prefetchQueueAt<prefetchQueue.length;
}
function nextPrefetch(){
    if(prefetchBusy||!state.connected||!cacheReadDone)return;
    var largeInventory=discovered.size>=1200;
    if(largeInventory&&activeGameplayScene())return;
    if(externalTables()&&diskReady&&diskQueue.length>=3000)return;
    if(!hasQueuedPrefetch())return;
    prefetchBusy=true;
    setTimeout(function(){
        var jobs=[];
        function release(){
            prefetchBusy=false;
            setTimeout(nextPrefetch,discovered.size>=1200?120:(state.batch?15:45));
        }
        function failed(item){
            if(item.status==="ready")return;
            state.errors++;item.failures=(item.failures||0)+1;
            if(item.failures<=3)deferPrefetch(item,Date.now()+1500*item.failures);
            else markPrefetchRejected(item);
        }
        try{
            if(!state.connected){release();return;}
            var cap=state.batch?(discovered.size>=1200?1:4):1,budget=256;
            while(jobs.length<cap&&budget--){
                var item=takePriorityPrefetch()||takeBackgroundPrefetch();
                if(!item)break;
                item.status="working";jobs.push(item);
            }
            if(!jobs.length){release();return;}
            Promise.all(jobs.map(function(item){
                // A formatting exception must not leave the queue locked.
                // Only live messages get wire priority over CSV inventory.
                return Promise.resolve().then(function(){
                    var existing=readyText(item.source,item.text);
                    if(existing!==null)return existing;
                    return translatePreservingControls(item.source,item.text,false,externalTables()?false:item.priority);
                }).then(function(out){
                    if(out!==null)markPrefetchReady(item);
                    else if(item.status!=="ready"){
                        var retry=rejectedKeys.get(item.source+"\u0000"+item.text);
                        if(!state.connected||(retry&&retry!==Infinity))deferPrefetch(item,retry);
                        else markPrefetchRejected(item);
                    }
                },function(){failed(item);});
            })).then(release,function(){jobs.forEach(function(item){if(item.status==="working")failed(item);});release();});
        }catch(_){
            jobs.forEach(function(item){if(item.status==="working")failed(item);});release();
        }
    },30);
}
// First-pass preparation is a bounded, optional title-screen wait, never
// a wait inside Game_Interpreter or Window_Message. The title keeps running.
function firstMapProgress(){
    if(externalTables()){
        var complete=(!tableStats.root||tableStats.rootDone)&&(!tsv.detected||tsv.done)&&(!iavra.detected||iavra.done)&&scanStats.done&&cacheReadDone&&
            scanStats.ready+scanStats.rejected>=discovered.size&&!prefetchBusy;
        return {ready:scanStats.ready,finished:scanStats.ready+scanStats.rejected,total:discovered.size,complete:complete};
    }
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
        preferRemNativeSpanish();
        var out=start.apply(this,arguments);
        if(externalTables()){queueFlush();nextPrefetch();}
        if(!runtimeActivated){
            runtimeActivated=true;
            try{startFullScan();refreshConnection();}catch(_){state.errors++;}
        }
        if(tsv.detected)startFullScan();
        return out;
    };
    var launch=proto.commandNewGame,update=proto.update;
    if(typeof launch!=="function"||typeof update!=="function")return;
    function finish(scene){
        var gate=scene._iaStartGate;
        if(!gate)return;
        scene._iaStartGate=null;
        if(externalTables()){queueFlush();nextPrefetch();}
        if(scene._iaTitleProgress&&typeof scene._iaTitleProgress.hide==="function")scene._iaTitleProgress.hide();
        // invoke the original title handler exactly once, with its own arguments
        return launch.apply(scene,gate.args);
    }
    function showPreparation(scene){
        var width=Math.min(720,Graphics.boxWidth||816),x=Math.max(0,Math.floor(((Graphics.boxWidth||816)-width)/2));
        var win=scene._iaTitleProgress;
        if(!win){
            win=isMZ?new Window_Base(new Rectangle(x,8,width,124)):new Window_Base(x,8,width,124);win._iaOwnSurface=true;
            if(!win.contents)win.initialize.apply(win,ownWindowArgs(x,8,width,124));
            scene.addWindow(win);scene._iaTitleProgress=win;
        }
        win.show();win.contents.fontSize=18;return win;
    }
    proto.commandNewGame=function(){
        this._iaTitleMonitor=false;
        if(this._iaStartGate)return finish(this); // explicit second selection skips
        if(this._iaTitleProgress)this._iaTitleProgress.hide();
        // TSV games start immediately; F10 still exposes preparation.
        // The queue belongs to the process, not the title scene.
        if(tsv.detected||remNativeActive()){startFullScan();nextPrefetch();return launch.apply(this,arguments);}
        var info=firstMapProgress();
        if((!tableStats.root&&scanStats.done&&!initialMapFile)||info.complete||!content||
           !this._commandWindow||typeof this._commandWindow.activate!=="function"||
           typeof this.addWindow!=="function"||typeof Window_Base==="undefined")
            return launch.apply(this,arguments);
        try{
            var win=showPreparation(this);
            this._iaStartGate={deadline:Date.now()+25000,args:Array.prototype.slice.call(arguments),last:""};
            this._commandWindow.activate(); // allow pressing New Game again to skip
            win.contents.clear();
            win.drawText((tableStats.root?"Preparando CSV y textos del juego · ":"Preparando textos iniciales · ")+BUILD_ID,0,0,win.contentsWidth(),"center");
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
            if(info.complete||(!tableStats.root&&(scanStats.done&&!initialMapFile||remaining===0))||
               (typeof Input!=="undefined"&&Input.isTriggered("cancel"))){finish(this);return out;}
            var label=tableStats.root?"CSV: "+tableStats.rootFiles+"/"+tableStats.rootTotal+" · Listos: "+info.ready+"/"+info.total+" · Fallos: "+scanStats.rejected:
                "Inicio: "+info.ready+"/"+info.total+" · Total: "+scanStats.ready+"/"+discovered.size+" · "+remaining+" s";
            var win=this._iaTitleProgress;
            if(win&&gate.last!==label){
                gate.last=label;win.contents.clear();
                win.drawText(label,0,0,win.contentsWidth(),"center");
                win.drawText(tableStats.root?"Nueva partida: jugar mientras sigue traduciendo":"Nueva partida otra vez: continuar sin esperar",0,36,win.contentsWidth(),"center");
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
    if(isMZ)IAMini.prototype.updatePadding=function(){this.padding=6;};
    IAMini.prototype.lineHeight=function(){return 26;};
    IAMini.prototype.initialize=function(){
        this._iaOwnSurface=true;Window_Base.prototype.initialize.apply(this,ownWindowArgs(Math.max(0,Graphics.boxWidth-218),7,208,isMZ?this.lineHeight()+12:44));
        this.opacity=190;
        this.contents.fontSize=14;this.contents.outlineWidth=3;
        this.drawText("◆ IA Traductora · F10",0,0,this.contentsWidth(),"center");
    };
    function IAPanel(){this.initialize.apply(this,arguments);}
    IAPanel.prototype=Object.create(Window_Base.prototype);
    IAPanel.prototype.constructor=IAPanel;
    IAPanel.prototype.standardPadding=function(){return 14;};
    if(isMZ)IAPanel.prototype.updatePadding=function(){this.padding=14;};
    IAPanel.prototype.lineHeight=function(){return 38;};
    IAPanel.prototype.initialize=function(){
        var w=Math.min(540,Math.max(310,Graphics.boxWidth-22));
        var h=Math.min(535,Math.max(340,(Graphics.boxHeight||720)-20));
        this._iaOwnSurface=true;Window_Base.prototype.initialize.apply(this,ownWindowArgs(Math.max(5,Graphics.boxWidth-w-10),8,w,h));
        this.opacity=228;this.visible=false;this._tick=0;
        this.contents.fontSize=18;this.contents.outlineWidth=2;
        this.refresh();
    };
    IAPanel.prototype.refresh=function(){
        this.contents.clear();
        this.contents.fontSize=18;
        var lines=[
            "IA Traductora · RPG Maker "+ENGINE_ID,
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
            "Errores: "+state.errors+"   "+(scanStats.skipped?"Archivos omitidos por seguridad":scanStats.done?"Inventario terminado":"Inventario en curso"),
            iavra.detected?"JSON externo: "+iavra.files+" archivos · "+iavra.strings+" textos · "+iavra.shown+" mostrados":
            tsv.detected?"TSV: "+tsv.rows+" · Om.: "+tsv.skippedRows+" · Mostr.: "+tsv.shown+" · Redib.: "+tsv.late:
            tableStats.root?"CSV: "+tableStats.rootFiles+"/"+tableStats.rootTotal+" · Om.: "+tableStats.rootSkipped+" · Opc.: "+csvUiStats.choices:
            (scriptProfile||enabledTextPicture())?"Textos especiales: "+scriptStats.shown+" · Inventario: "+authoredDisplay.size:
            "Misiones: "+questStats.records+" · Redib.: "+lateStats.shown+" · NPC: "+ambientStats.shown+"/"+ambientStats.requested+" · C:"+String(ambientStats.factory||0)
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
        try{protectInputForm();}catch(_){state.errors++;}
        updateScene.apply(this,arguments);
        if(!runtimeActivated){
            runtimeActivated=true;
            try{startFullScan();refreshConnection();}catch(_){state.errors++;}
        }
        try{collectMapText();if(externalTables())nextPrefetch();}catch(_){state.errors++;}
        if(!inputFormActive()&&Input.isTriggered("ia-traductora")&&this._iaPanel){
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
    state.phase="RUTA";initPaths();detectRootCsv();detectTsv();detectIavraLocalization();detectRemNative();
    // Load verified translations asynchronously before map boot; never
    // hold the game's event loop waiting for a cache or neural result.
    loadDisplayMacros();startPersistentCache();
    state.phase="NUCLEO";
    if(engineAt(content)!==ENGINE_ID)throw Error("IA_NUCLEO_RPG_NO_ENCONTRADO");
    state.phase="MENSAJES";hookMessages();
    state.phase="OPCIONES";hookChoices();
    hookChoiceFirstView();hookCsvChoiceLabels();
    state.phase="INTERFAZ";hookInputForm();
    hookBuiltinNameInputScene();hookNativeSurface();hookAuthoredMZ();hookRemNative();hookTitleStart();
    state.phase="CONEXION";loadIavraCatalogs(function(){startFullScan();nextPrefetch();});startFullScan();refreshConnection();setInterval(function(){
        if(!state.connected||Date.now()-lastStatusProbe>=4500)refreshConnection();
        // Independent of title, menu, map or a closed F10 panel.
        if(runtimeActivated)try{startFullScan();collectMapText();}catch(_){state.errors++;}
        queueFlush();nextPrefetch();
    },750);
    state.phase="ACTIVO";
}catch(_){
    // Show a safe *stage* code instead of a generic exception or private path.
    state.status="IA_INICIO_"+state.phase+"_FALLIDO";
    state.errors++;
}
if(typeof window!=="undefined"&&window.__IA_TRADUCTORA_TEST_HOOKS__===true){
    // Opt-in test-only probes; ordinary game sessions never receive this object.
    window.__IA_TRADUCTORA_TEST__={
        inventorySize:function(){return discovered.size;},
        has:function(source,text){return discovered.has(source+"\u0000"+text);},
        done:function(){return scanStats.done;},
        limited:function(){return scanStats.limited;}
    };
}
})();
