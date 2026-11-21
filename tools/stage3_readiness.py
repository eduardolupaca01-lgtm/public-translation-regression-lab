"""Strict transition gate from Qwen3-8B development to disjoint dialogue holdout.

This module NEVER generates translations, repairs target text, or approves a
partially accepted model. It checks evidence produced by the actual neural
candidate and cold-process restart before exporting *source-only* test cases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.independent_pivot_holdout import (
    INDEPENDENT_CASES,
    SEMANTIC_POLICY_VERSION,
    _semantic_errors,
)
from tools.qwen3_8b_thinking_ja_es_candidate import (
    MODEL_REPO, MODEL_REVISION, MODEL_SHA256,
)
from tools.unseen_holdout import HOLDOUT_CASES
from translation_lab.pipeline import TranslationRejected, validate_translation


def promotion_errors(report: dict, restart: dict) -> list[str]:
    """Return evidence failures; an empty list is necessary for promotion."""
    errors: list[str] = []
    by_id = {case.id: case for case in INDEPENDENT_CASES}
    rows = report.get("cases") or []
    allowed_schemas = {
        "public-qwen3-8b-thinking-ja-es-candidate-v1",
        "public-qwen3-8b-careful-ja-es-candidate-v1",
        "public-qwen3-8b-two-pass-ja-es-candidate-v1",
    }
    schema = report.get("schema")
    if schema not in allowed_schemas:
        errors.append("UNEXPECTED_CANDIDATE_REPORT_SCHEMA")
    if schema == "public-qwen3-8b-careful-ja-es-candidate-v1":
        generation = report.get("generation_parameters") or {}
        policy = report.get("evaluation_policy") or {}
        if (
            policy.get("generation_variant")
            != "uniform_source_only_careful_prompt"
            or generation.get("temperature") != 0.25
            or generation.get("top_p") != 0.93
            or generation.get("seed") != 512
            or generation.get("source_only_prompt") is not True
        ):
            errors.append("CAREFUL_GENERATION_PROVENANCE_CHANGED")
    if schema == "public-qwen3-8b-two-pass-ja-es-candidate-v1":
        generation = report.get("generation_parameters") or {}
        policy = report.get("evaluation_policy") or {}
        if (
            policy.get("generation_variant")
            != "uniform_neural_two_pass_revision"
            or policy.get("two_neural_passes_for_every_request") is not True
            or policy.get("scripted_target_repairs") is not False
            or generation.get("draft") != {
                "temperature": 0.25, "top_p": 0.93, "seed": 512
            }
            or generation.get("review") != {
                "temperature": 0.0, "top_p": 1.0, "seed": 513
            }
            or generation.get("same_pinned_model_for_both") is not True
        ):
            errors.append("TWO_PASS_GENERATION_PROVENANCE_CHANGED")
        if not report.get("neural_review_history"):
            errors.append("TWO_PASS_RAW_REVIEW_EVIDENCE_MISSING")
    if report.get("status") != "PASS" or not report.get("backend_executed"):
        errors.append("NEURAL_DEVELOPMENT_NOT_PASSED")
    if (
        len(rows) != len(by_id)
        or {row.get("case") for row in rows if isinstance(row, dict)}
        != set(by_id)
    ):
        errors.append("DEVELOPMENT_CASES_MISSING_OR_DUPLICATED")
    if (
        report.get("accepted") != len(by_id)
        or report.get("rejected") != 0
        or report.get("required") != len(by_id)
        or report.get("cache_rows") != len(by_id)
        or report.get("review_queue_total") != 0
    ):
        errors.append("DEVELOPMENT_NOT_FULLY_ACCEPTED")

    policy = report.get("evaluation_policy") or {}
    required_policy = {
        "semantic_policy_version": SEMANTIC_POLICY_VERSION,
        "case_set_status": "published_development_regression_set_not_blind",
        "case_sources_unchanged": True,
        "human_approvals": False,
        "target_repairs": False,
        "source_paraphrases": False,
        "case_specific_retries": False,
        "glossary_edits": False,
        "all_cases_required": True,
    }
    if any(policy.get(key) != value for key, value in required_policy.items()):
        errors.append("EVALUATION_POLICY_PROVENANCE_CHANGED")

    expected = report.get("expected_model") or {}
    model_rows = report.get("models") or []
    if (
        expected.get("repo_id") != MODEL_REPO
        or expected.get("revision") != MODEL_REVISION
        or expected.get("sha256") != MODEL_SHA256
        or len(model_rows) != 1
        or model_rows[0].get("repo_id") != MODEL_REPO
        or model_rows[0].get("sha256") != MODEL_SHA256
        or model_rows[0].get("declared_license") != "apache-2.0"
    ):
        errors.append("MODEL_PROVENANCE_UNVERIFIED")

    for row in rows:
        if not isinstance(row, dict):
            errors.append("MALFORMED_CANDIDATE_CASE_ROW")
            continue
        case_id = row.get("case")
        case = by_id.get(case_id)
        if case is None:
            errors.append("UNKNOWN_CANDIDATE_CASE:" + str(case_id))
            continue
        translated = row.get("translated")
        if row.get("source") != case.japanese:
            errors.append("JAPANESE_SOURCE_CHANGED:" + case_id)
        if row.get("status") != "accepted" or not isinstance(translated, str):
            errors.append("UNACCEPTED_DEVELOPMENT_CASE:" + case_id)
            continue
        if not row.get("raw_model_attempts"):
            errors.append("MISSING_RAW_MODEL_RECEIPTS:" + case_id)
        digest = hashlib.sha256(translated.encode("utf-8")).hexdigest()
        # Older genuine runner receipts have no per-row digest; their cold
        # SQLite replay and independent semantic validation still apply.
        # When a digest is supplied, it must match exactly.
        if row.get("sha256") is not None and row.get("sha256") != digest:
            errors.append("TRANSLATION_RECEIPT_HASH_MISMATCH:" + case_id)
        try:
            validate_translation(case.japanese, translated, source="ja")
            if _semantic_errors(case, translated):
                errors.append("SEMANTIC_CHECK_FAILED:" + case_id)
        except TranslationRejected:
            errors.append("STRUCTURAL_CHECK_FAILED:" + case_id)

    if (
        restart.get("status") != "PASS"
        or restart.get("accepted") != len(by_id)
        or restart.get("required") != len(by_id)
        or restart.get("quality_status") != "PASS"
        or restart.get("persistence_status") != "PASS"
        or restart.get("models_loaded_during_restart") is not False
        or restart.get("errors")
        or restart.get("quality_errors")
        or restart.get("persistence_errors")
    ):
        errors.append("COLD_RESTART_PROOF_INCOMPLETE")

    fresh_sources = {case.japanese for case in HOLDOUT_CASES}
    if (
        len(HOLDOUT_CASES) != 10
        or len(fresh_sources) != len(HOLDOUT_CASES)
        or fresh_sources & {case.japanese for case in INDEPENDENT_CASES}
    ):
        errors.append("NEXT_STAGE_NOT_DISJOINT_FROM_DEVELOPMENT")
    return errors


def source_only_manifest() -> dict:
    """Freeze next-stage Japanese inputs without Spanish reference answers."""
    entries = [{"case": case.id, "source": case.japanese} for case in HOLDOUT_CASES]
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True)
    return {
        "schema": "research-ja-es-next-stage-source-manifest-v1",
        "case_set": "existing_separate_ten_case_dialogue_holdout",
        "count": len(entries),
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "cases": entries,
        "note": "Research holdout; not a secret or untouched external benchmark.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-report", type=Path, required=True)
    parser.add_argument("--restart-proof", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.candidate_report.read_text(encoding="utf-8"))
    proof = json.loads(args.restart_proof.read_text(encoding="utf-8"))
    errors = promotion_errors(report, proof)
    result = {
        "status": "PASS" if not errors else "BLOCKED",
        "accepted_development": report.get("accepted"),
        "required_development": len(INDEPENDENT_CASES),
        "next_stage_count": len(HOLDOUT_CASES),
        "errors": errors,
    }
    print(
        "QWEN8B_NEXT_STAGE_GATE "
        + json.dumps(result, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    if errors:
        return 1
    manifest = source_only_manifest()
    manifest["promotion_evidence"] = {
        "development_report_sha256": hashlib.sha256(
            args.candidate_report.read_bytes()
        ).hexdigest(),
        "cold_restart_proof_sha256": hashlib.sha256(
            args.restart_proof.read_bytes()
        ).hexdigest(),
    }
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
