#!/usr/bin/env python3
"""IA Traductora, motor neuronal independiente. Sólo 127.0.0.1, sin nube."""
from __future__ import annotations
import argparse, hashlib, json, os, secrets, sys, threading, time
import re, sqlite3, unicodedata
from pathlib import Path
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCHEMA="ia-traductora-bridge-v1"
MAX_TEXT=1800
MODELS={"ja":"opus_ja_es","en":"opus_en_es"}
CACHE_SCHEMA=2

def quality_reason(lang, original, output):
    """Conservative structural checks; semantic adequacy still needs bilingual QA."""
    if not isinstance(output,str) or not output.strip() or output.strip()==original.strip():
        return "IA_QUALITY_UNCHANGED"
    if "\ufffd" in output or "<unk>" in output or "▁" in output or "\x00" in output:
        return "IA_QUALITY_CORRUPT"
    if len(output)>max(120,min(5400,len(original)*5+80)):
        return "IA_QUALITY_LENGTH_EXCESS"
    digits=lambda text:sorted(str(int(unicodedata.normalize("NFKC",x))) for x in
         re.findall(r"[0-9０-９]+",text))
    if digits(original)!=digits(output):
        return "IA_QUALITY_NUMBER_MISSING"
    if lang=="ja" and re.search(r"[\u3041-\u3096\u30a1-\u30fa\u3400-\u9fff\uff66-\uff9d]",output):
        return "IA_QUALITY_JAPANESE_RESIDUAL"
    if lang=="en":
        # The bridge is responsible for native controls, not the model.
        # Reject stale model responses with invented tags and runaway output.
        if re.search(r"[<>]",output) and not re.search(r"[<>]",original):
            return "IA_QUALITY_EN_MARKUP"
        if re.search(r"word\s*wrap|wordwordwrap",output,re.I) and not re.search(r"word\s*wrap",original,re.I):
            return "IA_QUALITY_EN_MARKUP"
        if re.search(r"</?wordwrap>",original,re.I):
            return "IA_QUALITY_EN_CONTROL_INPUT"
        source_words=re.findall(r"[a-zA-Z']+",original)
        words=re.findall(r"[a-záéíóúüñ]+",output.lower())
        if len(output)>max(48,len(original)*2.8+24) or len(words)>max(12,len(source_words)*2.5+6):
            return "IA_QUALITY_EN_LENGTH"
        if any(words[i]==words[i-1]==words[i-2] for i in range(2,len(words))):
            return "IA_QUALITY_REPEATED_GENERATION"
    # A stage direction is not a substitute for dialogue. Use a conservative
    # exact output match, only when the source has no laughter indication.
    if lang=="ja" and re.fullmatch(r"[\s(\[（【「『]*?(?:risas?|jajaja|ja ja ja)[.!…\s]*[)\]）】」』]*",
                                  output.strip(),re.IGNORECASE):
        if not re.search(r"笑|わら|[wｗ]{2,}|(?:あ|は|ふ|へ|え|ひ)[はふへひハフヘヒ]{2,}|ハハ|フフ|へへ|ハッ|フッ",
                         original,re.IGNORECASE):
            return "IA_QUALITY_LAUGHTER_INVENTED"
    # A false stage direction was observed in persisted SQLite results.
    # Do not invalidate genuine applause described by the Japanese source.
    if lang=="ja" and re.fullmatch(r"[\s(\[（【「『]*(?:aplausos?|ovaci[oó]n)[.!…\s]*[)\]）】」』]*",
                                  output.strip(),re.IGNORECASE):
        if not re.search(r"拍手|喝采|パチパチ|ぱちぱち|万雷",original):
            return "IA_QUALITY_APPLAUSE_INVENTED"
    # TX716's bilingual holdout found 早過ぎ -> "too young" rather
    # than "too early". Reject this time-vs-age confusion, not the game.
    if lang=="ja" and re.search(r"(早過ぎ|早すぎ|遅過ぎ|遅すぎ)",original) and re.search(
            r"\b(joven|viejo|edad|niño|niña)\b",output.lower()):
        return "IA_QUALITY_TIME_AGE_CONFUSION"
    if len(original)>30 and original.count("。")+original.count("！")+original.count("？")>=2 and len(output)<12:
        return "IA_QUALITY_MULTICLAUSE_COMPRESSED"
    words=re.findall(r"[a-záéíóúñ]{2,}",output.lower())
    for index in range(5,len(words)):
        if words[index-2:index+1]==words[index-5:index-2]:
            return "IA_QUALITY_REPEATED_GENERATION"
    return None

