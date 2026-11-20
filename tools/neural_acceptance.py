"""Real neural Japanese-to-Spanish acceptance using public Argos models.

This runner does NOT load, embed, inspect, or redistribute any private assets.
Public model packages are downloaded only in temporary CI storage. Separate
processes perform inference and SQLite-only recovery.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import time

from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import TranslationRejected, translate_checked


@dataclass(frozen=True)
class Case:
    id: str
    japanese: str
    required_groups: tuple[tuple[str, ...], ...] = ()
    glossary: tuple[tuple[str, str], ...] = ()


# Original, synthetic analogues of the failure patterns. No game text or model
# weights are copied to this public test repository.
CASES: tuple[Case, ...] = (
    Case("greeting", "太郎、おはよう！今日は遅刻しなかったね。",
         (("buen", "hola"), ("tarde", "retras", "puntual", "tiempo", "llegad"))),
    Case("weather", "今日はいい天気ですね。",
         (("tiempo", "clima", "buen", "día", "sol"),)),
    Case("gratitude", "ありがとうございます。", (("gracias", "agradec"),)),
    Case("question", "学校はどこですか？",
         (("escuela", "colegio"), ("dónde", "donde"))),
    Case("club", "今日からクラブ活動が再開します。うれしいです！",
         (("club", "actividades"), ("reanuda", "recomienza", "reinicia", "vuelve", "regresa", "nuevo"))),
    Case("morning_evening", "夏の授業は午前中に終わります。夕方に図書館へ行きます。",
         (("mañana",), ("tarde", "atardecer"), ("biblioteca",))),
    Case("sports", "私はサッカー部にいます。友人は水泳部です。私たちの学校はサッカーが盛んです。水泳部には新しい先生が来ました。",
         (("fútbol", "futbol"), ("natación",), ("escuela", "colegio"), ("nuev", "reciente"))),
    Case("preparation", "早く準備しないと、友人に怒られます。",
         (("prepar", "list", "rápido", "pronto"), ("enfad", "enoj", "molest", "furios", "ira"))),
    Case("childhood", "花子は私の幼なじみです。家が隣にあります。小学生のころから友達です。",
         (("hanako",), ("infancia", "niñ", "primaria"), ("casa", "vecin", "lado")),
         (("花子", "Hanako"),)),
    Case("waking", "もう朝です。起きましょう。",
         (("mañana", "día"), ("despiert", "levant", "levanta"))),
    Case("numbers_and_code", r"\V[12]の予定は12時30分です。",
         (("12",), ("30",))),
    Case("line_breaks", "学校に行きます。\r\n明日は休みです。",
         (("escuela", "colegio"), ("mañana",))),
)


def _semantic_missing(spanish: str, required: tuple[tuple[str, ...], ...]) -> list[list[str]]:
    folded = spanish.casefold()
    return [list(group) for group in required
            if not any(option.casefold() in folded for option in group)]


def _create_models():
    # Delayed import is crucial: the independent restart check does not import
    # Argos or load model weights; it reads persisted SQLite rows only.
    import argostranslate.package as package
    import argostranslate.translate as translation

    package.update_package_index()
    catalog = package.get_available_packages()
    provenance = []
    for source, target in (("ja", "en"), ("en", "es")):
        candidates = [item for item in catalog
                      if item.from_code == source and item.to_code == target]
        if len(candidates) != 1:
            raise RuntimeError("ARGOS_MODEL_ROUTE_NOT_UNIQUE_OR_MISSING:" + source + "_" + target)
        item = candidates[0]
        if not any(str(link).startswith("https://argos-net.com/") for link in item.links):
            raise RuntimeError("ARGOS_MODEL_SOURCE_NOT_OFFICIAL:" + source + "_" + target)
        downloaded = item.download()
        package.install_from_path(downloaded)
        provenance.append({"direction": source + "_" + target,
                           "package_version": item.package_version,
                           "catalog_url": "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json",
                           "download_domains": ["argos-net.com"]})
    ja = translation.get_language_from_code("ja")
    en = translation.get_language_from_code("en")
    es = translation.get_language_from_code("es")
    if not ja or not en or not es or not ja.get_translation(en) or not en.get_translation(es):
        raise RuntimeError("ARGOS_REQUIRED_EXPLICIT_TWO_STAGE_ROUTES_NOT_INSTALLED")
    return translation, provenance


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def translate_phase(workspace: Path) -> int:
    if workspace.exists():
        raise RuntimeError("ACCEPTANCE_WORKSPACE_MUST_BE_NEW")
    workspace.mkdir(parents=True)
    report_path = workspace / "neural-report.json"
    report = {
        "schema": "public-real-neural-ja-en-es-v1",
        "kind": "REAL_NEURAL_PUBLIC_ARGOS_NOT_ORIGINAL_PRIVATE_MODEL",
        "required_cases": len(CASES),
        "routes": ["ja_en", "en_es"],
        "backend_executed": False,
        "cases": [],
        "models": [],
    }
    start = time.monotonic()
    try:
        engine, provenance = _create_models()
        report["models"] = provenance
        report["backend_executed"] = True
        with DurableTranslationCache(workspace / "cache") as cache:
            for sample in CASES:
                steps = []
                def neural(fragment: str) -> str:
                    english = engine.translate(fragment, "ja", "en")
                    if not isinstance(english, str) or not english.strip():
                        raise TranslationRejected("ARGOS_JA_EN_EMPTY")
                    spanish = engine.translate(english, "en", "es")
                    if not isinstance(spanish, str) or not spanish.strip():
                        raise TranslationRejected("ARGOS_EN_ES_EMPTY")
                    steps.append({"source": fragment[:180],
                                  "pivot_en": english[:250],
                                  "result_es": spanish[:250]})
                    return spanish

                def producer(japanese: str) -> str:
                    spanish = translate_checked(
                        japanese, neural, source="ja", glossary=dict(sample.glossary))
                    missing = _semantic_missing(spanish, sample.required_groups)
                    if missing:
                        raise TranslationRejected("SEMANTIC_FIDELITY_FAILED:" +
                                                  json.dumps(missing, ensure_ascii=False))
                    return spanish

                case_record = {"case": sample.id, "source": sample.japanese,
                               "status": "rejected", "stages": steps}
                try:
                    value = cache.translate_or_get(
                        "ja", "es", sample.japanese, producer)
                    case_record["status"] = "accepted"
                    case_record["translated"] = value
                    case_record["sha256"] = hashlib.sha256(
                        value.encode("utf-8")).hexdigest()
                except Exception as exc:
                    case_record["error"] = type(exc).__name__ + ":" + str(exc)[:450]
                report["cases"].append(case_record)
                print("NEURAL_CASE " + sample.id + " " + case_record["status"] +
                      " " + case_record.get("error", ""), flush=True)
            report["cache_rows"] = cache.count()
    except Exception as exc:
        report["setup_error"] = type(exc).__name__ + ":" + str(exc)[:800]
        print("NEURAL_SETUP_FAILURE " + report["setup_error"], flush=True)
    report["accepted"] = sum(1 for item in report["cases"]
                             if item["status"] == "accepted")
    report["rejected"] = len(CASES) - report["accepted"]
    report["elapsed_seconds"] = round(time.monotonic() - start, 2)
    _save_json(report_path, report)
    print("NEURAL_ACCEPTANCE_REPORT " +
          json.dumps(report, ensure_ascii=True, sort_keys=True), flush=True)
    # Full acceptance requires the actual backend and every independent
    # semantic/structural sample; never reduce the threshold to make CI green.
    return 0 if report["backend_executed"] and report["accepted"] == len(CASES) else 1


def verify_phase(workspace: Path) -> int:
    report_path = workspace / "neural-report.json"
    if not report_path.is_file():
        print("NEURAL_RESTART_FAIL_NO_PROOF_RECEIPT", flush=True)
        return 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    accepted = [c for c in report["cases"] if c["status"] == "accepted"]
    errors = []
    if not report.get("backend_executed"):
        errors.append("REAL_NEURAL_INFERENCE_WAS_NOT_EXECUTED")
    if not accepted:
        errors.append("NO_VALID_TRANSLATIONS_AVAILABLE_TO_RESTORE")
    db_path = workspace / "cache" / "translation-cache.sqlite3"
    if not db_path.is_file():
        errors.append("PERSISTENT_SQLITE_DATABASE_MISSING")
    else:
        with DurableTranslationCache(workspace / "cache") as cache:
            if cache.count() != len(accepted):
                errors.append("REJECTED_TRANSLATION_WAS_CACHED_OR_VALID_ROW_LOST")
            for row in accepted:
                value = cache.get("ja", "es", row["source"])
                if value != row["translated"]:
                    errors.append("CACHE_CONTENT_CHANGED:" + row["case"])
                    continue
                def forbidden_model(_unused: str) -> str:
                    raise RuntimeError("CACHE_MISS_TRIGGERED_NEURAL_INFERENCE")
                try:
                    replay = cache.translate_or_get(
                        "ja", "es", row["source"], forbidden_model)
                    if replay != row["translated"]:
                        errors.append("REPLAY_CONTENT_MISMATCH:" + row["case"])
                except Exception as exc:
                    errors.append("REPLAY_FAILED:" + row["case"] + ":" + str(exc)[:150])
            for row in report["cases"]:
                if row["status"] != "accepted" and cache.get(
                        "ja", "es", row["source"]) is not None:
                    errors.append("REJECTED_ITEM_PERSISTED:" + row["case"])
    proof = {"schema": "public-real-neural-cache-restart-v1",
             "accepted": len(accepted), "required": len(CASES),
             "backend_executed_before_restart": report.get("backend_executed", False),
             "models_loaded_during_restart": False, "errors": errors}
    _save_json(workspace / "restart-proof.json", proof)
    print("NEURAL_RESTART_PROOF " +
          json.dumps(proof, ensure_ascii=True, sort_keys=True), flush=True)
    return 0 if not errors and len(accepted) == len(CASES) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "translate":
        return translate_phase(args.workspace)
    return verify_phase(args.workspace)


if __name__ == "__main__":
    sys.exit(main())
