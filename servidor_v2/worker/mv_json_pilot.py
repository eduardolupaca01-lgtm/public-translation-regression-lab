"""R44: conservative offline translation of a copied MV starting map.

Only event display lines (401/405) and verified native choice labels
(102/402 pairs) are eligible. Do not run game code, change event indices,
scripts, controls, or access compiled plugins. Output is a candidate in
the owned journal, not a modified game file.
"""
import hashlib
import json
import re
import stat
import unicodedata
from pathlib import Path

SCHEMA="ia-mv-json-pilot-v1"
MARKER="IA_COPIA_JSON_INCOMPLETA.txt"
MAX_BYTES=16*1024*1024
MAX_UNITS=256
MAX_TEXT=1800
CONTROL=re.compile(r"(\\(?:[CVNPI]\[\d{1,6}\]|[Gg](?![A-Za-z])|[.!|^$<>{}\\])|\r\n|\r|\n)",re.I)
JAPANESE=re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9d]")
ENGLISH=re.compile(r"\b(?:the|a|an|you|your|me|my|our|we|he|she|they|it|this|that|these|those|i|is|are|was|were|be|been|have|has|had|do|does|did|not|no|can|could|will|would|must|should|of|to|for|from|with|without|and|or|but|in|on|at|by|when|where|what|why|how|here|there|now|please|listen|hear|wait|look|open|close|go|come|remember|want|need|thank|welcome|good|years|ago|before|after|then|once|long|story|world|king|hero)\b",re.I)
SPANISH=re.compile(r"\b(?:usted|ustedes|nosotros|tengo|tienes|tiene|puedes|puede|quiero|gracias|hola|buenos|buenas|ahora|espera|para|porque|pero|del|desde|hacia|sobre|entonces|esto|esta|estas|estos|los|las|que|por|con|una|uno|el|la)\b",re.I)
FORBIDDEN=re.compile(r"[\\<>{}\[\]\x00-\x1f]|%[0-9sdf]|https?:|www\.|[A-Za-z]:[/\\]")

def error(code):
    return ValueError("IA_MV_JSON_"+code)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def strict_object(pairs):
    obj={}
    for key,value in pairs:
        if key in obj:raise error("JSON_DUPLICADO")
        obj[key]=value
    return obj

def decode(raw):
    try:
        return json.loads(raw.decode("utf-8-sig"),object_pairs_hook=strict_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(error("JSON_INVALIDO")))
    except (UnicodeError,ValueError,RecursionError) as exc:
        raise error("JSON_INVALIDO") from exc

def regular(path,limit):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400 or not 0<info.st_size<=limit:
        raise error("ARCHIVO_NO_VERIFICADO")
    with path.open("rb") as f:raw=f.read(limit+1)
    if not raw or len(raw)>limit:raise error("ARCHIVO_NO_VERIFICADO")
    return raw

def directory(path,root):
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400 or not path.resolve(strict=True).is_relative_to(root):
        raise error("RUTA_NO_VERIFICADA")
    return path

def source(text,names):
    if not text or text in names or len(text)>MAX_TEXT or FORBIDDEN.search(text):return None
    if text.endswith(":"):return None
    if JAPANESE.search(text):return "ja"
    if re.search(r"[áéíóúñ¿¡]",text,re.I) or SPANISH.search(text) and not ENGLISH.search(text):return None
    # Do not classify file paths, identifiers, pure labels or proper names
    # as prose. The pilot is deliberately narrower than the live MV hook.
    plain=text.replace("’","'").replace("‘","'").replace("“",'"').replace("”",'"').replace("…","...").replace("–","-").replace("—","-")
    if re.search(r"[^ -~]",plain) or re.fullmatch(r"[A-Za-z0-9_.-]+",plain):return None
    words=re.findall(r"[A-Za-z]+",plain)
    return "en" if len(words)>=2 and ENGLISH.search(plain) else None

def plan(raw,names):
    if not isinstance(raw,str) or not raw or len(raw)>MAX_TEXT:return None
    parts=CONTROL.split(raw)
    units=[]
    for i in range(0,len(parts),2):
        piece=parts[i]
        if FORBIDDEN.search(piece):return None
        body=piece.strip(" \t\u3000")
        lang=source(body,names)
        if lang:
            start=len(piece)-len(piece.lstrip(" \t\u3000"))
            units.append((i,piece[:start],body,piece[start+len(body):],lang))
    return (parts,units) if units else None