# The MV bridge separates literal outer delimiters from the neural segment.
# Validate both sides of its cache contract, not the entire rendered message.
def native_quality_reason(lang,original,output):
    reason=quality_reason(lang,original,output)
    if reason:
        return reason
    opening="(（[［【「『《〈〔"
    closing=")）]］】」』》〉〕"
    def edges(value):
        value=value.strip(" \t\u3000")
        left=len(value)-len(value.lstrip(opening))
        right=len(value.rstrip(closing))
        return value[:left],value[right:]
    if lang=="ja" and edges(original)!=edges(output):
        return "IA_QUALITY_NATIVE_DELIMITERS"
    return None

class TranslationMemory:
    """Game-local, crash-durable SQLite; never touches original game data."""
    def __init__(self,game):
        root=game/"IA Traductora"/".local"/"Rpg"
        directory=root/"cache"
        if root.is_symlink() or directory.is_symlink():
            raise RuntimeError("IA_CACHE_RUTA_NO_SEGURA")
        directory.mkdir(mode=0o700,exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError("IA_CACHE_RUTA_NO_SEGURA")
        filename=directory/"translation-memory-v2.sqlite3"
        if filename.is_symlink() or (filename.exists() and not filename.is_file()):
            raise RuntimeError("IA_CACHE_ARCHIVO_AJENO")
        self.db=sqlite3.connect(str(filename),timeout=7,check_same_thread=False)
        self.lock=threading.RLock()
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS translations ("
            "key_sha256 TEXT PRIMARY KEY, schema_version INTEGER NOT NULL,"
            "source TEXT NOT NULL, original TEXT NOT NULL,"
            "translated TEXT NOT NULL, created_unix INTEGER NOT NULL)")
        self.db.commit()
    def get(self,key,lang,text):
        with self.lock:
            row=self.db.execute(
                "SELECT translated FROM translations WHERE key_sha256=? "
                "AND schema_version=? AND source=? AND original=?",
                (key,CACHE_SCHEMA,lang,text)).fetchone()
        return row[0] if row and not native_quality_reason(lang,text,row[0]) else None
    def put(self,key,lang,text,output):
        if native_quality_reason(lang,text,output):
            return False
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO translations "
                "(key_sha256,schema_version,source,original,translated,created_unix) "
                "VALUES (?,?,?,?,?,?)",
                (key,CACHE_SCHEMA,lang,text,output,int(time.time())))
            self.db.commit()
        return True
    def close(self):
        with self.lock:self.db.close()


def decoding_budget(language: str, source_tokens: int) -> int:
    if language == "en":
        return min(144, max(32, source_tokens*3+16))
    return min(300, max(48, source_tokens*3+24))

def manual_source_eos(config, tokenizer):
    """Respect CT2's source boundary contract, independently for each model.

    Converted HF Marian models expect the caller to add the source EOS.
    Native Marian conversions may already add it within CT2. The packaged
    EN model has add_source_eos=false, while JA has true. Never add twice.
    """
    automatic=config.get("add_source_eos")
    if automatic is True:
        return None
    if automatic is not False:
        raise RuntimeError("IA_MODELO_CONFIG_EOS_INVALIDA")
    token=config.get("eos_token")
    if (not isinstance(token,str) or not token or tokenizer.eos_id()<0
            or tokenizer.id_to_piece(tokenizer.eos_id())!=token):
        raise RuntimeError("IA_MODELO_TOKEN_EOS_INVALIDO")
    return token

def encode_source(tokenizer, text, eos=None):
    tokens=list(tokenizer.encode(text,out_type=str))
    if tokens and eos is not None and tokens[-1]!=eos:
        tokens.append(eos)
    return tokens

