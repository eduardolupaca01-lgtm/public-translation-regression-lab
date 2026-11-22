"""Fail-closed final integration: source integrity and independent signoff checks.

This command never modifies a PR, merges, publishes, or fabricates human approval.
The approval input must match original immutable reports, their source hashes,
and an independent GitHub APPROVED review for the current PR head.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

from tools.stage9_bilingual_review import EXPECTED, read_receipts, screen_case, review_flags

REVIEWED_PACKET_PATH = "reviews/stage9-independent-reviewed-packet.json"
FROZEN_RUNS = {"6": "44931094612", "7": "44942504944", "8": "44961618206"}
REVIEW_DIMENSIONS = (
    "human_fidelity",
    "human_grammar",
    "human_naturalness_es_419",
    "human_rpg_codes",
)
OWNER_GITHUB_LOGIN = "eduardolupaca01-lgtm"


def _packet_integrity_blockers(reports: dict, packet: dict, hashes: dict) -> list[str]:
    """Check every review record against the originals, not just the total."""
    faults = []
    if packet.get("schema") != "ja-es-stage9-independent-bilingual-review-packet-v1":
        faults.append("STAGE9_PACKET_SCHEMA_UNRECOGNIZED")
    if packet.get("public_synthetic_not_externally_blind") is not True:
        faults.append("STAGE9_SYNTHETIC_SCOPE_DECLARATION_CHANGED")
    if packet.get("automatic_approval_forbidden") is not True:
        faults.append("STAGE9_AUTOMATIC_APPROVAL_POLICY_CHANGED")
    if packet.get("source_run_ids_by_stage") != FROZEN_RUNS:
        faults.append("STAGE9_FROZEN_RUN_PROVENANCE_MISMATCH")
    if packet.get("evidence_report_sha256_by_stage") != {
        str(stage): hashes[stage] for stage in EXPECTED
    }:
        faults.append("STAGE9_REPORT_HASH_SET_MISMATCH")

    expected = {}
    for stage in EXPECTED:
        for case in reports[stage]["cases"]:
            key = f"stage{stage}:{case['case']}"
            if key in expected:
                faults.append("STAGE9_ORIGINAL_CASE_ID_DUPLICATE")
            expected[key] = (stage, case)

    rows = packet.get("items")
    if not isinstance(rows, list) or len(rows) != sum(EXPECTED.values()):
        return sorted(set(faults + ["STAGE9_PACKET_INCOMPLETE"]))
    actual = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            faults.append("STAGE9_PACKET_MALFORMED_CASE_ROW")
            continue
        case_id = row["id"]
        if case_id in actual:
            faults.append("STAGE9_PACKET_DUPLICATE_CASE_ID")
        actual[case_id] = row
    if set(actual) != set(expected) or len(actual) != len(expected):
        faults.append("STAGE9_PACKET_CASE_SET_MISMATCH")
    for case_id in set(actual).intersection(expected):
        stage, original = expected[case_id]
        row = actual[case_id]
        source = original.get("source", "")
        translated = original.get("translated") or ""
        if (row.get("stage") != stage
                or row.get("case_id") != original["case"]
                or row.get("source_ja") != source
                or (row.get("candidate_es_419") or "") != translated
                or row.get("historical_rubric") != original.get("status")
                or row.get("posthoc_screen_flags") != review_flags(
                    stage, original["case"], translated, original.get("status", "unknown")
                )
                or row.get("raw_model_attempts") != original.get("raw_model_attempts", [])
                or row.get("source_sha256") != hashlib.sha256(
                    source.encode("utf-8")
                ).hexdigest()):
            faults.append(f"STAGE9_ORIGINAL_CASE_EVIDENCE_CHANGED:{case_id}")
    return sorted(set(faults))


def _reviewer_blockers(
    packet: dict, hashes: dict,
    verified_github_reviews: list[dict] | None,
    expected_head_sha: str | None,
) -> list[str]:
    """No self-asserted review counts as an authenticated human approval."""
    blockers = []
    rows = packet.get("items")
    rows = rows if isinstance(rows, list) else []
    att = packet.get("reviewer_attestation")
    att = att if isinstance(att, dict) else {}
    reviewer = att.get("reviewer_github_login")
    if not isinstance(reviewer, str) or not reviewer.strip():
        blockers.append("STAGE9_REVIEWER_ATTESTATION_MISSING")
        reviewer = None
    elif reviewer.casefold() == OWNER_GITHUB_LOGIN:
        blockers.append("STAGE9_REVIEWER_NOT_INDEPENDENT")

    if att.get("evidence_report_sha256_by_stage") != {
        str(stage): hashes[stage] for stage in EXPECTED
    }:
        blockers.append("STAGE9_REVIEWER_ATTESTED_HASHES_MISSING_OR_MISMATCHED")
    if att.get("source_run_ids_by_stage") != FROZEN_RUNS:
        blockers.append("STAGE9_REVIEWER_RUNS_MISSING_OR_MISMATCHED")
    if att.get("independent_bilingual_review_confirmed") is not True:
        blockers.append("STAGE9_INDEPENDENT_BILINGUAL_QUALIFICATION_NOT_ATTESTED")
    signed_at = att.get("reviewed_at_utc")
    try:
        signed_date = datetime.fromisoformat(signed_at.replace("Z", "+00:00"))
        if signed_date.tzinfo is None:
            raise ValueError("missing UTC offset")
    except (ValueError, TypeError, AttributeError):
        blockers.append("STAGE9_REVIEWER_TIMESTAMP_INVALID")

    if packet.get("human_review_completed") is not True:
        blockers.append("STAGE9_INDEPENDENT_HUMAN_REVIEW_PENDING")
    if packet.get("human_review_approved") is not True:
        blockers.append("STAGE9_INDEPENDENT_BILINGUAL_APPROVAL_MISSING")
    if (len(rows) != sum(EXPECTED.values())
            or any(row.get("human_decision") != "approved" for row in rows
                   if isinstance(row, dict))):
        blockers.append("STAGE9_CASE_LEVEL_REVIEW_INCOMPLETE")

    for row in rows:
        if not isinstance(row, dict):
            blockers.append("STAGE9_CASE_LEVEL_REVIEW_INCOMPLETE")
            continue
        if any(row.get(dimension) != "approved" for dimension in REVIEW_DIMENSIONS):
            blockers.append("STAGE9_REVIEW_DIMENSIONS_NOT_ALL_APPROVED")
        if not reviewer or (row.get("reviewer") or "").casefold() != reviewer.casefold():
            blockers.append("STAGE9_CASE_REVIEWER_IDENTITY_MISMATCH")
        if row.get("posthoc_screen_flags") and not str(row.get("notes") or "").strip():
            blockers.append("STAGE9_FLAGGED_CASE_LACKS_REVIEWER_NOTES")

    latest: dict[str, dict] = {}
    for item in verified_github_reviews or []:
        if not isinstance(item, dict):
            continue
        who = item.get("user_login") or (item.get("user") or {}).get("login")
        if not isinstance(who, str):
            continue
        if item.get("commit_id") != expected_head_sha:
            continue
        prev = latest.get(who.casefold())
        if prev is None or (item.get("submitted_at") or "") >= (prev.get("submitted_at") or ""):
            latest[who.casefold()] = item
    approved = (
        reviewer is not None
        and isinstance(expected_head_sha, str) and len(expected_head_sha) == 40
        and reviewer.casefold() in latest
        and latest[reviewer.casefold()].get("state") == "APPROVED"
        and reviewer.casefold() != OWNER_GITHUB_LOGIN
    )
    if not approved:
        blockers.append("STAGE10_CURRENT_HEAD_INDEPENDENT_GITHUB_APPROVAL_NOT_VERIFIED")
    return sorted(set(blockers))


def assess(
    reports: dict, proofs: dict, packet: dict, hashes: dict,
    verified_github_reviews: list[dict] | None = None,
    expected_head_sha: str | None = None,
) -> dict:
    blockers: list[str] = []
    results: dict[str, str] = {}
    for stage, required in EXPECTED.items():
        report, proof = reports[stage], proofs[stage]
        good = (
            report.get("model_executed") is True
            and report.get("rubric_accepted") == required
            and report.get("rejected") == 0
            and report.get("cache_rows") == required
            and report.get("review_queue_pending") == 0
            and report.get("case_specific_prompts") is False
            and report.get("target_repairs") is False
            and proof.get("persistence_status") == "PASS"
            and proof.get("rubric_status") == "PASS"
            and proof.get("models_loaded_during_restart") is False
        )
        results[str(stage)] = "PASS" if good else "FAIL"
        if not good:
            blockers.append(f"STAGE{stage}_QUALITY_OR_PERSISTENCE_NOT_READY")
        if packet.get("evidence_report_sha256_by_stage", {}).get(str(stage)) != hashes[stage]:
            blockers.append(f"STAGE{stage}_EVIDENCE_HASH_MISMATCH")
        for case in report["cases"]:
            if case.get("status") == "rubric_accepted" and stage in (7, 8):
                flags = screen_case(stage, case["case"], case.get("translated", ""))
                if flags:
                    blockers.append(
                        f"STAGE{stage}_POSTHOC_SEMANTIC_ERROR:{case['case']}:"
                        + ",".join(flags)
                    )
    blockers.extend(_packet_integrity_blockers(reports, packet, hashes))
    blockers.extend(_reviewer_blockers(
        packet, hashes, verified_github_reviews, expected_head_sha
    ))
    if packet.get("total_items") != sum(EXPECTED.values()):
        blockers.append("STAGE9_PACKET_INCOMPLETE")
    blockers = sorted(set(blockers))
    return {
        "schema": "ja-es-stage10-final-gate-v2",
        "status": "HOLD" if blockers else "READY_FOR_MANUAL_PR_REVIEW",
        "automated_checks": results,
        "blockers": blockers,
        "automatic_merge_or_publication_permitted": False,
        "merge_performed": False,
        "manual_pr_and_main_review_required": True,
        "public_synthetic_not_externally_blind": True,
        "human_review_verified": not any(x.startswith("STAGE9_") or
                                         x.startswith("STAGE10_CURRENT_HEAD") for x in blockers),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipts", type=Path, required=True)
    p.add_argument("--stage9-packet", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--github-reviews-jsonl", type=Path)
    p.add_argument("--expected-head-sha", type=str)
    p.add_argument("--require-ready", action="store_true")
    args = p.parse_args()
    reports, proofs, hashes = read_receipts(args.receipts)
    packet = json.loads(args.stage9_packet.read_text(encoding="utf-8"))
    reviews = None
    if args.github_reviews_jsonl:
        reviews = [
            json.loads(line) for line in
            args.github_reviews_jsonl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    result = assess(
        reports, proofs, packet, hashes,
        verified_github_reviews=reviews,
        expected_head_sha=args.expected_head_sha,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print("STAGE10_GATE " + json.dumps(result, sort_keys=True))
    return 1 if args.require_ready and result["status"] == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