def event_lists(doc):
    if not isinstance(doc,dict) or not isinstance(doc.get("events"),list):raise error("MAPA_INVALIDO")
    for event in doc["events"]:
        if event is None:continue
        if not isinstance(event,dict) or not isinstance(event.get("pages"),list):raise error("MAPA_INVALIDO")
        for page in event["pages"]:
            if not isinstance(page,dict) or not isinstance(page.get("list"),list):raise error("MAPA_INVALIDO")
            rows=page["list"]
            for cmd in rows:
                if not isinstance(cmd,dict) or type(cmd.get("code")) is not int or type(cmd.get("indent")) is not int:
                    raise error("MAPA_INVALIDO")
            yield rows

def display_entries(doc):
    for rows in event_lists(doc):
        for cmd in rows:
            if cmd["code"] not in (401,405):continue
            params=cmd.get("parameters")
            if not isinstance(params,list) or len(params)!=1 or not isinstance(params[0],str):raise error("MAPA_INVALIDO")
            yield cmd["code"],params

def display_lines(doc):
    for _,params in display_entries(doc):yield params

# Choice condition plugins can embed executable expressions or tags in a
# label. Only plain, short, single-line labels qualify. If any label or
# branch is not a standard native shape, leave its entire group unchanged.
CHOICE_UNSAFE=re.compile(r"[\\<>{}\[\]()%:\x00-\x1f]|https?://|www\.|(?:\b(?:hide_if|show_if|enable_if|disable_if|en|if)\s*\()")
CHOICE_FIXED={"Yes":"Sí","No":"No","See Intro":"Ver introducción","Skip":"Omitir",
              "Continue":"Continuar","Cancel":"Cancelar","Back":"Volver","Leave":"Salir",
              "Accept":"Aceptar","Decline":"Rechazar","Talk":"Hablar","Wait":"Esperar"}
def plain_choice(value):
    return isinstance(value,str) and 0<len(value)<=180 and value==value.strip() and not CHOICE_UNSAFE.search(value)

def choice_groups(doc):
    for rows in event_lists(doc):
        stack=[]
        for cmd in rows:
            code,indent,params=cmd["code"],cmd["indent"],cmd.get("parameters")
            if code==102:
                while stack and stack[-1]["indent"]>=indent:stack.pop()
                labels=params[0] if isinstance(params,list) and len(params)==5 else None
                valid=(isinstance(labels,list) and 1<=len(labels)<=24 and all(plain_choice(x) for x in labels)
                       and all(type(x) is int for x in params[1:]))
                stack.append({"indent":indent,"labels":labels,"branches":{},"valid":valid})
            elif code in (402,403,404):
                # Do not infer a pairing across an unclosed nested block.
                if not stack or stack[-1]["indent"]!=indent:
                    for group in stack:group["valid"]=False
                    continue
                group=stack[-1]
                if code==402:
                    labels=group["labels"]
                    valid=(group["valid"] and isinstance(params,list) and len(params)==2 and type(params[0]) is int
                           and 0<=params[0]<len(labels) and params[0] not in group["branches"] and params[1]==labels[params[0]])
                    if valid:group["branches"][params[0]]=params
                    else:group["valid"]=False
                elif code==403:
                    if params!=[]:group["valid"]=False
                else:
                    stack.pop()
                    if group["valid"] and params==[] and len(group["branches"])==len(group["labels"]):
                        yield group["labels"],group["branches"]

# A conservative width budget, not the game's font measurement. Native
# line breaks are inserted only at existing spaces, never inside a word
# or escape token. Actual variable/actor substitutions may still be wider.
WRAP_PIXELS=500
def estimated_width(text):
    total=0
    for i,part in enumerate(CONTROL.split(text)):
        if i%2:
            upper=part.upper()
            if upper.startswith(("\\N[","\\P[","\\V[")):total+=160
            elif upper.startswith("\\I["):total+=36
            elif upper=="\\G":total+=80
            elif upper=="\\\\":total+=18
            continue
        for ch in part:
            if unicodedata.combining(ch):continue
            if ch==" ":total+=9
            elif ch in "ilI.,:;!|'’":total+=9
            elif unicodedata.east_asian_width(ch) in ("W","F"):total+=28
            elif ch in "mwMW@%":total+=27
            elif ch.isupper():total+=23
            else:total+=17
    return total

def wrap_display(value):
    lines=re.split(r"(\r\n|\r|\n)",value)
    breaks=0
    warnings=0
    for i in range(0,len(lines),2):
        line=lines[i]
        if estimated_width(line)<=WRAP_PIXELS:continue
        # No character truncation, no artificial spaces in escape codes,
        # and no conversion of the game's original line separators.
        pieces=re.split(r"( +)",line)
        out=pieces[0]
        row=pieces[0]
        for j in range(1,len(pieces),2):
            spaces,word=pieces[j],pieces[j+1]
            if row.strip() and word and estimated_width(row+spaces+word)>WRAP_PIXELS:
                out+="\n"+word;row=word;breaks+=1
            else:
                out+=spaces+word;row+=spaces+word
        if any(estimated_width(x)>WRAP_PIXELS for x in out.split("\n")):warnings+=1
        lines[i]=out
    return "".join(lines),breaks,warnings

