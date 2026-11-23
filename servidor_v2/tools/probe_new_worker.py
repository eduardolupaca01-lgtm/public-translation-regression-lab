#!/usr/bin/env python3
"""Prueba BLOQUEANTE del motor propio, nunca imprime texto, tokens o rutas."""
from __future__ import annotations
import argparse,json,re,time
from pathlib import Path
from urllib.request import Request, build_opener,ProxyHandler
from urllib.error import HTTPError

def read_bridge(file):
    if not file.is_file() or file.is_symlink() or file.stat().st_size>4096:return None
    try: d=json.loads(file.read_text("utf8"))
    except (ValueError,OSError):return None
    if (not isinstance(d,dict) or d.get("schema")!="ia-traductora-bridge-v1"
       or type(d.get("port")) is not int or not 1024<=d["port"]<=65535
       or not isinstance(d.get("token"),str) or not re.fullmatch("[0-9a-f]{64}",d["token"])):
        return None
    return d
def call(opener,url,token,object=None):
    data=json.dumps(object,ensure_ascii=False).encode() if object is not None else None
    headers={"X-IA-Token":token,"Accept":"application/json"}
    if data: headers["Content-Type"]="application/json"
    request=Request(url,data=data,headers=headers,method="POST" if data else "GET")
    with opener.open(request,timeout=120 if data else 10) as response:
        if response.status!=200 or "application/json" not in response.headers.get("Content-Type",""):
            raise RuntimeError("IA_HTTP_NO_VALIDADO")
        body=response.read(65537)
        if len(body)>65536: raise RuntimeError("IA_RESPUESTA_EXCESIVA")
    return json.loads(body.decode("utf8"))
def run(game:Path):
    game=game.resolve(strict=True)
    folder=game/"www"/"data"/"IATraductora"
    if not (game/"IA Traductora"/".local"/"Rpg"/"engine"/"IATraductora.exe").is_file():
        raise RuntimeError("IA_MOTOR_PROPIO_FALTANTE")
    opener=build_opener(ProxyHandler({}))
    limit=time.monotonic()+200
    while time.monotonic()<limit:
        d=read_bridge(folder/"bridge.json")
        if d:
            base="http://127.0.0.1:"+str(d["port"])
            try:
                status=call(opener,base+"/status",d["token"])
                if status.get("active") and status.get("schema")=="ia-traductora-bridge-v1":
                    break
            except Exception:
                pass
        time.sleep(.5)
    else:raise RuntimeError("IA_PUENTE_AUTENTICADO_NO_INICIO")
    original="おはようございます。"
    result=call(opener,base+"/translate",d["token"],
                {"source":"ja","target":"es","text":original})
    translated=result.get("translated") if isinstance(result,dict) else None
    if not isinstance(translated,str) or not translated.strip() or translated==original:
        raise RuntimeError("IA_SIN_TRADUCCION_REAL")
    if re.search("[\u3040-\u30ff\u3400-\u9fff\ufffd]",translated):
        raise RuntimeError("IA_SALIDA_NO_ES_ESPANOL")
    if len(translated)>1000:raise RuntimeError("IA_TRADUCCION_NO_ACOTADA")
    print("SERVIDOR_V2_REAL_OPUS_JAPONES_A_ESPANOL_PASS")
    english="Thank you for your help."
    try:
        response=call(opener,base+"/translate",d["token"],
                      {"source":"en","target":"es","text":english})
    except HTTPError as exc:
        if exc.code==503:raise RuntimeError("IA_INGLES_MODELO_HTTP_503") from None
        raise RuntimeError("IA_INGLES_HTTP_RECHAZADO") from None
    except OSError:
        raise RuntimeError("IA_INGLES_CONEXION_INTERRUMPIDA") from None
    translated_en=response.get("translated") if isinstance(response,dict) else None
    if (not isinstance(translated_en,str) or not translated_en.strip()
        or translated_en.casefold().strip()==english.casefold().strip()):
        raise RuntimeError("IA_INGLES_SIN_TRADUCCION_REAL")
    if re.search("[\\u3040-\\u30ff\\u3400-\\u9fff\\ufffd]",translated_en):
        raise RuntimeError("IA_INGLES_IDIOMA_INCORRECTO")
    if len(translated_en)>1000:raise RuntimeError("IA_INGLES_TRADUCCION_NO_ACOTADA")
    print("SERVIDOR_V2_REAL_OPUS_INGLES_A_ESPANOL_PASS")
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--game-root",type=Path,required=True)
    args=parser.parse_args()
    try:run(args.game_root)
    except Exception as e:
        message=str(e)
        if not re.fullmatch(r"IA_[A-Z0-9_]+",message):message="IA_PROBE_FALLO_RESERVADO"
        print(message)
        raise SystemExit(1)