class NeuralOPUS:
    def __init__(self, engine: Path):
        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as exc:
            raise RuntimeError("IA_DEPENDENCIAS_MODELO_FALTANTES") from exc
        self.ct2 = ctranslate2
        self.models = {}
        self.roots = {}
        self.source_end_tokens = {}
        self.lock = threading.RLock()
        for lang, name in MODELS.items():
            root = engine / "models" / name
            for filename in ("model.bin", "config.json", "source.spm", "target.spm"):
                if not (root / filename).is_file():
                    raise RuntimeError("IA_MODELO_INCOMPLETO")
            # Reading with Python's Windows Unicode path handling avoids
            # passing Japanese game directories to SentencePiece's C++ loader.
            source = spm.SentencePieceProcessor(model_proto=(root / "source.spm").read_bytes())
            target = spm.SentencePieceProcessor(model_proto=(root / "target.spm").read_bytes())
            config=json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.source_end_tokens[lang]=manual_source_eos(config,source)
            self.roots[lang] = root
            self.models[lang] = (None, source, target)

    def _ready(self, lang):
        model, source, target = self.models[lang]
        if model is None:
            root = self.roots[lang]
            content = {}
            for name in (
                "model.bin", "config.json", "shared_vocabulary.json",
                "source_vocabulary.json", "target_vocabulary.json",
                "vocabulary.json",
            ):
                file = root / name
                if file.is_file():
                    # Python reads Unicode paths; CT2 v4.6 loads only bytes
                    # using its documented files= API and ASCII identifier.
                    content[name] = file.read_bytes()
            if "model.bin" not in content or "config.json" not in content:
                raise RuntimeError("IA_MODELO_INCOMPLETO")
            model = self.ct2.Translator("IA_OPUS_" + lang, device="cpu",
                                        compute_type="int8", inter_threads=1,
                                        files=content)
            self.models[lang] = (model, source, target)
        return self.models[lang]

    def check_all(self):
        with self.lock:
            for lang in MODELS:
                self._ready(lang)

    def check_inference(self):
        # This is a genuine neural preflight on neutral test phrases.
        # It runs in --check-models, before the installer is packaged,
        # without reading or seeding any user translation memory.
        samples={"ja":("おはようございます。",r"\b(buenos|buen|días|día|hola)\b"),
                 "en":("Thank you for your help.",r"\b(gracias|agradezco|agradecemos|ayuda|asistencia)\b")}
        for lang,(text,expected) in samples.items():
            result=self.translate(lang,text)
            if native_quality_reason(lang,text,result) or not re.search(expected,result,re.I):
                raise RuntimeError("IA_QUALITY_PREFLIGHT_"+lang.upper())


    def translate_many(self, lang: str, texts: list[str]) -> list[str | None]:
        if not texts or len(texts)>6:
            raise ValueError("IA_LOTE_INVALIDO")
        with self.lock:
            model, source, target = self._ready(lang)
            eos=self.source_end_tokens[lang]
            encoded=[encode_source(source,text,eos) for text in texts]
            if any(not tokens for tokens in encoded):
                raise ValueError("IA_TEXTO_VACIO")
            # Use genuine CT2 batching, preserving the N-best quality
            # checks for each individual source. Never concatenate unrelated
            # dialogue into one model input or one cache key.
            kwargs={"beam_size":4,"num_hypotheses":3,
                    "repetition_penalty":1.12,"no_repeat_ngram_size":3,
                    "max_decoding_length":max(decoding_budget(lang,len(t)) for t in encoded),
                    "batch_type":"tokens","max_batch_size":512}
            results=model.translate_batch(encoded,**kwargs)
            if len(results)!=len(texts):
                raise RuntimeError("IA_LOTE_RESPUESTA_INVALIDA")
            def choose(original,result):
                for hypothesis in result.hypotheses:
                    output=unicodedata.normalize("NFC",target.decode(hypothesis)).strip()
                    if native_quality_reason(lang,original,output) is None:
                        return output
                return None
            answers=[choose(original,result) for original,result in zip(texts,results)]
            # Only failed segments receive a second pass. Accepted
            # results, model files and the usual fast path stay unchanged.
            rejected=[i for i,answer in enumerate(answers) if answer is None]
            if rejected:
                retry_tokens=[encoded[i] for i in rejected]
                retry=dict(kwargs,beam_size=6,num_hypotheses=5,disable_unk=True,
                           repetition_penalty=1.05,
                           max_decoding_length=max(decoding_budget(lang,len(t)) for t in retry_tokens))
                try:
                    alternative=model.translate_batch(retry_tokens,**retry)
                    if len(alternative)==len(rejected):
                        for i,result in zip(rejected,alternative):
                            answers[i]=choose(texts[i],result)
                except (RuntimeError,ValueError):
                    # Keep the first-pass successes even if recovery fails.
                    pass
            # A beam can repeat despite the ordinary N-best search. For
            # rejected English only, try short per-sentence decoding with
            # independent budgets. A fallback must pass the same QA; never
            # accept corrupted or excessively long output just to pass CI.
            if lang=="en":
                for i,answer in enumerate(answers):
                    if answer is not None:
                        continue
                    limit=max(12,min(96,len(encoded[i])*2+8))
                    for beam in (1,3):
                        options=dict(kwargs,beam_size=beam,num_hypotheses=beam,
                                     repetition_penalty=1.2,no_repeat_ngram_size=2,
                                     disable_unk=True,max_decoding_length=limit)
                        try:
                            candidates=model.translate_batch([encoded[i]],**options)
                            if len(candidates)==1:
                                answers[i]=choose(texts[i],candidates[0])
                        except (RuntimeError,ValueError,TypeError):
                            continue
                        if answers[i] is not None:
                            break
            return answers

    def translate(self,lang:str,text:str)->str:
        result=self.translate_many(lang,[text])[0]
        if result is None:
            raise RuntimeError("IA_QUALITY_ALL_CANDIDATES_REJECTED")
        return result