def localize_map(doc,names,resolve,quality):
    planned=[]
    keys={}
    skipped=0
    for code,params in display_entries(doc):
        p=plan(params[0],names)
        if p is None:
            skipped+=1
            continue
        fresh={(unit[4],unit[2]) for unit in p[1]}-keys.keys()
        if len(keys)+len(fresh)>MAX_UNITS:
            skipped+=1
            continue
        for unit in p[1]:keys[(unit[4],unit[2])]=None
        planned.append((code,params,p))
    choices=[]
    for labels,branches in choice_groups(doc):
        items=[]
        for at,value in enumerate(labels):
            if value in CHOICE_FIXED:
                items.append((at,CHOICE_FIXED[value],None))
            else:
                lang=source(value,names)
                if lang:items.append((at,None,(lang,value)))
        fresh={key for _,_,key in items if key is not None}-keys.keys()
        if len(keys)+len(fresh)>MAX_UNITS:continue
        for key in fresh:keys[key]=None
        if items:choices.append((labels,branches,items))
    answers,stats=resolve(list(keys))
    changed=0
    rejected=0
    wrapped=0
    added_breaks=0
    fit_warnings=0
    for code,params,(parts,units) in planned:
        output=parts[:]
        valid=True
        for i,lead,body,tail,lang in units:
            translated=answers.get((lang,body))
            if not isinstance(translated,str) or FORBIDDEN.search(translated) or quality(lang,body,translated):
                valid=False
                break
            output[i]=lead+translated.strip(" \t\u3000")+tail
        if not valid:
            rejected+=1
            continue
        value="".join(output)
        if value!=params[0]:
            if code==401:
                value,breaks,warnings=wrap_display(value)
                wrapped+=int(breaks>0);added_breaks+=breaks;fit_warnings+=warnings
            params[0]=value
            changed+=1
    groups=0
    labels_changed=0
    for labels,branches,items in choices:
        updates={}
        for at,fixed,key in items:
            value=fixed if key is None else answers.get(key)
            if not plain_choice(value) or estimated_width(value)>WRAP_PIXELS or (key and quality(key[0],key[1],value)):
                updates=None;break
            if value!=labels[at]:updates[at]=value
        if not updates:continue
        for at,value in updates.items():
            labels[at]=value
            branches[at][1]=value
        groups+=1;labels_changed+=len(updates)
    return {"translated_lines":changed,"eligible_lines":len(planned),
            "skipped_lines":skipped,"rejected_lines":rejected,"unique_units":len(keys),
            "choice_groups":groups,"choice_labels":labels_changed,"wrapped_lines":wrapped,
            "added_breaks":added_breaks,"fit_warnings":fit_warnings,**stats}

def resolve_local(keys,neural,memory,quality,checkpoint=lambda _:None):
    answers={}
    new=0
    hits=0
    for lang in ("en","ja"):
        checkpoint("IA_MV_JSON_FASE_CACHE_"+lang.upper())
        missing=[]
        for key in keys:
            if key[0]!=lang:continue
            text=key[1]
            digest_key=digest((lang+"\0"+text).encode("utf8"))
            found=memory.get(digest_key,lang,text)
            if found is not None and not FORBIDDEN.search(found) and not quality(lang,text,found):
                answers[key]=found
                hits+=1
            else:missing.append((key,digest_key))
        if not missing:continue
        # A small offline batch bounds the native decoder's peak working
        # memory. Persist each accepted result before continuing. The other
        # language's model is not loaded until it actually has missing work.
        try:
            for at in range(0,len(missing),2):
                checkpoint("IA_MV_JSON_FASE_INFERENCIA_"+lang.upper())
                batch=missing[at:at+2]
                values=neural.translate_many(lang,[k[1] for k,_ in batch])
                if len(values)!=len(batch):raise error("RESPUESTA_INVALIDA")
                for (key,digest_key),out in zip(batch,values):
                    if not isinstance(out,str) or FORBIDDEN.search(out) or quality(lang,key[1],out):continue
                    if memory.put(digest_key,lang,key[1],out):
                        answers[key]=out
                        new+=1
        finally:
            release=getattr(neural,"release_pilot_language",None)
            if callable(release):
                checkpoint("IA_MV_JSON_FASE_LIBERAR_"+lang.upper())
                release(lang)
    checkpoint("IA_MV_JSON_FASE_PROYECCION")
    return answers,{"new_translations":new,"cache_hits":hits}

def create_new(path,data):
    with path.open("xb") as f:
        f.write(data)
        f.flush()
        import os
        os.fsync(f.fileno())

