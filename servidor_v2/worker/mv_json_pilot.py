"""R44: conservative offline translation of a copied MV starting map.

Only event display lines (401/405) are eligible. Do not run game code,
change scripts/controls/choices or access compiled plugins. The worker
produces a candidate inside its owned journal, not a modified game file.
"""
import hashlib
import json
import re
import stat
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

def display_lines(doc):
    if not isinstance(doc,dict) or not isinstance(doc.get("events"),list):raise error("MAPA_INVALIDO")
    for event in doc["events"]:
        if event is None:continue
        if not isinstance(event,dict) or not isinstance(event.get("pages"),list):raise error("MAPA_INVALIDO")
        for page in event["pages"]:
            if not isinstance(page,dict) or not isinstance(page.get("list"),list):raise error("MAPA_INVALIDO")
            for cmd in page["list"]:
                if not isinstance(cmd,dict):raise error("MAPA_INVALIDO")
                if type(cmd.get("code")) is not int or type(cmd.get("indent")) is not int:raise error("MAPA_INVALIDO")
                if cmd["code"] not in (401,405):continue
                params=cmd.get("parameters")
                if not isinstance(params,list) or len(params)!=1 or not isinstance(params[0],str):raise error("MAPA_INVALIDO")
                yield params

def localize_map(doc,names,resolve,quality):
    planned=[]
    keys={}
    skipped=0
    for params in display_lines(doc):
        p=plan(params[0],names)
        if p is None:
            skipped+=1
            continue
        fresh={(unit[4],unit[2]) for unit in p[1]}-keys.keys()
        if len(keys)+len(fresh)>MAX_UNITS:
            skipped+=1
            continue
        for unit in p[1]:keys[(unit[4],unit[2])]=None
        planned.append((params,p))
    answers,stats=resolve(list(keys))
    changed=0
    rejected=0
    for params,(parts,units) in planned:
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
            params[0]=value
            changed+=1
    return {"translated_lines":changed,"eligible_lines":len(planned),
            "skipped_lines":skipped,"rejected_lines":rejected,"unique_units":len(keys),**stats}

def resolve_local(keys,neural,memory,quality):
    answers={}
    new=0
    hits=0
    for lang in ("en","ja"):
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
        for at in range(0,len(missing),6):
            batch=missing[at:at+6]
            values=neural.translate_many(lang,[k[1] for k,_ in batch])
            if len(values)!=len(batch):raise error("RESPUESTA_INVALIDA")
            for (key,digest_key),out in zip(batch,values):
                if not isinstance(out,str) or FORBIDDEN.search(out) or quality(lang,key[1],out):continue
                if memory.put(digest_key,lang,key[1],out):
                    answers[key]=out
                    new+=1
    return answers,{"new_translations":new,"cache_hits":hits}

def create_new(path,data):
    with path.open("xb") as f:
        f.write(data)
        f.flush()
        import os
        os.fsync(f.fileno())

def run_pilot(game,engine,neural_factory,memory_factory,quality):
    root=Path(game).absolute()
    for p in (root,*root.parents):
        info=p.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400:
            raise error("RUTA_NO_VERIFICADA")
    root=root.resolve(strict=True)
    regular(root/MARKER,4096)
    sidecar=directory(root/"IA Traductora",root)
    local=directory(sidecar/".local",root)
    rpg=directory(local/"Rpg",root)
    expected=directory(rpg/"engine",root)
    if Path(engine).resolve(strict=True)!=expected:raise error("MOTOR_NO_VERIFICADO")
    directory(sidecar/"install",root)
    journal=directory(sidecar/"install"/"mv-json",root)
    request=decode(regular(journal/"request.json",8192))
    if not isinstance(request,dict) or request.get("schema")!=SCHEMA or request.get("content") not in ("www","."):
        raise error("SOLICITUD_INVALIDA")
    name=request.get("map")
    if not isinstance(name,str) or not re.fullmatch(r"Map[0-9]{3,6}\.json",name):raise error("SOLICITUD_INVALIDA")
    content=root if request["content"]=="." else directory(root/"www",root)
    data=directory(content/"data",root)
    system=decode(regular(data/"System.json",MAX_BYTES))
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
    memory=memory_factory(root)
    try:
        neural=neural_factory(expected)
        neural.check_all()
        stats=localize_map(doc,names,lambda keys:resolve_local(keys,neural,memory,quality),quality)
    finally:
        memory.close()
    if stats["translated_lines"]<=0:raise error("SIN_TRADUCCIONES_VALIDAS")
    result=json.dumps(doc,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf8")
    if len(result)>MAX_BYTES:raise error("RESULTADO_EXCESIVO")
    if digest(regular(source_path,MAX_BYTES))!=request["before_sha256"]:raise error("ORIGEN_CAMBIADO")
    create_new(journal/"candidate.json",result)
    report={"schema":SCHEMA,"map":name,"before_sha256":digest(raw),"after_sha256":digest(result),**stats}
    create_new(journal/"report.json",json.dumps(report,ensure_ascii=True,separators=(",",":")).encode("utf8"))