def game_root(exe_root:Path)->tuple[Path,Path]:
    if exe_root.is_symlink():raise ValueError("IA_JUEGO_NO_VALIDO")
    root=exe_root.resolve(strict=True)
    if not root.is_dir():raise ValueError("IA_JUEGO_NO_VALIDO")
    def ordinary(f):
        return f.is_file() and not f.is_symlink()
    layouts=[]
    for folder in (root/"www",root):
        js=folder/"js"
        mv=ordinary(js/"rpg_core.js")
        mz=ordinary(js/"rmmz_core.js")
        if mv and mz:raise ValueError("IA_RPG_RUTAS_AMBIGUAS")
        if not (ordinary(js/"plugins.js") and ordinary(folder/"data"/"System.json")):continue
        if mz:
            if any(not ordinary(js/n) for n in ("rmmz_managers.js","rmmz_objects.js","rmmz_scenes.js","rmmz_windows.js")):
                raise ValueError("IA_RPG_RUTAS_AMBIGUAS")
            if any(d.is_symlink() for d in (folder,js,folder/"data")):
                raise ValueError("IA_RPG_RUTAS_AMBIGUAS")
        if mv or mz:layouts.append(folder)
    if len(layouts)!=1:raise ValueError("IA_SOLAMENTE_RPG_MV_MZ")
    return root,layouts[0]

class Service:
    def __init__(self,game:Path,engine:Path,neural=None):
        self.game,self.content=game_root(game)
        engine=engine.resolve(strict=True)
        if engine.is_symlink() or not engine.is_relative_to(self.game):
            raise ValueError("IA_MOTOR_FUERA_DEL_JUEGO")
        self.engine=engine
        self.neural=neural if neural is not None else NeuralOPUS(engine)
        self.token=secrets.token_hex(32)
        self.translations=0
        self.failures=0
        self.quality_rejected=0
        self.cache=OrderedDict()
        self.lock=threading.Lock()
        self.inference_lock=threading.RLock()
        self.memory=TranslationMemory(self.game)

    def translate(self,lang,text):
        with self.inference_lock:
            return self._translate_one(lang,text)

    def _translate_one(self,lang,text):
        if lang not in MODELS or not isinstance(text,str) or not (0<len(text)<=MAX_TEXT):
            raise ValueError("IA_SOLICITUD_INVALIDA")
        key=hashlib.sha256((lang+"\0"+text).encode()).hexdigest()
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key);return self.cache[key]
        disk=self.memory.get(key,lang,text)
        if disk is not None:
            with self.lock:
                self.cache[key]=disk
                while len(self.cache)>3000:self.cache.popitem(last=False)
            return disk
        try:
            output=self.neural.translate(lang,text)
        except RuntimeError as err:
            if "IA_QUALITY_" in str(err):
                with self.lock:self.quality_rejected+=1
            raise
        reason=native_quality_reason(lang,text,output)
        if reason is not None:
            with self.lock:self.quality_rejected+=1
            raise RuntimeError(reason)
        # No text is called translated until its validated bytes are committed.
        self.memory.put(key,lang,text,output)
        with self.lock:
            self.cache[key]=output
            while len(self.cache)>3000:self.cache.popitem(last=False)
            self.translations+=1
        return output

    def translate_batch(self,lang,texts):
        if lang not in MODELS or not isinstance(texts,list) or not (1<=len(texts)<=6):
            raise ValueError("IA_LOTE_INVALIDO")
        if any(not isinstance(t,str) or not (0<len(t)<=MAX_TEXT) for t in texts):
            raise ValueError("IA_SOLICITUD_INVALIDA")
        with self.inference_lock:
            results={}
            missing=[]
            for text in dict.fromkeys(texts):
                key=hashlib.sha256((lang+"\0"+text).encode()).hexdigest()
                with self.lock:
                    result=self.cache.get(key)
                if result is None:
                    result=self.memory.get(key,lang,text)
                if result is None:
                    missing.append((key,text))
                else:
                    results[text]={"translated":result}
            if missing:
                if hasattr(self.neural,"translate_many"):
                    generated=self.neural.translate_many(lang,[t for _,t in missing])
                else:
                    generated=[]
                    for _,t in missing:
                        try:generated.append(self.neural.translate(lang,t))
                        except RuntimeError as err:
                            if "IA_QUALITY_" not in str(err):raise
                            generated.append(None)
                if len(generated)!=len(missing):raise RuntimeError("IA_LOTE_RESPUESTA_INVALIDA")
                for (key,text),out in zip(missing,generated):
                    reason=native_quality_reason(lang,text,out)
                    if reason:
                        results[text]={"error":reason,"permanent":True}
                        with self.lock:self.quality_rejected+=1
                        continue
                    self.memory.put(key,lang,text,out)
                    with self.lock:
                        self.cache[key]=out
                        while len(self.cache)>3000:self.cache.popitem(last=False)
                        self.translations+=1
                    results[text]={"translated":out}
            # Same order and multiplicity as the requested list.
            return [results[t] for t in texts]

    def close(self):
        self.memory.close()