def run_pilot(game,engine,neural_factory,memory_factory,quality,checkpoint=lambda _:None,direct=False,runtime_mode="source"):
    checkpoint("IA_MV_JSON_FASE_VALIDAR")
    root=Path(game).absolute()
    for p in (root,*root.parents):
        info=p.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400:
            raise error("RUTA_NO_VERIFICADA")
    root=root.resolve(strict=True)
    if not direct:regular(root/MARKER,4096)
    sidecar=directory(root/"IA Traductora",root)
    local=directory(sidecar/".local",root)
    rpg=directory(local/"Rpg",root)
    expected=directory(rpg/"engine",root)
    if Path(engine).resolve(strict=True)!=expected:raise error("MOTOR_NO_VERIFICADO")
    directory(sidecar/"install",root)
    if direct:
        base=directory(sidecar/"install"/"mv-json-direct",root)
        journal=directory(base/"active",root)
        intent=decode(regular(journal/"intent.json",8192))
        if not isinstance(intent,dict) or intent.get("schema")!="ia-mv-json-direct-v1":
            raise error("SOLICITUD_INVALIDA")
    else:
        journal=directory(sidecar/"install"/"mv-json",root)
    request=decode(regular(journal/"request.json",8192))
    if not isinstance(request,dict) or request.get("schema")!=SCHEMA or request.get("content") not in ("www","."):
        raise error("SOLICITUD_INVALIDA")
    name=request.get("map")
    if not isinstance(name,str) or not re.fullmatch(r"Map[0-9]{3,6}\.json",name):raise error("SOLICITUD_INVALIDA")
    content=root if request["content"]=="." else directory(root/"www",root)
    data=directory(content/"data",root)
    system_raw=regular(data/"System.json",MAX_BYTES)
    if direct and (intent.get("content")!=request["content"] or intent.get("map")!=name or
                   intent.get("map_before_sha256")!=request.get("before_sha256") or
                   intent.get("system_before_sha256")!=digest(system_raw)):
        raise error("ORIGEN_CAMBIADO")
    system=decode(system_raw)
    start=system.get("startMapId") if isinstance(system,dict) else None
    if type(start) is not int or not 1<=start<=999999 or name!="Map%03d.json"%start:
        raise error("MAPA_INICIAL_INVALIDO")
    source_path=data/name
    raw=regular(source_path,MAX_BYTES)
    if digest(raw)!=request.get("before_sha256"):raise error("ORIGEN_CAMBIADO")
    doc=decode(raw)
    actors=decode(regular(data/"Actors.json",MAX_BYTES))
    if not isinstance(actors,list):raise error("JSON_INVALIDO")
    names={v[field] for v in actors if isinstance(v,dict) for field in ("name","nickname") if isinstance(v.get(field),str)}
    # Validate the complete map before opening the models/cache.
    list(display_lines(doc))
    checkpoint("IA_MV_JSON_FASE_MEMORIA")
    if direct:
        # Existing SQLite files must be ordinary local files; never follow
        # a junction or symlink into another directory during direct mode.
        cache=rpg/"cache"
        if cache.exists() or cache.is_symlink():
            directory(cache,root)
            for name_suffix in ("","-wal","-shm"):
                f=cache/("translation-memory-v2.sqlite3"+name_suffix)
                if f.exists() or f.is_symlink():
                    info=f.lstat()
                    if not stat.S_ISREG(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400:
                        raise error("RUTA_NO_VERIFICADA")
    memory=memory_factory(root)
    try:
        checkpoint("IA_MV_JSON_FASE_TOKENIZADORES")
        neural=neural_factory(expected)
        # Do not eagerly load both CT2 models for a monolingual map.
        # The packaged build still independently verifies both weights.
        checkpoint("IA_MV_JSON_FASE_INVENTARIO")
        stats=localize_map(doc,names,lambda keys:resolve_local(keys,neural,memory,quality,checkpoint),quality)
    finally:
        memory.close()
    if stats["translated_lines"]+stats["choice_labels"]<=0:raise error("SIN_TRADUCCIONES_VALIDAS")
    result=json.dumps(doc,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf8")
    if len(result)>MAX_BYTES:raise error("RESULTADO_EXCESIVO")
    if digest(regular(source_path,MAX_BYTES))!=request["before_sha256"]:raise error("ORIGEN_CAMBIADO")
    checkpoint("IA_MV_JSON_FASE_PUBLICAR")
    create_new(journal/"candidate.json",result)
    import os
    report={"schema":SCHEMA,"map":name,"before_sha256":digest(raw),"after_sha256":digest(result),
            "worker_pid":os.getpid(),"runtime_mode":runtime_mode,**stats}
    create_new(journal/"report.json",json.dumps(report,ensure_ascii=True,separators=(",",":")).encode("utf8"))
