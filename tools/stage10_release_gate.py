"""Fail-closed research release gate; never merge or publish automatically."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from tools.stage9_bilingual_review import EXPECTED, read_receipts, screen_case

def assess(reports: dict, proofs: dict, packet: dict, hashes: dict) -> dict:
    blockers = []
    results = {}
    for stage, required in EXPECTED.items():
        r, p = reports[stage], proofs[stage]
        good = (
            r.get("model_executed") is True
            and r.get("rubric_accepted") == required and r.get("rejected") == 0
            and r.get("cache_rows") == required
            and r.get("review_queue_pending") == 0
            and r.get("case_specific_prompts") is False
            and r.get("target_repairs") is False
            and p.get("persistence_status") == "PASS"
            and p.get("rubric_status") == "PASS"
            and p.get("models_loaded_during_restart") is False
        )
        results[str(stage)] = "PASS" if good else "FAIL"
        if not good:
            blockers.append(f"STAGE{stage}_QUALITY_OR_PERSISTENCE_NOT_READY")
        if packet.get("evidence_report_sha256_by_stage", {}).get(str(stage)) != hashes[stage]:
            blockers.append(f"STAGE{stage}_EVIDENCE_HASH_MISMATCH")
        for case in r["cases"]:
            if case.get("status") == "rubric_accepted" and stage in (7, 8):
                flags = screen_case(stage, case["case"], case.get("translated", ""))
                if flags:
                    blockers.append(f"STAGE{stage}_POSTHOC_SEMANTIC_ERROR:{case['case']}:"
                                    + ",".join(flags))
    if packet.get("total_items") != sum(EXPECTED.values()) or len(packet.get("items", [])) != 40:
        blockers.append("STAGE9_PACKET_INCOMPLETE")
    if packet.get("human_review_completed") is not True:
        blockers.append("STAGE9_INDEPENDENT_HUMAN_REVIEW_PENDING")
    if packet.get("human_review_approved") is not True:
        blockers.append("STAGE9_INDEPENDENT_BILINGUAL_APPROVAL_MISSING")
    if not packet.get("reviewer_attestation"):
        blockers.append("STAGE9_REVIEWER_ATTESTATION_MISSING")
    if any(x.get("human_decision") != "approved" for x in packet.get("items", [])):
        blockers.append("STAGE9_CASE_LEVEL_REVIEW_INCOMPLETE")
    blockers = sorted(set(blockers))
    return {
        "schema": "ja-es-stage10-final-gate-v1",
        "status": "HOLD" if blockers else "READY_FOR_MANUAL_PR_REVIEW",
        "automated_checks": results, "blockers": blockers,
        "automatic_merge_or_publication_permitted": False,
        "merge_performed": False,
        "manual_pr_and_main_review_required": True,
    }

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipts", type=Path, required=True)
    p.add_argument("--stage9-packet", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--require-ready", action="store_true")
    a = p.parse_args()
    reports, proofs, hashes = read_receipts(a.receipts)
    packet = json.loads(a.stage9_packet.read_text(encoding="utf-8"))
    result = assess(reports, proofs, packet, hashes)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                   indent=2) + "\n", encoding="utf-8")
    print("STAGE10_GATE " + json.dumps(result, sort_keys=True))
    return 1 if a.require_ready and result["status"] == "HOLD" else 0

if __name__ == "__main__":
    raise SystemExit(main())
