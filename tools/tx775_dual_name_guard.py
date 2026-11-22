#!/usr/bin/env python3
"""TX775: two original V95 filters must preserve native speaker tags.

Only patches a pinned, private-source temporary Windows Actions checkout.
No model, game, private source or translation contents are copied to Git.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess

SOURCE_SHA="aeb9ff9326e418fbabe2d53dff7891f4fb340c37"
TARGET=Path("reference/tx331-clean-product-host/rpg_live_plugin/versions/tx757-patched-template.js")
HAS_START="    function hasUntranslatedJapanese(original, candidate) {"
HAS_END="    function sentencePieces(line) {"
OLD_HAS="containsJapanese(original) && containsJapanese(candidate)"
VALID_START="    function valid(source, candidate) {"
OLD_VALID="jp(candidate) || candidate.length > 8000"
JP_COUNT='var jpCount=(source.replace(controlPattern,"").match('
CONTROL=re.compile(r"\\N<[^>\r\n]{1,128}>")
JAPANESE=re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")

CORE_HELPER=r'''    // TX775: preserve only an unchanged native speaker-name control.
    // A Japanese glyph in the spoken body remains a rejected result.
    function japaneseOutsideNativeSpeaker(source, candidate) {
        if (typeof source !== "string" || typeof candidate !== "string") return true;
        var actorTag=/\\N<[^>\r\n]{1,128}>/g;
        var oldNames=source.match(actorTag)||[];
        var newNames=candidate.match(actorTag)||[];
        if (oldNames.length!==newNames.length) return true;
        for (var i=0;i<oldNames.length;i++) {
            if (oldNames[i]!==newNames[i]) return true;
        }
        var originalProse=source.replace(actorTag,"");
        var translatedProse=candidate.replace(actorTag,"");
        if (!originalProse.trim() || !translatedProse.trim()) return true;
        return jp(translatedProse);
    }
'''
HAS_JS=r'''    // TX775: native Japanese actor metadata can coexist with Spanish prose.
    // Never accept Japanese in the body or changed/removed actor controls.
    function hasUntranslatedJapanese(original, candidate) {
        if (typeof candidate !== "string" || typeof original !== "string") return true;
        var actorTag=/\\N<[^>\r\n]{1,128}>/g;
        var oldNames=original.match(actorTag)||[];
        var newNames=candidate.match(actorTag)||[];
        if (oldNames.length!==newNames.length) return true;
        for (var i=0;i<oldNames.length;i++) {
            if (oldNames[i]!==newNames[i]) return true;
        }
        if (!containsJapanese(original)) return false;
        var oldProse=original.replace(actorTag,"");
        var newProse=candidate.replace(actorTag,"");
        if (!oldProse.trim() || !newProse.trim()) return true;
        return containsJapanese(newProse);
    }
'''

def transform(source: str)->str:
    if source.count(HAS_START)!=1 or source.count(HAS_END)!=1:
        raise RuntimeError("TX775_NATIVE_SECOND_GUARD_ANCHOR_CHANGED")
    before,rest=source.split(HAS_START,1)
    older,after=rest.split(HAS_END,1)
    if older.count(OLD_HAS)!=1 or "TX706" not in older or len(older)>3500:
        raise RuntimeError("TX775_UNRECOGNIZED_JAPANESE_PROSE_GUARD")
    source=before+HAS_JS+HAS_END+after
    for anchor in (VALID_START,OLD_VALID,JP_COUNT):
        if source.count(anchor)!=1:
            raise RuntimeError("TX775_SOURCE_CORE_ANCHOR_CHANGED")
    source=source.replace(VALID_START,CORE_HELPER+VALID_START)
    source=source.replace(OLD_VALID,"japaneseOutsideNativeSpeaker(source,candidate) || candidate.length > 8000")
    source=source.replace(JP_COUNT,'var jpCount=(source.replace(controlPattern,"").replace(/\\\\N<[^>\\r\\n]{1,128}>/g,"").match(')
    if source.count("TX775: native Japanese actor metadata")!=1 or source.count("TX775: preserve only an unchanged native")!=1:
        raise RuntimeError("TX775_PATCH_COUNT_INCONSISTENT")
    return source

def would_reject(source: str,candidate: str)->bool:
    if CONTROL.findall(source)!=CONTROL.findall(candidate):
        return True
    if not JAPANESE.search(source):
        return False
    a,b=CONTROL.sub("",source),CONTROL.sub("",candidate)
    return not bool(a.strip() and b.strip()) or bool(JAPANESE.search(b))

def self_test()->None:
    source=r"\N<隼人 \N[2]>おはようございます。"
    accepted=r"\N<隼人 \N[2]>Buenos días."
    failed=[
        r"\N<隼人 \N[2]>おはようございます。",
        r"\N<夏実 \N[2]>Buenos días.",
        r"\N<隼人 \N[2]>Hola、まだ",
        r"\N<隼人 \N[2]>",
        "Buenos días.",
    ]
    assert not would_reject(source,accepted)
    assert all(would_reject(source,bad) for bad in failed)
    fixture=(
      'function jp(s){return /[\\u3040-\\u30ff\\u3400-\\u9fff]/.test(s);}\n'
      +VALID_START+'\n        // TX721\n        return '+OLD_VALID+';\n    }\n'
      + 'var jpCount=(source.replace(controlPattern,"").match(/[\\u3040-\\u30ff\\u3400-\\u9fff]/g)||[]).length;\n'
      +HAS_START+'\n        // TX706\n        return '+OLD_HAS+';\n    }\n'
      +HAS_END+'\n'
    )
    patched=transform(fixture)
    assert patched.count("TX775: preserve only")==1
    for bad_source in (fixture.replace("TX706","else"),fixture.replace(OLD_VALID,"false")):
        try:transform(bad_source)
        except RuntimeError:pass
        else:raise AssertionError("TX775_SOURCE_PIN_WEAK")
    script=(
       "function containsJapanese(s){return /[\\u3040-\\u30ff\\u3400-\\u9fff]/.test(s);}\n"
       +CORE_HELPER+HAS_JS+"\n"
       + "const src="+json.dumps(source,ensure_ascii=False)+";\n"
       + "const allowed="+json.dumps(accepted,ensure_ascii=False)+";\n"
       + "const invalid="+json.dumps(failed,ensure_ascii=False)+";\n"
       + "if(japaneseOutsideNativeSpeaker(src,allowed)||hasUntranslatedJapanese(src,allowed))process.exit(51);\n"
       + "if(invalid.some(v=>!japaneseOutsideNativeSpeaker(src,v)||!hasUntranslatedJapanese(src,v)))process.exit(52);\n"
       + "if(!japaneseOutsideNativeSpeaker(src,src))process.exit(53);\n"
       + "console.log('TX775_DUAL_JS_NATIVE_NAME_GUARD_PASS');\n"
    )
    result=subprocess.run(["node","-e",script],capture_output=True,text=True,check=False)
    if result.returncode!=0 or "TX775_DUAL_JS_NATIVE_NAME_GUARD_PASS" not in result.stdout:
        raise AssertionError("TX775_NODE_DUAL_GUARD_FAILED")
    print("TX775_SOURCE_FREE_TWO_GUARD_REGRESSION_PASS")

def patch_private_checkout(source_root:Path)->None:
    root=source_root.resolve()
    sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True,
                                stderr=subprocess.DEVNULL).strip()
    if sha!=SOURCE_SHA:raise RuntimeError("TX775_EXACT_PRIVATE_COMMIT_REQUIRED")
    filename=root/TARGET
    if not filename.is_file() or filename.is_symlink():
        raise RuntimeError("TX775_ORIGINAL_PLUGIN_MISSING_OR_LINKED")
    raw=filename.read_text(encoding="utf-8")
    patched=transform(raw)
    filename.write_text(patched,encoding="utf-8")
    print("TX775_BOTH_PRIVATE_V95_GUARDS_APPLIED_TEMPORARILY")

def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--source-root",type=Path)
    args=parser.parse_args()
    if args.self_test:self_test()
    if args.source_root:
        self_test()
        patch_private_checkout(args.source_root)
    if not (args.self_test or args.source_root):
        parser.error("use --self-test or --source-root")
if __name__=="__main__":main()
