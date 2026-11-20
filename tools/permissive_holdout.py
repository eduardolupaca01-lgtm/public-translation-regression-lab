"""Compare permissively licensed public models on the fixed ten-case holdout.

No source paraphrases, target-language corrections, prepared translations, or
case-specific retries are allowed. Only structural protection, strict semantic
validation, and durable SQLite caching are shared between candidate models.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

from tools.direct_marian_acceptance import _load_public_model
from tools.m2m_acceptance import _load_public_m2m_model
from tools.unseen_holdout import HOLDOUT_CASES, _require_semantic_fidelity
from translation_lab.cache import DurableTranslationCache
from translation_lab.review_queue import ReviewQueue
from translation_lab.pipeline import translate_checked, validate_translation


@dataclass(frozen=True)
class BackendSpec:
    model_id: str
    declared_license: str
    loader: Callable[[], tuple[Any, list[dict]]]


MODEL_SPECS = {
    "marian": BackendSpec(
        "Helsinki-NLP/opus-mt-ja-es", "apache-2.0", _load_public_model
    ),
    "m2m100": BackendSpec(
        "facebook/m2m100_418M", "mit", _load_public_m2m_model
    ),
}


def _load_backend(backend: str):
    try:
        spec = MODEL_SPECS[backend]
    except KeyError as exc:
        raise ValueError("UNKNOWN_HOLDOUT_BACKEND") from exc
    model, provenance = spec.loader()
    if not isinstance(provenance, list) or len(provenance) != 1:
        raise RuntimeError("HOLDOUT_MODEL_PROVENANCE_CARDINALITY_INVALID")
    metadata = provenance[0]
    if metadata.get("model_id") != spec.model_id:
        raise RuntimeError("HOLDOUT_MODEL_ID_PROVENANCE_MISMATCH")
    if metadata.get("declared_license") != spec.declared_license:
        raise RuntimeError("HOLDOUT_MODEL_LICENSE_PROVENANCE_MISMATCH")
    return model, provenance


def _save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def translate_phase(backend: str, workspace: Path) -> int:
    if backend not in MODEL_SPECS:
        raise ValueError("UNKNOWN_HOLDOUT_BACKEND")
    if workspace.exists():
        raise RuntimeError("LICENSED_HOLDOUT_WORKSPACE_MUST_BE_NEW")
    workspace.mkdir(parents=True)
    spec = MODEL_SPECS[backend]
    report = {
        "schema": "public-licensed-unseen-holdout-v1",
        "backend": backend,
        "kind": "REAL_NEURAL_PUBLIC_LICENSED_MODEL_NOT_ORIGINAL_PRIVATE_MODEL",
        "expected_model_id": spec.model_id,
        "expected_license": spec.declared_license,
        "evaluation_policy": {
            "holdout_cases": len(HOLDOUT_CASES),
            "source_paraphrases": False,
            "target_language_repairs": False,
            "prepared_translations": False,
            "case_specific_retries": False,
            "structural_pipeline_only": True,
            "all_cases_required": True,
        },
        "backend_executed": False,
        "models": [],
        "cases": [],
    }
    started = time.monotonic()
    try:
        model, provenance = _load_backend(backend)
        report["backend_executed"] = True
        report["models"] = provenance
        with DurableTranslationCache(workspace / "cache") as cache, ReviewQueue(workspace / "cache") as review_queue:
            for sample in HOLDOUT_CASES:
                attempts: list[dict] = []
                entry = {
                    "case": sample.id,
                    "source": sample.japanese,
                    "status": "rejected",
                    "raw_model_attempts": attempts,
                }
                candidate_box: list[str] = []

                def producer(source_text: str) -> str:
                    def model_piece(fragment: str) -> str:
                        value = model.translate(fragment)
                        attempts.append({
                            "source_fragment": fragment[:220],
                            "raw_output": value[:500] if isinstance(value, str) else "",
                        })
                        return value
                    candidate = translate_checked(
                        source_text, model_piece, source="ja",
                        protect_numbers=True,
                        split_model_sentences=True,
                    )
                    candidate_box.append(candidate)
                    _require_semantic_fidelity(sample, candidate)
                    return candidate

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
                            "backend": backend,
                            "model_provenance": provenance,
                            "raw_model_attempts": attempts,
                        },
                    )
                    entry["review_item_id"] = review_item.item_id
                    entry["review_status"] = review_item.status
                report["cases"].append(entry)
                print(
                    "LICENSED_HOLDOUT_CASE " + backend + " " + sample.id + " " +
                    entry["status"] + " " + entry.get("error", ""),
                    flush=True,
                )
            report["cache_rows"] = cache.count()
            report["review_queue_pending"] = review_queue.count("pending")
            report["review_queue_total"] = review_queue.count()
            review_queue.export_snapshot(workspace / "review-queue.json")
    except Exception as exc:
        report["setup_error"] = type(exc).__name__ + ":" + str(exc)[:900]
        print("LICENSED_HOLDOUT_SETUP_FAILURE " + report["setup_error"], flush=True)

    report["accepted"] = sum(x["status"] == "accepted" for x in report["cases"])
    report["rejected"] = len(HOLDOUT_CASES) - report["accepted"]
    report["required"] = len(HOLDOUT_CASES)
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["status"] = (
        "PASS" if report["backend_executed"] and
        report["accepted"] == len(HOLDOUT_CASES) else "FAIL"
    )
    _save_json(workspace / "holdout-report.json", report)
    print(
        "LICENSED_HOLDOUT_REPORT " +
        json.dumps(report, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if report["status"] == "PASS" else 1


def verify_phase(backend: str, workspace: Path) -> int:
    if backend not in MODEL_SPECS:
        raise ValueError("UNKNOWN_HOLDOUT_BACKEND")
    report_path = workspace / "holdout-report.json"
    if not report_path.is_file():
        print("LICENSED_HOLDOUT_RESTART_FAIL_NO_REPORT", flush=True)
        return 1
    spec = MODEL_SPECS[backend]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    accepted = [x for x in report.get("cases", []) if x.get("status") == "accepted"]
    case_by_id = {x.id: x for x in HOLDOUT_CASES}
    errors: list[str] = []
    if report.get("backend") != backend:
        errors.append("HOLDOUT_BACKEND_CHANGED")
    if not report.get("backend_executed"):
        errors.append("REAL_MODEL_INFERENCE_NOT_EXECUTED")
    if report.get("expected_model_id") != spec.model_id:
        errors.append("EXPECTED_MODEL_ID_CHANGED")
    if report.get("expected_license") != spec.declared_license:
        errors.append("EXPECTED_LICENSE_CHANGED")
    metadata = report.get("models", [{}])[0]
    if metadata.get("model_id") != spec.model_id:
        errors.append("ACTUAL_MODEL_ID_PROVENANCE_MISMATCH")
    if metadata.get("declared_license") != spec.declared_license:
        errors.append("ACTUAL_MODEL_LICENSE_PROVENANCE_MISMATCH")
    if len(accepted) != len(HOLDOUT_CASES):
        errors.append("HOLDOUT_NOT_FULLY_ACCEPTED")
    db_path = workspace / "cache" / "translation-cache.sqlite3"
    if not db_path.is_file():
        errors.append("HOLDOUT_SQLITE_DATABASE_MISSING")
    else:
        with DurableTranslationCache(workspace / "cache") as cache, ReviewQueue(workspace / "cache") as review_queue:
            if cache.count() != len(accepted) + review_queue.count("approved"):
                errors.append("REJECTED_ROW_CACHED_OR_ACCEPTED_ROW_LOST")
            for row in accepted:
                sample = case_by_id.get(row.get("case"))
                if sample is None:
                    errors.append("UNKNOWN_HOLDOUT_CASE:" + str(row.get("case")))
                    continue
                validator = lambda candidate, current=sample: _require_semantic_fidelity(
                    current, candidate
                )
                cached = cache.get(
                    "ja", "es", sample.japanese, quality_validator=validator
                )
                if cached != row.get("translated"):
                    errors.append("CACHE_CONTENT_CHANGED:" + sample.id)
                    continue
                try:
                    replay = cache.translate_or_get(
                        "ja", "es", sample.japanese,
                        lambda _unused: (_ for _ in ()).throw(
                            AssertionError("HOLDOUT_CACHE_MISS_RECALLED_MODEL")
                        ),
                        quality_validator=validator,
                    )
                    if replay != row.get("translated"):
                        errors.append("CACHE_REPLAY_MISMATCH:" + sample.id)
                except Exception as exc:
                    errors.append("CACHE_REPLAY_FAILED:" + sample.id + ":" + str(exc)[:180])
            for row in report.get("cases", []):
                if row.get("status") != "accepted":
                    sample = case_by_id.get(row.get("case"))
                    if sample and cache.get("ja", "es", sample.japanese) is not None:
                        errors.append("REJECTED_ROW_WAS_CACHED:" + sample.id)
                    if sample is not None:
                        review_item = review_queue.get(row.get("review_item_id", ""))
                        if review_item is None:
                            errors.append("REJECTED_CASE_MISSING_REVIEW_ITEM:" + sample.id)
                        elif (review_item.source, review_item.target, review_item.original) != ("ja", "es", sample.japanese):
                            errors.append("REVIEW_ITEM_SOURCE_MISMATCH:" + sample.id)
                        elif review_item.status == "approved":
                            promoted = cache.get(
                                "ja", "es", sample.japanese,
                                quality_validator=lambda candidate, current=sample: _require_semantic_fidelity(current, candidate),
                            )
                            if promoted != review_item.correction:
                                errors.append("HUMAN_APPROVAL_NOT_IN_ACCEPTED_CACHE:" + sample.id)

    proof = {
        "schema": "public-licensed-unseen-holdout-restart-v1",
        "backend": backend,
        "model_id": spec.model_id,
        "declared_license": spec.declared_license,
        "accepted": len(accepted),
        "required": len(HOLDOUT_CASES),
        "backend_executed_before_restart": bool(report.get("backend_executed")),
        "models_loaded_during_restart": False,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
    _save_json(workspace / "holdout-restart-proof.json", proof)
    print(
        "LICENSED_HOLDOUT_RESTART_PROOF " +
        json.dumps(proof, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--backend", required=True, choices=tuple(MODEL_SPECS))
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    if args.phase == "translate":
        return translate_phase(args.backend, args.workspace)
    return verify_phase(args.backend, args.workspace)


if __name__ == "__main__":
    sys.exit(main())
