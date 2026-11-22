"""Gated research evaluation of Qwen3-8B on the separate 10-dialogue set.

No development receipt can be promoted without 20/20 semantic acceptance AND
cold-restart integrity. No Spanish references, model-output repairs, human
approvals, or per-case prompts enter the next-stage inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools import qwen3_8b_careful_ja_es_candidate as careful
from tools import qwen3_8b_thinking_ja_es_candidate as thinking
from tools import qwen3_8b_two_pass_ja_es_candidate as two_pass
from tools.stage3_readiness import promotion_errors, source_only_manifest
from tools.unseen_holdout import HOLDOUT_CASES, _require_semantic_fidelity
from translation_lab.cache import DurableTranslationCache
from translation_lab.review_queue import ReviewQueue
from translation_lab.restart import verify_candidate_persistence
from translation_lab.pipeline import (
    TranslationRejected,
    translate_checked,
    validate_translation,
)

SEGMENTATION_MODES = (
    ("document_context", "document"),
    ("line_context", "lines"),
    ("sentence_context", True),
)
CAREFUL_SCHEMA = "public-qwen3-8b-careful-ja-es-candidate-v1"
THINKING_SCHEMA = "public-qwen3-8b-thinking-ja-es-candidate-v1"
# Uniform per-call budget on CPU: 2048 output tokens at ~4 tok/s need
# substantially more than the previous 180-second HTTP cutoff.
THINKING_REQUEST_TIMEOUT_SECONDS = 720
TWO_PASS_SCHEMA = "public-qwen3-8b-two-pass-ja-es-candidate-v1"


def _write(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_pinned_model(
    schema: str, llama_server: Path, workspace: Path
):
    if schema == CAREFUL_SCHEMA:
        return careful._load_careful_model(llama_server, workspace)
    if schema == THINKING_SCHEMA:
        model, provenance = thinking._load_model(llama_server, workspace)
        original_request = model.request_json

        def extended_timeout_request(url: str, payload: dict, timeout: int):
            # The identical prompt, seed, sampling and generated text are used;
            # only the HTTP deadline changes, for every source without exception.
            return original_request(
                url, payload, max(timeout, THINKING_REQUEST_TIMEOUT_SECONDS)
            )

        model.request_json = extended_timeout_request
        provenance[0]["http_request_timeout_seconds"] = (
            THINKING_REQUEST_TIMEOUT_SECONDS
        )
        return model, provenance
    if schema == TWO_PASS_SCHEMA:
        return two_pass._load_two_pass_model(llama_server, workspace)
    raise RuntimeError("STAGE3_UNSUPPORTED_CANDIDATE_VARIANT")


def translate_phase(
    workspace: Path,
    development_report: Path,
    restart_proof: Path,
    llama_server: Path | None,
    *,
    model_loader=None,
) -> int:
    """Run a new local-model inference only after evidence passes the gate."""
    development_raw = development_report.read_bytes()
    restart_raw = restart_proof.read_bytes()
    development = json.loads(development_raw)
    restart = json.loads(restart_raw)
    blocked = promotion_errors(development, restart)
    if blocked:
        print(
            "QWEN8B_STAGE3_PROMOTION_BLOCKED "
            + json.dumps({"errors": blocked}, sort_keys=True),
            flush=True,
        )
        return 1
    if workspace.exists():
        raise RuntimeError("QWEN8B_STAGE3_WORKSPACE_MUST_BE_NEW")
    workspace.mkdir(parents=True)

    manifest = source_only_manifest()
    manifest["promotion_evidence"] = {
        "development_report_sha256": hashlib.sha256(
            development_raw
        ).hexdigest(),
        "cold_restart_proof_sha256": hashlib.sha256(
            restart_raw
        ).hexdigest(),
    }
    _write(workspace / "stage3-source-manifest.json", manifest)

    report: dict = {
        "schema": "public-qwen3-8b-stage3-ten-dialogue-v1",
        "research_only": True,
        "held_out_from_development": True,
        "not_a_blind_or_external_benchmark": True,
        "candidate_schema": development["schema"],
        "model_provenance": development["models"],
        "manifest_sha256": manifest["sha256"],
        "promotion_evidence": manifest["promotion_evidence"],
        "source_count": len(HOLDOUT_CASES),
        "backend_executed": False,
        "case_specific_retries": False,
        "target_side_repairs": False,
        "human_approvals": False,
        "cases": [],
    }
    model = None
    try:
        if model_loader is not None:
            model, provenance = model_loader()
        else:
            if llama_server is None:
                raise RuntimeError("QWEN8B_STAGE3_LLAMA_SERVER_REQUIRED")
            model, provenance = _load_pinned_model(
                development["schema"], llama_server, workspace
            )
        expected = development["models"]
        if (
            len(provenance) != 1
            or len(expected) != 1
            or provenance[0].get("repo_id") != expected[0].get("repo_id")
            or provenance[0].get("revision") != expected[0].get("revision")
            or provenance[0].get("sha256") != expected[0].get("sha256")
        ):
            raise RuntimeError("QWEN8B_STAGE3_MODEL_PROVENANCE_MISMATCH")

        report["backend_executed"] = True
        report["inference_runtime_provenance"] = provenance
        with (
            DurableTranslationCache(workspace / "cache") as cache,
            ReviewQueue(workspace / "cache") as reviews,
        ):
            for case in HOLDOUT_CASES:
                entry: dict = {
                    "case": case.id,
                    "source": case.japanese,
                    "status": "rejected",
                    "raw_model_attempts": [],
                }
                candidates: list[str] = []

                def producer(source_text: str) -> str:
                    failures: list[dict] = []
                    for mode, layout in SEGMENTATION_MODES:
                        def translate_piece(fragment: str) -> str:
                            raw = model.translate(fragment)
                            entry["raw_model_attempts"].append({
                                "mode": mode,
                                "source_fragment": fragment,
                                "raw_output": raw,
                            })
                            return raw

                        try:
                            translated = translate_checked(
                                source_text,
                                translate_piece,
                                source="ja",
                                protect_numbers=False,
                                contextualize_name_codes=False,
                                split_model_sentences=layout,
                                protect_literals_in_context=True,
                            )
                            candidates.append(translated)
                            validate_translation(
                                source_text, translated, source="ja"
                            )
                            _require_semantic_fidelity(case, translated)
                            entry["accepted_mode"] = mode
                            entry["rejected_modes"] = failures
                            return translated
                        except Exception as exc:
                            failures.append({
                                "mode": mode,
                                "reason": type(exc).__name__ + ":" + str(exc)[:450],
                            })
                    entry["rejected_modes"] = failures
                    if failures and all(
                        "TimeoutError" in failure["reason"]
                        for failure in failures
                    ):
                        raise TranslationRejected("STAGE3_ALL_MODES_TIMED_OUT")
                    raise TranslationRejected("STAGE3_ALL_MODES_REJECTED")

                try:
                    translated = cache.translate_or_get(
                        "ja", "es", case.japanese, producer,
                        quality_validator=lambda value, sample=case:
                            _require_semantic_fidelity(sample, value),
                    )
                    validate_translation(case.japanese, translated, source="ja")
                    _require_semantic_fidelity(case, translated)
                    entry["status"] = "accepted"
                    entry["translated"] = translated
                    entry["sha256"] = hashlib.sha256(
                        translated.encode("utf-8")
                    ).hexdigest()
                except Exception as exc:
                    entry["error"] = type(exc).__name__ + ":" + str(exc)[:500]
                    item = reviews.enqueue(
                        "ja", "es", case.japanese,
                        candidates[-1] if candidates else "",
                        reason=entry["error"],
                        context={
                            "case_id": case.id,
                            "source_set": "separate_ten_dialogue_research_holdout",
                            "raw_model_attempts": entry["raw_model_attempts"],
                        },
                    )
                    entry["review_item_id"] = item.item_id
                    entry["review_status"] = item.status

                report["cases"].append(entry)
                print(
                    f"QWEN8B_STAGE3_CASE {case.id} {entry['status']}",
                    flush=True,
                )
            report["cache_rows"] = cache.count()
            report["review_queue_total"] = reviews.count()
            report["review_queue_pending"] = reviews.count("pending")
            reviews.export_snapshot(workspace / "stage3-review-queue.json")
    except Exception as exc:
        report["setup_error"] = type(exc).__name__ + ":" + str(exc)[:600]
    finally:
        if model is not None and hasattr(model, "close"):
            model.close()

    report["accepted"] = sum(
        row.get("status") == "accepted" for row in report["cases"]
    )
    report["rejected"] = len(HOLDOUT_CASES) - report["accepted"]
    report["status"] = (
        "PASS" if report["backend_executed"]
        and report["accepted"] == len(HOLDOUT_CASES)
        and report.get("cache_rows") == len(HOLDOUT_CASES)
        and report.get("review_queue_total") == 0
        else "FAIL"
    )
    _write(workspace / "stage3-report.json", report)
    print(
        "QWEN8B_STAGE3_REPORT "
        + json.dumps({
            "status": report["status"],
            "accepted": report["accepted"],
            "rejected": report["rejected"],
            "backend_executed": report["backend_executed"],
            "setup_error": report.get("setup_error"),
        }, sort_keys=True),
        flush=True,
    )
    return 0 if report["status"] == "PASS" else 1


def verify_phase(workspace: Path) -> int:
    """Cold-process durability audit, never reloading neural model weights."""
    report_path = workspace / "stage3-report.json"
    manifest_path = workspace / "stage3-source-manifest.json"
    if not report_path.is_file() or not manifest_path.is_file():
        print("QWEN8B_STAGE3_RESTART_MISSING_REPORT_OR_MANIFEST", flush=True)
        return 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = report.get("cases") or []
    by_id = {case.id: case for case in HOLDOUT_CASES}
    accepted = [row for row in rows if row.get("status") == "accepted"]
    errors: list[str] = []
    quality: list[str] = []
    persistence: list[str] = []

    if (
        len(rows) != len(by_id)
        or {row.get("case") for row in rows} != set(by_id)
        or manifest.get("sha256") != source_only_manifest()["sha256"]
        or report.get("manifest_sha256") != manifest.get("sha256")
        or manifest.get("promotion_evidence") != report.get("promotion_evidence")
    ):
        errors.append("STAGE3_REPORT_OR_MANIFEST_CHANGED")
    if not report.get("backend_executed"):
        errors.append("STAGE3_NEURAL_BACKEND_NOT_EXECUTED")
    if len(accepted) != len(HOLDOUT_CASES):
        quality.append("STAGE3_NOT_ALL_HOLDOUT_CASES_ACCEPTED")

    database = workspace / "cache" / "translation-cache.sqlite3"
    if not database.is_file():
        persistence.append("STAGE3_SQLITE_DATABASE_MISSING")
    else:
        with (
            DurableTranslationCache(workspace / "cache") as cache,
            ReviewQueue(workspace / "cache") as reviews,
        ):
            persistence.extend(verify_candidate_persistence(
                cache, reviews,
                accepted_count=len(accepted),
                rejected_count=max(0, len(rows) - len(accepted)),
                prefix="QWEN8BSTAGE3",
            ))
            for row in accepted:
                case = by_id.get(row.get("case"))
                if case is None:
                    errors.append("STAGE3_UNKNOWN_CASE")
                    continue
                output = row.get("translated", "")
                if row.get("source") != case.japanese:
                    errors.append("STAGE3_JAPANESE_SOURCE_CHANGED:" + case.id)
                if row.get("sha256") != hashlib.sha256(
                    output.encode("utf-8")
                ).hexdigest():
                    persistence.append("STAGE3_DIGEST_CHANGED:" + case.id)
                try:
                    validate_translation(case.japanese, output, source="ja")
                    _require_semantic_fidelity(case, output)
                except TranslationRejected:
                    quality.append("STAGE3_SEMANTIC_OR_STRUCTURE_FAILED:" + case.id)
                    continue
                validator = lambda value, sample=case: _require_semantic_fidelity(
                    sample, value
                )
                cached = cache.get(
                    "ja", "es", case.japanese, quality_validator=validator
                )
                if cached != output:
                    persistence.append("STAGE3_CACHE_CONTENT_CHANGED:" + case.id)
                    continue
                try:
                    replay = cache.translate_or_get(
                        "ja", "es", case.japanese,
                        lambda _source: (_ for _ in ()).throw(
                            AssertionError("STAGE3_REPLAY_RECALLED_MODEL")
                        ),
                        quality_validator=validator,
                    )
                    if replay != output:
                        persistence.append("STAGE3_REPLAY_MISMATCH:" + case.id)
                except Exception as exc:
                    persistence.append(
                        "STAGE3_REPLAY_FAILED:" + case.id
                        + ":" + type(exc).__name__
                    )

    proof = {
        "schema": "public-qwen3-8b-stage3-restart-v1",
        "required": len(HOLDOUT_CASES),
        "accepted": len(accepted),
        "models_loaded_during_restart": False,
        "errors": errors,
        "quality_errors": quality,
        "persistence_errors": persistence,
        "quality_status": "PASS" if not quality else "FAIL",
        "persistence_status": "PASS" if not persistence else "FAIL",
        "status": (
            "PASS" if not (errors or quality or persistence)
            else "QUALITY_FAIL_PERSISTENCE_PASS"
            if not (errors or persistence) else "FAIL"
        ),
    }
    _write(workspace / "stage3-restart-proof.json", proof)
    print(
        "QWEN8B_STAGE3_RESTART_PROOF "
        + json.dumps(proof, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if not (errors or persistence) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path)
    parser.add_argument("--candidate-restart-proof", type=Path)
    parser.add_argument("--llama-server", type=Path)
    args = parser.parse_args()
    if args.phase == "translate":
        if not args.candidate_report or not args.candidate_restart_proof:
            parser.error("Stage3 translation requires both development receipts")
        return translate_phase(
            args.workspace, args.candidate_report,
            args.candidate_restart_proof, args.llama_server,
        )
    return verify_phase(args.workspace)


if __name__ == "__main__":
    raise SystemExit(main())
