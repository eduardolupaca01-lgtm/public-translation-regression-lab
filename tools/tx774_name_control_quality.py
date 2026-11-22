#!/usr/bin/env python3
"""Source-pinned TX774 correction for protected RPG speaker names.

SQLite diagnosis is read-only and prints NO game text. Patches are permitted
only on an ephemeral checkout of the EXACT approved private source SHA.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
import subprocess

SOURCE_SHA="aeb9ff9326e418fbabe2d53dff7891f4fb340c37"
TARGET=Path("reference/tx331-clean-product-host/rpg_live_plugin/versions/tx757-patched-template.js")
START="    function hasUntranslatedJapanese(original, candidate) {"
END="    function sentencePieces(line) {"
OLD="containsJapanese(original) && containsJapanese(candidate)"
CONTROL=re.compile(r"\\N<[^>\r\n]{1,128}>")
JAPANESE=re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")

JS=r'''    // TX774: unchanged native speaker metadata is NOT untranslated prose.
    // Preserve original actor names, control codes and message event state.
    function hasUntranslatedJapanese(original, candidate) {
        if (typeof candidate !== "string" ||
            !containsJapanese(original) || !containsJapanese(candidate)) return false;
        var nameTag = /\\N<[^>\r\n]{1,128}>/g;
        var oldTags = typeof original === "string" ? original.match(nameTag) || [] : [];
        var newTags = candidate.match(nameTag) || [];
        if (oldTags.length !== newTags.length) return true;
        for (var n=0; n<oldTags.length; n++) {
            if (oldTags[n] !== newTags[n]) return true;
        }
        var oldProse=original.replace(nameTag,"");
        var newProse=candidate.replace(nameTag,"");
        if (!oldProse.trim() || !newProse.trim()) return true;
        return containsJapanese(newProse);
    }
'''

def would_reject(source: str, translated: str) -> bool:
    if not JAPANESE.search(source) or not JAPANESE.search(translated):
        return False
    if CONTROL.findall(source)!=CONTROL.findall(translated):
        return True
    source_prose=CONTROL.sub("",source)
    translated_prose=CONTROL.sub("",translated)
    if not source_prose.strip() or not translated_prose.strip():
        return True
    return bool(JAPANESE.search(translated_prose))

def transform(old: str) -> str:
    if old.count(START)!=1 or old.count(END)!=1:
        raise RuntimeError("TX774_PINNED_NAME_GUARD_ANCHOR_CHANGED")
    before,remainder=old.split(START,1)
    original,after=remainder.split(END,1)
    if original.count(OLD)!=1 or "TX706" not in original or len(original)>3500:
        raise RuntimeError("TX774_ORIGINAL_V95_NAME_GUARD_NOT_RECOGNIZED")
    return before+JS+END+after

def audit_sqlite(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("TX774_SQLITE_FILE_MISSING_OR_UNSAFE")
    db=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)
    result={"schema":"tx774-protected-speaker-audit-v1",
            "done":0,"retry":0,"raw_japanese":0,
            "protected_name_only":0,"outside_name":0,
            "modified_name":0,"no_japanese":0}
    try:
        db.execute("PRAGMA query_only=ON")
        columns={row[1] for row in db.execute("PRAGMA table_info(segments)")}
        if not {"source","target","original","state","translated"}.issubset(columns):
            raise RuntimeError("TX774_UNKNOWN_SQLITE_SCHEMA")
        for lang,tgt,source,state,translated in db.execute(
                "SELECT source,target,original,state,translated FROM segments"):
            if state=="retry":
                result["retry"]+=1
                continue
            if state!="done" or tgt!="es" or lang not in ("ja","en"):
                continue
            result["done"]+=1
            if not isinstance(translated,str) or not JAPANESE.search(translated):
                result["no_japanese"]+=1
                continue
            result["raw_japanese"]+=1
            if CONTROL.findall(source)!=CONTROL.findall(translated):
                result["modified_name"]+=1
            elif JAPANESE.search(CONTROL.sub("",translated)):
                result["outside_name"]+=1
            else:
                result["protected_name_only"]+=1
    finally:
        db.close()
    return result

def self_test() -> None:
    source=r"\N<隼人 \N[2]>おはようございます。"
    accepted=r"\N<隼人 \N[2]>Buenos días."
    failed=[
        r"\N<隼人 \N[2]>おはようございます。",
        r"\N<夏実 \N[2]>Buenos días.",
        r"\N<隼人 \N[2]>Hola、まだ",
        r"\N<隼人 \N[2]>",
    ]
    assert not would_reject(source,accepted)
    assert all(would_reject(source,x) for x in failed)
    fixture=START+"\n        // TX706 original guard\n        return "+OLD+";\n    }\n"+END
    result=transform(fixture)
    assert result.count("var oldTags")==1
    for corruption in (fixture.replace("TX706","older"),fixture.replace(OLD,"false")):
        try: transform(corruption)
        except RuntimeError:pass
        else:raise AssertionError("SOURCE_PIN_GUARD_WEAK")
    test_script=(
        "function containsJapanese(s){return /[\\u3040-\\u30ff\\u3400-\\u9fff]/.test(String(s||''));}\n"
        + JS + "\n"
        + "const src="+json.dumps(source,ensure_ascii=False)+";\n"
        + "const yes="+json.dumps(accepted,ensure_ascii=False)+";\n"
        + "const no="+json.dumps(failed,ensure_ascii=False)+";\n"
        + "if(hasUntranslatedJapanese(src,yes)||no.some(x=>!hasUntranslatedJapanese(src,x)))process.exit(15);\n"
        + "console.log('TX774_JS_NATIVE_SPEAKER_REGRESSION_PASS');\n"
    )
    r=subprocess.run(["node","-e",test_script],text=True,capture_output=True,check=False)
    if r.returncode!=0 or "TX774_JS_NATIVE_SPEAKER_REGRESSION_PASS" not in r.stdout:
        raise AssertionError("TX774_NODE_JS_QUALITY_REGRESSION_HOLD")
    print("TX774_SOURCE_FREE_PROTECTED_NAME_GUARD_PASS")

def patch_exact_checkout(source_root: Path) -> None:
    root=source_root.resolve()
    sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,
                                text=True,stderr=subprocess.DEVNULL).strip()
    if sha!=SOURCE_SHA:
        raise RuntimeError("TX774_PRIVATE_SOURCE_SHA_MISMATCH")
    file=root/TARGET
    if not file.is_file() or file.is_symlink():
        raise RuntimeError("TX774_SOURCE_JS_ABSENT_OR_LINKED")
    original=file.read_text(encoding="utf-8")
    file.write_text(transform(original),encoding="utf-8")
    print("TX774_EPHEMERAL_OWNER_SOURCE_GUARD_PATCHED")

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--audit-sqlite",type=Path)
    p.add_argument("--source-root",type=Path)
    a=p.parse_args()
    if a.self_test:self_test()
    if a.audit_sqlite:print(json.dumps(audit_sqlite(a.audit_sqlite),ensure_ascii=False,indent=2))
    if a.source_root:
        self_test()
        patch_exact_checkout(a.source_root)
    if not (a.self_test or a.audit_sqlite or a.source_root):
        p.error("choose --self-test, --audit-sqlite or --source-root")

if __name__=="__main__":
    main()