def make_handler(service:Service):
    class Handler(BaseHTTPRequestHandler):
        server_version="IATraductora/1"
        sys_version=""
        def log_message(self,*_):pass
        def send(self,status,obj):
            body=json.dumps(obj,ensure_ascii=False).encode("utf8")
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def allowed(self):return secrets.compare_digest(self.headers.get("X-IA-Token",""),service.token)
        def do_GET(self):
            if not self.allowed():return self.send(403,{"error":"IA_TOKEN_INVALIDO"})
            if self.path!="/status":return self.send(404,{"error":"IA_RUTA_INVALIDA"})
            self.send(200,{"schema":SCHEMA,"active":True,
                "translated":service.translations,"failed":service.failures,
                "cache":len(service.cache),
                "quality_rejected":service.quality_rejected,"batch":True})
        def do_POST(self):
            if not self.allowed():return self.send(403,{"error":"IA_TOKEN_INVALIDO"})
            if self.path not in ("/translate","/translate_batch"):return self.send(404,{"error":"IA_RUTA_INVALIDA"})
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not (0<length<=(32768 if self.path=="/translate_batch" else 8192)):raise ValueError("IA_TAMANO")
                data=json.loads(self.rfile.read(length).decode("utf8"))
                if not isinstance(data,dict) or data.get("target")!="es":
                    raise ValueError("IA_IDIOMA")
                if self.path=="/translate_batch":
                    results=service.translate_batch(data.get("source"),data.get("texts"))
                    return self.send(200,{"results":results})
                answer=service.translate(data.get("source"),data.get("text"))
                self.send(200,{"translated":answer,"source":data["source"],"target":"es"})
            except (ValueError,UnicodeError):
                self.send(400,{"error":"IA_SOLICITUD_INVALIDA"})
            except Exception as error:
                service.failures+=1
                if isinstance(error,RuntimeError) and "IA_QUALITY_" in str(error):
                    category=str(error)
                    if not re.fullmatch(r"IA_QUALITY_[A-Z0-9_]{1,64}",category):
                        category="IA_QUALITY_RECHAZADA"
                    return self.send(422,{"error":"IA_CALIDAD_RECHAZADA","reason":category,"permanent":True})
                self.send(503,{"error":"IA_MOTOR_FALLO"})
    return Handler

def publish(service,port):
    folder=service.content/"data"/"IATraductora"
    folder.mkdir(exist_ok=True,mode=0o700)
    if folder.is_symlink() or not folder.resolve().is_relative_to(service.game):
        raise RuntimeError("IA_PUENTE_INSEGURO")
    dest=folder/"bridge.json"
    if dest.is_symlink():raise RuntimeError("IA_PUENTE_INSEGURO")
    item={"schema":SCHEMA,"token":service.token,"port":port,
          "pid":os.getpid(),"start_unix":int(time.time())}
    tmp=folder/(".ia-"+secrets.token_hex(12)+".tmp")
    try:
        with tmp.open("x",encoding="utf8") as f:
            json.dump(item,f)
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,dest)
    finally:
        if tmp.exists():tmp.unlink()
    return dest

