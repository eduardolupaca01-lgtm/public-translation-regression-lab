"""Independent post-hoc JA→ES quality screen of the 10-dialogue holdout.

The historic 10/10 result remains unchanged. This supplementary audit checks
previously untested relationships, grammar, and lexical ambiguity without
rewriting any model output. This is NOT a replacement for bilingual review or
an untouched, external blind benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from tools.qwen3_8b_thinking_ja_es_candidate import (
    MODEL_REPO, MODEL_REVISION, MODEL_SHA256,
)
from tools.stage3_readiness import source_only_manifest
from tools.unseen_holdout import HOLDOUT_CASES

SCHEMA = "ja-es-stage4-bilingual-quality-screen-v1"
STAGE3_SCHEMA = "public-qwen3-8b-stage3-ten-dialogue-v1"
THINKING_SCHEMA = "public-qwen3-8b-thinking-ja-es-candidate-v1"


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in value if not unicodedata.combining(c))


def screen_stage3(report: dict, restart: dict, manifest: dict) -> dict:
    """Audit stage3 receipts; *never* grant independent human approval."""
    errors: list[str] = []
    hard: list[dict[str, str]] = []
    review: list[dict[str, str]] = []
    cases = report.get("cases")
    known = {case.id: case.japanese for case in HOLDOUT_CASES}
    expected_manifest = source_only_manifest()

    if (
        report.get("schema") != STAGE3_SCHEMA
        or report.get("candidate_schema") != THINKING_SCHEMA
        or report.get("status") != "PASS"
        or report.get("backend_executed") is not True
        or report.get("research_only") is not True
        or report.get("accepted") != 10
        or report.get("rejected") != 0
        or report.get("cache_rows") != 10
        or report.get("review_queue_total") != 0
        or report.get("source_count") != 10
        or report.get("human_approvals") is not False
        or report.get("target_side_repairs") is not False
    ):
        errors.append("STAGE3_REPORT_NOT_FULLY_ACCEPTED_OR_PROVEN")

    if (
        restart.get("status") != "PASS"
        or restart.get("quality_status") != "PASS"
        or restart.get("persistence_status") != "PASS"
        or restart.get("accepted") != 10
        or restart.get("required") != 10
        or restart.get("models_loaded_during_restart") is not False
        or any(restart.get(k) for k in (
            "errors", "quality_errors", "persistence_errors"
        ))
    ):
        errors.append("STAGE3_COLD_RESTART_NOT_PROVEN")

    if (
        manifest.get("sha256") != expected_manifest["sha256"]
        or manifest.get("cases") != expected_manifest["cases"]
        or report.get("manifest_sha256") != expected_manifest["sha256"]
        or manifest.get("promotion_evidence") != report.get("promotion_evidence")
    ):
        errors.append("STAGE3_SOURCE_MANIFEST_OR_EVIDENCE_MISMATCH")

    model_rows = report.get("model_provenance") or []
    if (
        len(model_rows) != 1
        or model_rows[0].get("repo_id") != MODEL_REPO
        or model_rows[0].get("revision") != MODEL_REVISION
        or model_rows[0].get("sha256") != MODEL_SHA256
        or model_rows[0].get("reasoning_mode") != "think"
    ):
        errors.append("STAGE3_PINNED_THINKING_MODEL_NOT_PROVEN")

    if not isinstance(cases, list):
        errors.append("STAGE3_CASE_ROWS_MISSING")
        cases = []
    case_ids = [
        c.get("case") for c in cases if isinstance(c, dict)
    ]
    if len(cases) != 10 or len(set(case_ids)) != 10 or set(case_ids) != set(known):
        errors.append("STAGE3_CASE_COUNT_OR_IDS_CHANGED")

    for row in cases:
        if not isinstance(row, dict):
            errors.append("STAGE3_CASE_ROW_MALFORMED")
            continue
        case_id = row.get("case")
        if case_id not in known:
            continue
        translated = row.get("translated")
        if (
            row.get("status") != "accepted"
            or row.get("source") != known[case_id]
            or not isinstance(translated, str)
            or not translated.strip()
            or not row.get("raw_model_attempts")
        ):
            errors.append("STAGE3_CASE_SOURCE_OUTPUT_OR_RECEIPT_CHANGED:" + case_id)
            continue
        digest = hashlib.sha256(translated.encode("utf-8")).hexdigest()
        if row.get("sha256") != digest:
            errors.append("STAGE3_TRANSLATION_SHA256_MISMATCH:" + case_id)
        folded = _fold(translated)

        if case_id == "rainy_meeting":
            # 駅の前 means *in front of* the station, not merely at the station.
            front = re.search(
                r"\b(?:frente\s+a|frente\s+de|enfrente\s+de|"
                r"delante\s+de|ante)\s+la\s+estacion\b",
                folded,
            )
            if not front:
                hard.append({
                    "case": case_id,
                    "code": "STATION_FRONT_LOCATION_OMITTED",
                    "evidence": "駅の前 specifies a position in front of the station",
                })

        if case_id == "sister_homework":
            # Singular 'pienso ir' cannot agree with bare plural 'juntos'.
            singular_intent_with_plural = re.search(
                r"\b(?:pienso|planeo|pretendo)\s+"
                r"(?:ir|salir|volver)\b.{0,85}\bjunt[oa]s?\b",
                folded,
            )
            if singular_intent_with_plural:
                hard.append({
                    "case": case_id,
                    "code": "SINGULAR_INTENT_PLURAL_ADVERB_DISAGREEMENT",
                    "evidence": "Use 'ir con ella' or plural 'iremos juntos/as'",
                })
            if re.search(r"\bla\s+hermana\s+menor\b", folded):
                review.append({
                    "case": case_id,
                    "code": "SIBLING_RELATIONSHIP_REFERENCE_REVIEW",
                    "evidence": "妹 lacks overt possessive in isolation; resolve narrative perspective",
                })

        if case_id == "red_and_blue_apples":
            # 青いリンゴ is usually a green/unripe apple in ordinary Japanese.
            # In a fantasy-game setting a literally blue fruit remains possible.
            if re.search(r"\bmanzan\w*\s+azul(?:es)?\b", folded):
                review.append({
                    "case": case_id,
                    "code": "AOI_APPLE_BLUE_VS_GREEN_CONTEXT_REVIEW",
                    "evidence": "青いリンゴ can be green apples; check visual/narrative context",
                })

    status = (
        "BLOCKED" if errors or hard
        else "BILINGUAL_REVIEW_REQUIRED" if review
        else "AUTOMATED_SCREEN_PASS_HUMAN_REVIEW_PENDING"
    )
    return {
        "schema": SCHEMA,
        "status": status,
        "source_set": "ten_case_public_research_holdout",
        "stage3_automatic_acceptance": report.get("accepted"),
        "stage3_automatic_result_preserved": True,
        "errors": errors,
        "hard_issues": hard,
        "context_review_issues": review,
        "human_review_completed": False,
        "promotion_approved": False,
        "note": "Post-hoc screen on published cases; not independent blind or professional approval",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--restart-proof", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    proof = json.loads(args.restart_proof.read_text(encoding="utf-8"))
    manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    result = screen_stage3(report, proof, manifest)
    result["evidence_sha256"] = {
        "report": hashlib.sha256(args.report.read_bytes()).hexdigest(),
        "restart_proof": hashlib.sha256(args.restart_proof.read_bytes()).hexdigest(),
        "source_manifest": hashlib.sha256(args.source_manifest.read_bytes()).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "STAGE4_BILINGUAL_SCREEN "
        + json.dumps({
            "status": result["status"],
            "historical_automatic_score": report.get("accepted"),
            "hard_issues": result["hard_issues"],
            "context_review_issues": result["context_review_issues"],
            "evidence_errors": result["errors"],
            "promotion_approved": False,
        }, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    # The automated screen may pass, but independent human bilingual sign-off
    # is always a separate requirement before general use or stage promotion.
    return 0 if result["status"] == "AUTOMATED_SCREEN_PASS_HUMAN_REVIEW_PENDING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
