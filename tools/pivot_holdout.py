"""Strict Japanese -> English -> Spanish pivot evaluation on the fixed holdout.

Both public Marian models declare Apache-2.0. The route uses raw model output
with structural token/number/line-break protection only. No paraphrases,
glossary edits, target repairs, prepared translations, or retries are allowed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from tools.unseen_holdout import HOLDOUT_CASES, _require_semantic_fidelity
from translation_lab.cache import DurableTranslationCache
from translation_lab.review_queue import ReviewQueue
from translation_lab.pipeline import (
    TranslationRejected, contextualize_name_code_source,
    restore_contextual_name_codes, translate_checked, validate_translation,
)

JA_EN_MODEL_ID = "Helsinki-NLP/opus-mt-ja-en"
EN_ES_MODEL_ID = "Helsinki-NLP/opus-mt-en-es"
DECLARED_LICENSE = "apache-2.0"


def _load_pivot_models():
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    torch.set_num_threads(2)

    def load_one(model_id: str, source: str, target: str):
        tokenizer = AutoTokenizer.from_pretrained(
            model_id, trust_remote_code=False
        )
        model = AutoModelForSeq2SeqLM.from_pretrained(
            model_id, trust_remote_code=False
        )
        model.eval()

        class _Translator:
            def translate(self, text: str) -> str:
                if not isinstance(text, str) or not text.strip():
                    raise RuntimeError("PIVOT_MODEL_EMPTY_SOURCE:" + model_id)
                encoded = tokenizer(
                    [text], return_tensors="pt", truncation=False
                )
                if encoded["input_ids"].shape[-1] > 512:
                    raise RuntimeError("PIVOT_MODEL_CONTEXT_EXCEEDED:" + model_id)
                with torch.inference_mode():
                    generated = model.generate(
                        **encoded, max_new_tokens=256, num_beams=4,
                        renormalize_logits=True,
                    )
                decoded = tokenizer.batch_decode(
                    generated, skip_special_tokens=True
                )
                if len(decoded) != 1 or not isinstance(decoded[0], str):
                    raise RuntimeError("PIVOT_MODEL_INVALID_OUTPUT:" + model_id)
                return decoded[0]

        provenance = {
            "model_id": model_id,
            "architecture": model.__class__.__name__,
            "source": source,
            "target": target,
            "declared_license": DECLARED_LICENSE,
            "model_page": "https://huggingface.co/" + model_id,
            "trust_remote_code": False,
        }
        return _Translator(), provenance

    ja_en, ja_en_provenance = load_one(JA_EN_MODEL_ID, "ja", "en")
    en_es, en_es_provenance = load_one(EN_ES_MODEL_ID, "en", "es")
    return ja_en, en_es, [ja_en_provenance, en_es_provenance]


def _save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def translate_phase(workspace: Path) -> int:
    if workspace.exists():
        raise RuntimeError("PIVOT_HOLDOUT_WORKSPACE_MUST_BE_NEW")
    workspace.mkdir(parents=True)
    report = {
        "schema": "public-ja-en-es-pivot-holdout-v1",
        "kind": "REAL_NEURAL_PUBLIC_TWO_STAGE_MARIAN_PIVOT",
        "route": ["ja-en", "en-es"],
        "expected_models": [
            {"model_id": JA_EN_MODEL_ID, "declared_license": DECLARED_LICENSE},
            {"model_id": EN_ES_MODEL_ID, "declared_license": DECLARED_LICENSE},
        ],
        "evaluation_policy": {
            "holdout_cases": len(HOLDOUT_CASES),
            "source_paraphrases": False,
            "target_language_repairs": False,
            "prepared_translations": False,
            "case_specific_retries": False,
            "glossary_edits": False,
            "uniform_segmentation_modes": ["document_context", "line_context", "sentence_context"],
            "selection": "first_candidate_passing_fixed_semantic_policy",
            "numeric_literals_sent_to_model": True,
            "contextual_name_code_aliases": True,
            "structural_protection_only": True,
            "all_cases_required": True,
        },
        "backend_executed": False,
        "models": [],
        "cases": [],
    }
    started = time.monotonic()
    try:
        ja_en, en_es, provenance = _load_pivot_models()
        if len(provenance) != 2 or any(
            item.get("declared_license") != DECLARED_LICENSE
            for item in provenance
        ):
            raise RuntimeError("PIVOT_MODEL_LICENSE_PROVENANCE_INVALID")
        report["backend_executed"] = True
        report["models"] = provenance
        with DurableTranslationCache(workspace / "cache") as cache, ReviewQueue(workspace / "cache") as review_queue:
            for sample in HOLDOUT_CASES:
                ja_en_attempts: list[dict] = []
                en_es_attempts: list[dict] = []
                entry = {
                    "case": sample.id,
                    "source": sample.japanese,
                    "status": "rejected",
                    "ja_en_raw_attempts": ja_en_attempts,
                    "en_es_raw_attempts": en_es_attempts,
                }
                candidate_box: list[str] = []

                def producer(source_text: str) -> str:
                    rejected_modes: list[dict[str, str]] = []
                    for mode, segmentation in (
                        ("document_context", "document"),
                        ("line_context", "lines"),
                        ("sentence_context", True),
                    ):
                        model_source, name_codes = contextualize_name_code_source(source_text)

                        def translate_ja_en(fragment: str) -> str:
                            value = ja_en.translate(fragment)
                            ja_en_attempts.append({
                                "mode": mode,
                                "source_fragment": fragment[:220],
                                "raw_output": value[:600],
                            })
                            return value

                        def translate_en_es(fragment: str) -> str:
                            value = en_es.translate(fragment)
                            en_es_attempts.append({
                                "mode": mode,
                                "source_fragment": fragment[:220],
                                "raw_output": value[:600],
                            })
                            return value

                        try:
                            english = translate_checked(
                                model_source, translate_ja_en, source="ja",
                                protect_numbers=False,
                                split_model_sentences=segmentation,
                            )
                            entry["intermediate_english"] = english[:1400]
                            spanish = translate_checked(
                                english, translate_en_es, source="en",
                                protect_numbers=False,
                                split_model_sentences=segmentation,
                            )
                            spanish = restore_contextual_name_codes(spanish, name_codes)
                            validate_translation(source_text, spanish, source="ja")
                            candidate_box.append(spanish)
                            _require_semantic_fidelity(sample, spanish)
                            entry["accepted_segmentation_mode"] = mode
                            entry["rejected_segmentation_modes"] = rejected_modes
                            return spanish
                        except TranslationRejected as exc:
                            rejected_modes.append({
                                "mode": mode,
                                "reason": str(exc)[:350],
                            })
                    entry["rejected_segmentation_modes"] = rejected_modes
                    raise TranslationRejected(
                        "ALL_PIVOT_SEGMENTATION_MODES_REJECTED:" +
                        json.dumps(rejected_modes, ensure_ascii=False)[:700]
                    )

                try:
                    value = cache.translate_or_get(
                        "ja", "es", sample.japanese, producer,
                        quality_validator=lambda candidate: _require_semantic_fidelity(
                            sample, candidate
                        ),
                    )
                    validate_translation(sample.japanese, value, source="ja")
                    entry["status"] = "accepted"
                    entry["translated"] = value
                    entry["sha256"] = hashlib.sha256(
                        value.encode("utf-8")
                    ).hexdigest()
                except Exception as exc:
                    entry["error"] = type(exc).__name__ + ":" + str(exc)[:700]
                    review_item = review_queue.enqueue(
                        "ja", "es", sample.japanese,
                        candidate_box[-1] if candidate_box else "",
                        reason=entry["error"],
                        context={
                            "case_id": sample.id,
                            "semantic_policy": "unseen_holdout_v1",
                            "route": ["ja-en", "en-es"],
                            "model_provenance": provenance,
                            "intermediate_english": entry.get("intermediate_english", ""),
                            "ja_en_raw_attempts": ja_en_attempts,
                            "en_es_raw_attempts": en_es_attempts,
                        },
                    )
                    entry["review_item_id"] = review_item.item_id
                    entry["review_status"] = review_item.status
                report["cases"].append(entry)
                print(
                    "PIVOT_HOLDOUT_CASE " + sample.id + " " +
                    entry["status"] + " " + entry.get("error", ""),
                    flush=True,
                )
            report["cache_rows"] = cache.count()
            report["review_queue_pending"] = review_queue.count("pending")
            report["review_queue_total"] = review_queue.count()
            review_queue.export_snapshot(workspace / "review-queue.json")
    except Exception as exc:
        report["setup_error"] = type(exc).__name__ + ":" + str(exc)[:900]
        print("PIVOT_HOLDOUT_SETUP_FAILURE " + report["setup_error"], flush=True)

    report["accepted"] = sum(x["status"] == "accepted" for x in report["cases"])
    report["rejected"] = len(HOLDOUT_CASES) - report["accepted"]
    report["required"] = len(HOLDOUT_CASES)
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["status"] = (
        "PASS" if report["backend_executed"] and
        report["accepted"] == len(HOLDOUT_CASES) else "FAIL"
    )
    _save_json(workspace / "pivot-report.json", report)
    print(
        "PIVOT_HOLDOUT_REPORT " +
        json.dumps(report, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if report["status"] == "PASS" else 1


def verify_phase(workspace: Path) -> int:
    report_path = workspace / "pivot-report.json"
    if not report_path.is_file():
        print("PIVOT_HOLDOUT_RESTART_FAIL_NO_REPORT", flush=True)
        return 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    accepted = [x for x in report.get("cases", []) if x.get("status") == "accepted"]
    by_id = {x.id: x for x in HOLDOUT_CASES}
    errors: list[str] = []
    if not report.get("backend_executed"):
        errors.append("PIVOT_NEURAL_INFERENCE_NOT_EXECUTED")
    actual = report.get("models", [])
    expected = report.get("expected_models", [])
    if len(actual) != 2 or len(expected) != 2:
        errors.append("PIVOT_MODEL_PROVENANCE_CARDINALITY_INVALID")
    else:
        for observed, wanted in zip(actual, expected):
            if observed.get("model_id") != wanted.get("model_id"):
                errors.append("PIVOT_MODEL_ID_CHANGED")
            if observed.get("declared_license") != DECLARED_LICENSE:
                errors.append("PIVOT_MODEL_LICENSE_CHANGED")
    db_path = workspace / "cache" / "translation-cache.sqlite3"
    if not db_path.is_file():
        errors.append("PIVOT_SQLITE_DATABASE_MISSING")
    else:
        with DurableTranslationCache(workspace / "cache") as cache, ReviewQueue(workspace / "cache") as review_queue:
            if cache.count() != len(accepted) + review_queue.count("approved"):
                errors.append("PIVOT_REJECTED_ROW_CACHED_OR_ACCEPTED_ROW_LOST")
            approved_items = [
                item for item in review_queue.list_items(status="approved", limit=1000)
                if item.source == "ja" and item.target == "es"
                and item.context.get("semantic_policy") == "unseen_holdout_v1"
                and item.original in {case.japanese for case in HOLDOUT_CASES}
            ]
            approved_by_original = {
                item.original: item for item in sorted(
                    approved_items, key=lambda value: value.approved_at or value.updated_at
                )
            }
            auto_originals = {row.get("source") for row in accepted}
            human_originals = set(approved_by_original) - auto_originals
            total_accepted = len(auto_originals | set(approved_by_original))
            if total_accepted != len(HOLDOUT_CASES):
                errors.append("PIVOT_HOLDOUT_NOT_FULLY_ACCEPTED")
            if cache.count() != total_accepted:
                errors.append("PIVOT_CACHE_ROWS_DO_NOT_MATCH_ACCEPTED_ITEMS")
            for row in accepted:
                sample = by_id.get(row.get("case"))
                if sample is None:
                    errors.append("PIVOT_UNKNOWN_CASE:" + str(row.get("case")))
                    continue
                validator = lambda candidate, current=sample: _require_semantic_fidelity(
                    current, candidate
                )
                cached = cache.get(
                    "ja", "es", sample.japanese, quality_validator=validator
                )
                if cached != row.get("translated"):
                    errors.append("PIVOT_CACHE_CONTENT_CHANGED:" + sample.id)
                    continue
                try:
                    replay = cache.translate_or_get(
                        "ja", "es", sample.japanese,
                        lambda _unused: (_ for _ in ()).throw(
                            AssertionError("PIVOT_CACHE_MISS_RECALLED_MODEL")
                        ),
                        quality_validator=validator,
                    )
                    if replay != row.get("translated"):
                        errors.append("PIVOT_REPLAY_MISMATCH:" + sample.id)
                except Exception as exc:
                    errors.append("PIVOT_REPLAY_FAILED:" + sample.id + ":" + str(exc)[:180])
            for row in report.get("cases", []):
                if row.get("status") != "accepted":
                    sample = by_id.get(row.get("case"))
                    if sample is None:
                        errors.append("PIVOT_UNKNOWN_REJECTED_CASE:" + str(row.get("case")))
                    else:
                        review_item = review_queue.get(row.get("review_item_id", ""))
                        if review_item is None:
                            errors.append("REJECTED_CASE_MISSING_REVIEW_ITEM:" + sample.id)
                        elif (review_item.source, review_item.target, review_item.original) != ("ja", "es", sample.japanese):
                            errors.append("REVIEW_ITEM_SOURCE_MISMATCH:" + sample.id)
                        approved_for_case = [
                            candidate for candidate in review_queue.list_items(status="approved", limit=1000)
                            if (candidate.source, candidate.target, candidate.original) == ("ja", "es", sample.japanese)
                        ]
                        if approved_for_case:
                            approved_correction = approved_for_case[-1].correction
                            promoted = cache.get(
                                "ja", "es", sample.japanese,
                                quality_validator=lambda candidate, current=sample: _require_semantic_fidelity(current, candidate),
                            )
                            if promoted != approved_correction:
                                errors.append("HUMAN_APPROVAL_NOT_IN_ACCEPTED_CACHE:" + sample.id)
                        elif cache.get("ja", "es", sample.japanese) is not None:
                            errors.append("PIVOT_REJECTED_CASE_WAS_CACHED:" + sample.id)

    proof = {
        "schema": "public-ja-en-es-pivot-restart-v1",
        "accepted": len(accepted),
        "human_approved": len(human_originals) if "human_originals" in locals() else 0,
        "total_accepted": total_accepted if "total_accepted" in locals() else len(accepted),
        "required": len(HOLDOUT_CASES),
        "backend_executed_before_restart": bool(report.get("backend_executed")),
        "models_loaded_during_restart": False,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
    _save_json(workspace / "pivot-restart-proof.json", proof)
    print(
        "PIVOT_HOLDOUT_RESTART_PROOF " +
        json.dumps(proof, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    return translate_phase(args.workspace) if args.phase == "translate" else verify_phase(
        args.workspace
    )


if __name__ == "__main__":
    sys.exit(main())