def monitor_game_lifetime(http, parent_pid):
    """Follow the real Windows process HANDLE so PID reuse is harmless."""
    if os.name != "nt" or parent_pid <= 0:
        return
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.OpenProcess(0x00100000, 0, parent_pid)
    if not handle:
        raise RuntimeError("IA_PARENT_PID_INVALIDO")
    def watch():
        try:
            if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) == 0:
                http.shutdown()
        finally:
            kernel.CloseHandle(handle)
    threading.Thread(target=watch, daemon=True, name="IA-Game-Lifetime").start()

def run(service,parent_pid=0):
    http=ThreadingHTTPServer(("127.0.0.1",0),make_handler(service))
    dest=publish(service,http.server_port)
    try:
        monitor_game_lifetime(http,parent_pid)
        http.serve_forever(poll_interval=0.5)
    finally:
        http.server_close()
        service.close()
        try:
            state=json.loads(dest.read_text("utf8"))
            if state.get("token")==service.token:dest.unlink()
        except (OSError,ValueError):pass

def safe_startup_code(error):
    # Neither a raw exception, a model path nor game dialogue may leave
    # the private worker through this diagnostic.
    raw = str(error).lower()
    if "version" in raw and ("model" in raw or "binary" in raw):
        return "IA_MODELO_VERSION_INCOMPATIBLE"
    if "ia_parent_pid_invalido" in raw:
        return "IA_PARENT_PID_INVALIDO"
    if "ia_cache_" in raw:
        return "IA_CACHE_PERSISTENTE_INACCESIBLE"
    if "ia_modelo_config_eos_invalida" in raw:
        return "IA_MODELO_CONFIG_EOS_INVALIDA"
    if "ia_modelo_token_eos_invalido" in raw:
        return "IA_MODELO_TOKEN_EOS_INVALIDO"
    if "ia_quality_" in raw:
        category=str(error)
        if re.fullmatch(r"IA_QUALITY_[A-Z0-9_]{1,64}",category):
            return category
        return "IA_TRADUCCION_RECHAZADA_POR_CALIDAD"
    if "sentencepiece" in raw or "ctranslate2" in raw:
        return "IA_LIBRERIA_NEURONAL_FALTANTE"
    if "model" in raw and ("path" in raw or "file" in raw):
        return "IA_ARCHIVOS_OPUS_INCOMPLETOS"
    if isinstance(error, (FileNotFoundError, PermissionError, OSError)):
        return "IA_MODELO_INACCESIBLE"
    if "out of memory" in raw or "bad_alloc" in raw:
        return "IA_MEMORIA_INSUFICIENTE"
    return "IA_MOTOR_ERROR_NO_CLASIFICADO"

def write_startup_code(filename, code):
    if filename is None:
        return
    if len(code) > 90 or not code.startswith("IA_"):
        return
    try:
        file = Path(filename)
        if file.is_symlink() or not file.parent.is_dir():
            return
        file.write_text(json.dumps({"schema": "ia-traductora-startup-v1", "code": code})+"\n",
                        encoding="utf8")
    except OSError:
        pass

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--game-root",type=Path)
    p.add_argument("--parent-pid",type=int,default=0)
    p.add_argument("--check-models",action="store_true")
    p.add_argument("--diagnostic-file",type=Path)
    args=p.parse_args()
    engine=Path(sys.executable if getattr(sys,"frozen",False) else __file__).resolve().parent
    try:
        if args.check_models:
            neural = NeuralOPUS(engine)
            neural.check_all()
            neural.check_inference()
            write_startup_code(args.diagnostic_file,"IA_MODELOS_REALES_CT2_LISTOS")
            return
        if args.game_root is None:
            raise ValueError("IA_GAME_ROOT_FALTANTE")
        service=Service(args.game_root,engine)
        write_startup_code(args.diagnostic_file,"IA_MODELOS_CARGADOS_SERVICIO_INICIANDO")
        run(service,args.parent_pid)
    except Exception as exc:
        write_startup_code(args.diagnostic_file,safe_startup_code(exc))
        raise SystemExit(1)

if __name__=="__main__":main()
