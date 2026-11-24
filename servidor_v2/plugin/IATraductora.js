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
var BUILD_ID="RPG-MVMZ-R4-20261124"; // also checked against the installed package SHA
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
            var lines=data.split("\n"),limit=Math.min(lines.length,externalTables()?300000:100000);
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
        .replace(/[\u2010-\u2015]/g,"-").replace(/\u2026/g,"...").replace(/\u00a0/g," ");
    if(/[áéíóúñ¿¡]/i.test(prose)||/[^\x09\x0a\x0d\x20-\x7e]/.test(prose))return null;
    var words=prose.match(/[A-Za-z']+/g)||[];
    if(words.length<2||prose.trim().length<5)return null;
    if(/\b(?:the|you|your|are|have|this|that|with|where|please|hello|sorry|why|what|when|would|could|should|really|don't|doesn't|isn't|won't|i'm|you're|we're|can't|thank|good|morning|and|of|from|into|there|here|was|were|will|must|he|she|they|their|his|her|my|our|is|i|it|him|himself|herself|ourselves|themselves|says|said|keep|moving|writing|looking|always|typical|absurd|enough|stop|listen|leave|wait|come|get|go|back|ready|look|find|help|give|take|bring|open|close|follow)\b/i.test(prose))return "en";
    return null;
}
// Never send game control sequences (including character names) to OPUS.
var controlRE=/(?:\\|\x1b)[Tt][Ll]\{[^{}\r\n]{1,300}\}|\\(?:[A-Za-z]{1,12}\[[^\]\r\n]{0,120}\]|[A-Za-z]{1,12}<[^>\r\n]{1,120}>|[A-Za-z]{1,12}\b|[{}!.,|^<>$\\])|\x1b(?:[mM]\[[A-Za-z0-9 _\-]{1,60}\]|[A-Za-z]+\[[0-9]{1,8}\]|[{}!.,|^<>$])|%(?:[0-9]{1,3}|[sdf])|\$\{[A-Za-z0-9_]{1,50}\}|\r?\n|<\/?[A-Za-z][A-Za-z0-9 _.,:'"=\/#%+\-]{0,100}>|\([A-Za-z]{1,10}:[^()\r\n]{1,100}\)/g;
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
    if(tsvRef(text)||tsvExcluded(text))return Promise.resolve(null);
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
function isQuestWindow(win){
    if(!win)return false;
    if(hasNativeClass(win,/^Window_Quest(?:Data|Title|List|Category|Info|Detail|Journal|Help|Command)/))return true;
    var scene=typeof SceneManager!=="undefined"?SceneManager._scene:null;
    return !!(scene&&hasNativeClass(scene,/^Scene_Quest/)&&
        (scene._questDataWindow===win||scene._dataWindow===win||scene._descriptionWindow===win));
}
function isQuestTemplate(win,text){
    if(typeof text!=="string"||text.length>16000||!pluginEnabled(/^YEP_QuestJournal$/)||
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
        if(identityDrawDepth||this._iaNameSurface||this._iaOwnSurface||typeof arguments[0]!=="string")
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
        return /^Window_(?:Quest(?:Data|Title|List|Category|Info|Detail|Journal|Help|Command)\w*|Galv(?:Caption|Message|Popup)|(?:Map)?Caption|TimedMessage(?:Popup)?|Popup|Gab(?:Window)?)$/.test(k);
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
                if(surfaceDepth||identityDrawDepth||this._iaOwnSurface||this._iaNameSurface||typeof arguments[0]!=="string")
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
    var update=win.update,shown=displayed.slice(),tick=0,tries=0,finished=false;
    var remaining=inputs.some(function(input,i){return input.source&&shown[i]===input.raw;});
    if(!remaining)return;
    win.update=function(){
        var output=update.apply(this,arguments);
        if(finished||this!==win)return output;
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
            width:b.width,height:b.height,style:style},result:null};
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
function csvNameReady(text){
    var list=csvNameTemplates.get(text.slice(0,8)),answer=null;
    if(!list)return null;
    for(var i=0;i<list.length;i++){
        var t=list[i];
        if(csvActorExpansion(t.text)!==text)continue;
        var result=readyText(t.source,t.text),expanded=result!==null?csvActorExpansion(result):null;
        if(typeof expanded!=="string"||expanded===text)continue;
        if(answer!==null&&answer!==expanded)return null;
        answer=expanded;
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
    // A verified choice surface may also carry a newly generated string.
    // Never use this fallback for arbitrary text in other windows.
    if(!source&&choice)source=languageFor(text);
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
// Engine-specific presentation adapter. Keep the neural/cache/scheduler core shared.
function ownWindowArgs(x,y,w,h){return isMZ?[new Rectangle(x,y,w,h)]:[x,y,w,h];}
function nativeTextColor(win,index){
    if(isMZ&&typeof ColorManager!=="undefined"&&typeof ColorManager.textColor==="function")
        return ColorManager.textColor(index);
    return typeof win.textColor==="function"?win.textColor(index):null;
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
                identityDrawDepth++;
                try{return original.apply(this,arguments);}finally{identityDrawDepth--;}
            };
        });
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
        hookSurfaceConversion(Window_Base.prototype,false);
        ["drawText","drawTextEx"].forEach(function(method){
            var original=Window_Base.prototype[method];
            if(typeof original!=="function")return;
            Window_Base.prototype[method]=function(){
                if(surfaceDepth)return original.apply(this,arguments);
                var args=Array.prototype.slice.call(arguments),identity=!!this._iaNameSurface;
                if(!identity&&!identityDrawDepth&&!this._iaOwnSurface&&typeof args[0]==="string"&&isAmbientWindow(this)){
                    surfaceDepth++;
                    try{return ambientDraw(this,method,args,original);}finally{surfaceDepth--;}
                }
                try{
                    if(typeof args[0]==="string"&&!identityDrawDepth&&!this._iaOwnSurface){
                        if(!identity&&questSurface(this,args[0]))args[0]=questDraw(this,args[0]);
                        else if(!identity&&isAmbientSurface(this,args[0]))args[0]=projectCaption(args[0]);
                        else {var bookLabel=!identity?questCachedLabel(args[0]):null;
                            if(bookLabel===null&&csvWindowEligible(this))bookLabel=csvProjectDisplay(args[0],csvWindowChoice(this),true);
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
        Bitmap.prototype.drawText=function(){
            var args=Array.prototype.slice.call(arguments);
            try{
                if(!identityDrawDepth&&typeof args[0]==="string"&&args[0].length>=2)
                    {var label=questCachedLabel(args[0]);
                     if(label===null)label=csvPlainLabel(args[0]);
                     args[0]=label!==null?label:translatedNativeLabel(args[0],false);}
            }catch(_){state.errors++;}
            var bitmap=this;return withQuestGlyphs(bitmap,args[0],function(){return bitmapDraw.apply(bitmap,args);});
        };
        var measure=Bitmap.prototype.measureTextWidth;
        if(typeof measure==="function")Bitmap.prototype.measureTextWidth=function(text){
            var bitmap=this,args=Array.prototype.slice.call(arguments),label=null;
            try{label=csvPlainLabel(text);}catch(_){}
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
            var r=w.runs[k],c=r.color===null?geometry.style.textColor:nativeTextColor(win,r.color);
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
    if(ticket.pages<=1&&replaceNativeMessage(win,ticket)){state.shown++;lateStats.shown++;if(ticket.tsv){tsv.shown++;tsv.late++;}}
    else lateStats.unsupported++;
}
function hookMessages(){
    if(typeof Window_Message==="undefined"||!Window_Message.prototype)return;
    var proto=Window_Message.prototype,original=proto.startMessage;
    if(typeof original!=="function")return;
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
        var projection=null;
        try{
            if(typeof $gameMessage!=="undefined"&&$gameMessage&&$gameMessage.hasText&&$gameMessage.hasText()){
                var text=$gameMessage.allText(),source=languageFor(text),keys=tsvRawMessage();
                this._iaSourceMessage=text;
                if(tsv.detected&&tsvRef(keys)){
                    var resolved=tsvMessageEntry(keys,text);
                    var locale=resolved?resolved.source:tsvProbeLocale(this);
                    if(locale)tsv.language=locale;
                    tsvPrioritize(keys,true);
                    var localized=locale?tsvTranslatedKeys(keys,locale,true):null;
                    if(localized!==null)projection={message:$gameMessage,raw:text,text:localized,used:false};
                    // Never replace the game's reference array.
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
        finally{tsvProjection=previousProjection;}
        if(projection&&projection.used){state.shown++;tsv.shown++;}
        if(tsv.detected)try{tsvLateTicket(this);}catch(_){state.errors++;}
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
    if(typeof terminate==="function")proto.terminateMessage=function(){hideLate(this);this._iaSourceMessage=null;return terminate.apply(this,arguments);};
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
        if(!Array.isArray(choices)||!choices.length||choices.length>12)
            return original.apply(this,arguments);
        var translated=choices.slice(),changed=false;
        try{
            for(var i=0;i<choices.length;i++){
                if(tsvRef(choices[i])){tsvPrioritize(choices[i],true);continue;}
                var source=languageFor(choices[i]);
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
var prefetchedMap=null,discovered=new Map(),priorityQueue=[],prefetchQueue=[];
var initialMapFile="",initialMapScanned=false,initialKeys=new Map(),collectInitial=false;
var scanStats={files:0,totalFiles:0,ready:0,rejected:0,skipped:0,done:false,limited:false};
var scanStarted=false,prefetchBusy=false,MAX_DISCOVERED=40000;
var inkStats={detected:false,files:0,candidates:0,excluded:0};
var tableStats={files:0,candidates:0,root:false,rootDone:false,rootFiles:0,rootTotal:0,rootSkipped:0,authored:0};

// Explicit localization dialect: data/Languages.tsv with a Key and four
// named language columns. The game's identifiers are never neural input.
var tsv={detected:false,valid:false,done:false,loading:false,rows:0,conflicts:0,shown:0,
    keys:new Map(),display:new Map(),chinese:new Map(),visual:new Map(),priority:new Map(),language:"en",skippedRows:0,late:0,visu:false,probe:null,loose:new Map(),repairs:0};
function externalTables(){return tableStats.root||tsv.detected;}
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
    MAX_DISCOVERED=Math.max(MAX_DISCOVERED,90000);
    MAX_CACHE_ENTRIES=Math.max(MAX_CACHE_ENTRIES,150000);
    CACHE_LIMIT=Math.max(CACHE_LIMIT,128*1024*1024);
}
function tsvCandidate(source,text){
    if(typeof text!=="string"||!text.trim()||text.length>1800||actorNames[text]||
       tsvRef(text)||csvExecutableSyntax(text)||/[\u0000\uFFFD]/.test(text)||
       /^\s*(?:\/\/|[#=$@+]|(?:eval|function|return|var|let|const)\s)/i.test(text)||
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
    return tsvVisualKey(tsvNormal(text).replace(/\\[.|]/g,"").replace(/<\/?wordwrap>/gi,"").replace(/<br>/gi,"\n"));
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
function tsvAdaptNative(visual,result){
    var raw=tsvNormal(visual),out=tsvNormal(result);
    // The author's layout may have consumed or removed timing markers.
    // Do not add a missing pause back after native conversion. Preserve
    // every actual non-layout control and every numeric argument.
    function signature(v){
        return protectedParts(v).filter(function(p){
            return p.locked&&!/^(?:\r?\n|<\/?wordwrap>|<br>)$/i.test(p.value);
        }).map(function(p){return p.value;}).join("\u0002");
    }
    if(!/\\[.|]/.test(raw))out=out.replace(/\\[.|]/g,"");
    if(signature(raw)!==signature(out)||numbersIn(raw)!==numbersIn(out))return null;
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
    var joined=pieces.join("");
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
        var joined=parts.join("");
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
            if(candidate&&tsvSurfaceKey(candidate)===key&&tsvCandidate(source,candidate))matches.push({source:source,text:candidate});
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
        $gameMessage.allText()===t.displayed;
}
function tsvEarlyPaint(win,t){
    var ts=win._textState;
    if(!ts||!t.result||ts.index!==0||ts.rtl||ts.buffer||ts.text!==t.visualOriginal||!tsvTicketCurrent(win,t))return false;
    var result=tsvAdaptNative(ts.text,t.result);
    if(result===null||!nativeRenderParts(result))return false;
    ts.text=result;state.shown++;tsv.shown++;hideLate(win);
    return true;
}
function tsvRefreshTicket(win,t){
    if(!tsvTicketCurrent(win,t))return;
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
        tsv:true,scene:scene,result:null,drawn:false,pages:1,geometry:null};
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
            if(rows.length>(maxRows||25000))return null;
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
    MAX_DISCOVERED=90000;MAX_CACHE_ENTRIES=150000;CACHE_LIMIT=128*1024*1024;
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
    return typeof value==="string"&&(/\b(?:if|en)\s*\(|\$(?:v|s|game\w*|data\w*)\s*[\[(]|\\(?:eval|script)\b/i.test(value)||
        /(?:^|\n)\s*(?:[\w.]+\s*=\s*[^=]|(?:function|var|let|const)\s+[A-Za-z_$])/i.test(value));
}
function csvCandidate(value,declared,allowNote){
    if(typeof value!=="string"||!value.trim()||value.length>1800||actorNames[value]||csvExecutableSyntax(value))return null;
    if((!allowNote&&/^\s*※/.test(value))||/^\s*(?:\/\/|[#=$@+]|(?:if|en|eval|function|return|var|let|const)\s*[\s(])/i.test(value)||
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
    if(csvKnown.size>=250000&&!csvKnown.has(text)){scanStats.limited=true;return;}
    csvKnown.set(text,source);
    var key=csvRenderKey(text);
    if(key&&key!==text){
        csvSetUnique(csvRenderAliases,key,{source:source,text:text},function(a,b){
            return a.source===b.source&&csvRenderKey(a.text)===csvRenderKey(b.text);
        });
    }
    // Profile renderers sometimes resolve one actor-name token before
    // handing a line to Bitmap. Index by a literal prefix, not by name.
    var m=/^([^\\\x1b\r\n]{8,})\\n\[(\d{1,5})\]([^\\\x1b\r\n]*)$/i.exec(text);
    if(m&&csvNameCount<12000){
        var k=m[1].slice(0,8),list=csvNameTemplates.get(k)||[];
        if(list.length<24&&!list.some(function(v){return v.text===text;})){
            list.push({source:source,text:text,id:Number(m[2]),prefix:m[1],suffix:m[3]});
            csvNameTemplates.set(k,list);csvNameCount++;
        }
    }
}
function csvSetUnique(map,key,value,equals){
    if(map.has(key)){
        var old=map.get(key);
        if(old!==null&&!equals(old,value))map.set(key,null);
    }else if(map.size<150000)map.set(key,value);
    else scanStats.limited=true;
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
    var rows=csvRows(raw.replace(/^\uFEFF/,""),100000),schema=rows&&rootCsvSchema(relative,rows);
    if(!schema){tableStats.rootSkipped++;scanStats.skipped++;done();return;}
    var at=schema.start,openText=false,mapId=0;
    var startMap=Number((initialMapFile.match(/\d+/)||["0"])[0]);
    function slice(){
        var end=Math.min(at+150,rows.length);
        for(;at<end&&discovered.size<MAX_DISCOVERED;at++){
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
        if(at<rows.length&&discovered.size<MAX_DISCOVERED){setTimeout(slice,0);return;}
        if(at<rows.length)scanStats.limited=true;
        tableStats.files++;tableStats.rootFiles++;scanStats.files++;done();
    }
    slice();
}
function scanRootCsv(done){
    if(!tableStats.root){done();return;}
    var base=path.join(content,"csv"),dirs=[{path:base,depth:0}],tasks=[];
    function enumerate(){
        if(!dirs.length||tasks.length>=256){
            if(dirs.length||tasks.length>=256)scanStats.limited=true;
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
            next();return;
        }
        var d=dirs.shift();
        fs.readdir(d.path,function(err,names){
            if(err){scanStats.skipped++;tableStats.rootSkipped++;enumerate();return;}
            if(names.length>512)scanStats.limited=true;
            names.sort().slice(0,512).forEach(function(n){
                if(!/^[A-Za-z0-9_.-]{1,100}$/.test(n)||n==="."||n==="..")return;
                var full=path.join(d.path,n);
                if(/\.csv$/i.test(n)&&regularUnder(base,full,16*1024*1024)&&tasks.length<256)
                    tasks.push({file:full,relative:path.relative(base,full).replace(/\\/g,"/")});
                else if(d.depth<4&&directoryUnder(base,full)&&dirs.length<128)dirs.push({path:full,depth:d.depth+1});
            });
            enumerate();
        });
    }
    function next(){
        if(!tasks.length||discovered.size>=MAX_DISCOVERED){
            if(tasks.length)scanStats.limited=true;
            tableStats.rootDone=true;done();return;
        }
        var task=tasks.shift();
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
        if(csvWindowEligible(win)&&typeof raw==="string"){
            try{translated=csvProjectDisplay(raw,true,true);}catch(_){state.errors++;}
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
            if(csvWindowEligible(this))try{
                var out=csvProjectDisplay(text,true,true);if(out!==null)args[0]=out;
            }catch(_){state.errors++;}
            return measure.apply(this,args);
        };
    }
    // A subclass may override the conversion itself.
    hookSurfaceConversion(p,true);
    if(typeof update!=="function")return;
    p.update=function(){
        var out=update.apply(this,arguments);
        if(!csvWindowEligible(this)||!this.active||this.openness===0||this._closing||
           !Array.isArray(this._list)||this._list.length>24||typeof this.redrawItem!=="function")return out;
        if((this._iaCsvChoiceTick=(this._iaCsvChoiceTick||0)+1)%12!==0)return out;
        var win=this,needsLayout=false,changes=[];
        try{
            this._list.forEach(function(item,i){
                var original=item&&item.name;
                if(typeof original!=="string")return;
                var translated=csvProjectDisplay(original,true,true);
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
    if(tsvRef(text)){if(priority)tsvPrioritize(text);return;}
    if(tsvExcluded(text))return;
    learnReadings(text);
    var source=languageFor(text)||(trustedLang==="en"&&/^[A-Za-z][A-Za-z0-9 .,\'!?\-]{0,79}$/.test(text)&&!actorNames[text]?"en":null);
    if(!source)return;
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
    if(discovered.size>=MAX_DISCOVERED){scanStats.limited=true;return;}
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
    for(var i=0;i<list.length;i++){
        var cmd=list[i];
        if(!cmd||!Array.isArray(cmd.parameters))continue;
        if(isMZ&&cmd.code===101){protectMZName(cmd.parameters[4]);continue;}
        // Structured plugin commands may contain executable arguments.
        if(isMZ&&cmd.code===357)continue;
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
    if(scanStarted||!content||(externalTables()&&!cacheReadDone))return;
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
        if(files.length>5000){files=files.slice(0,5000);scanStats.limited=true;}
        function step(){
            if(!files.length||discovered.size>=MAX_DISCOVERED){
                var finish=function(){scanQuestParameters(function(){scanExtraSources(dataDir,function(){scanStats.done=true;nextPrefetch();});});};
                if(tableStats.root&&!tableStats.rootDone){scanRootCsv(finish);return;}
                finish();return;
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
// A single scheduler survives all native scene transitions.
function nextPrefetch(){
    if(prefetchBusy||!state.connected||!cacheReadDone)return;
    if(externalTables()&&diskReady&&diskQueue.length>=3000)return;
    if(!priorityQueue.length&&!prefetchQueue.length)return;
    prefetchBusy=true;
    setTimeout(function(){
        var jobs=[];
        function release(){
            prefetchBusy=false;setTimeout(nextPrefetch,state.batch?15:45);
        }
        function failed(item){
            if(item.status==="ready")return;
            state.errors++;item.failures=(item.failures||0)+1;
            if(item.failures<=3)deferPrefetch(item,Date.now()+1500*item.failures);
            else markPrefetchRejected(item);
        }
        try{
            if(!state.connected){release();return;}
            var cap=state.batch?4:1,budget=256;
            while(jobs.length<cap&&budget--&&(priorityQueue.length||prefetchQueue.length)){
                var item=priorityQueue.length?priorityQueue.shift():prefetchQueue.shift();
                if(item.status!=="queued")continue;
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
        var complete=(!tableStats.root||tableStats.rootDone)&&(!tsv.detected||tsv.done)&&scanStats.done&&cacheReadDone&&
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
        if(tsv.detected){startFullScan();nextPrefetch();return launch.apply(this,arguments);}
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
            "Errores: "+state.errors+"   "+(scanStats.limited?"Límite de escaneo":scanStats.done?"Inventario terminado":"Inventario en curso"),
            tsv.detected?"TSV: "+tsv.rows+" · Om.: "+tsv.skippedRows+" · Mostr.: "+tsv.shown+" · Redib.: "+tsv.late:
            tableStats.root?"CSV: "+tableStats.rootFiles+"/"+tableStats.rootTotal+" · Om.: "+tableStats.rootSkipped+" · Opc.: "+csvUiStats.choices:
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
        updateScene.apply(this,arguments);
        if(!runtimeActivated){
            runtimeActivated=true;
            try{startFullScan();refreshConnection();}catch(_){state.errors++;}
        }
        try{collectMapText();if(externalTables())nextPrefetch();}catch(_){state.errors++;}
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
    state.phase="RUTA";initPaths();detectRootCsv();detectTsv();
    // Load verified translations asynchronously before map boot; never
    // hold the game's event loop waiting for a cache or neural result.
    loadDisplayMacros();startPersistentCache();
    state.phase="NUCLEO";
    if(engineAt(content)!==ENGINE_ID)throw Error("IA_NUCLEO_RPG_NO_ENCONTRADO");
    state.phase="MENSAJES";hookMessages();
    state.phase="OPCIONES";hookChoices();hookCsvChoiceLabels();
    state.phase="INTERFAZ";hookNativeSurface();hookTitleStart();
    state.phase="CONEXION";startFullScan();refreshConnection();setInterval(function(){
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
})();
