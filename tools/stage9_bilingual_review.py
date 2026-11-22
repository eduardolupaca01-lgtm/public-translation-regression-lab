"""Prepare an auditable human bilingual review packet; never auto-approve."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from tools.stage7_dialogue_cases import STAGE7_CASES, _semantic_errors as s7_errors
from tools.stage8_dialogue_cases import STAGE8_CASES, _semantic_errors as s8_errors

EXPECTED = {6: 16, 7: 12, 8: 12}
LOOKUP = {7: {x.id: x for x in STAGE7_CASES},
          8: {x.id: x for x in STAGE8_CASES}}
STAGE6_WATCH = {
    "two_item_cost_total": "PLURAL_AGREEMENT_IN_COST",
    "two_speakers_ask_sara": "VOLITIVE_AS_IMPERATIVE_REVIEW",
    "search_not_found_roles": "SPANISH_NATURALNESS_REVIEW",
    "rebook_saturday_not_thursday": "ARTICLE_CONTRACTION_REVIEW",
    "permission_changed_today": "PAST_PERMISSION_NUANCE_REVIEW",
    "green_appearance_apple": "BLUE_GREEN_APPLE_CONTEXT_REVIEW",
}

STAGE7_WATCH = {
    "npc_gate_two_variables": "SPANISH_ENTRANCE_NATURALNESS",
    "shop_discount_only_today": "FUTURE_SELLER_OR_OBJECT_AMBIGUITY",
    "rpg_two_speakers_sibling": "SPANISH_TENSE_AGREEMENT",
}
STAGE8_WATCH = {
    "two_speakers_aria_sara": "VOLITIVE_AS_IMPERATIVE_REVIEW",
}

def read_receipts(root: Path):
    reports, proofs, hashes = {}, {}, {}
    for n, expected in EXPECTED.items():
        folder = root / ("stage" + str(n))
        raw = (folder / f"stage{n}-neural-report.json").read_bytes()
        report = json.loads(raw)
        proof = json.loads((folder / f"stage{n}-cold-restart-proof.json")
                           .read_text(encoding="utf-8"))
        if report.get("required") != expected or len(report.get("cases", [])) != expected:
            raise ValueError(f"STAGE{n}_COUNT_OR_REPORT_MISSING")
        if report.get("target_repairs") or report.get("case_specific_prompts"):
            raise ValueError(f"STAGE{n}_UNEXPECTED_REPAIRS")
        reports[n], proofs[n] = report, proof
        hashes[n] = hashlib.sha256(raw).hexdigest()
    return reports, proofs, hashes

def screen_case(stage: int, case_id: str, translated: str) -> list[str]:
    flags = []
    if stage == 6 and case_id in STAGE6_WATCH:
        flags.append(STAGE6_WATCH[case_id])
    if stage in LOOKUP and translated:
        case = LOOKUP[stage].get(case_id)
        if case is None:
            flags.append("SOURCE_CASE_UNKNOWN")
        else:
            flags.extend((s7_errors if stage == 7 else s8_errors)(case, translated))
    return sorted(set(flags))

def review_flags(stage: int, case_id: str, translated: str, status: str) -> list[str]:
    # These are triage notes for a human, NOT new machine approval criteria.
    flags = screen_case(stage, case_id, translated)
    if stage == 7 and case_id in STAGE7_WATCH:
        flags.append(STAGE7_WATCH[case_id])
    if stage == 8 and case_id in STAGE8_WATCH:
        flags.append(STAGE8_WATCH[case_id])
    if status != "rubric_accepted":
        flags.append("HISTORICAL_RUBRIC_REJECTION")
    return sorted(set(flags))

def build_packet(reports: dict, proofs: dict, hashes: dict) -> dict:
    rows = []
    for stage in EXPECTED:
        for case in reports[stage]["cases"]:
            translated = case.get("translated") or ""
            source = case.get("source", "")
            rows.append({
                "id": f"stage{stage}:{case['case']}", "stage": stage,
                "case_id": case["case"], "source_ja": source,
                "candidate_es_419": translated or None,
                "raw_model_attempts": case.get("raw_model_attempts", []),
                "historical_rubric": case.get("status"),
                "posthoc_screen_flags": review_flags(stage, case["case"], translated, case.get("status", "unknown")),
                "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "reviewer": None, "human_fidelity": "pending",
                "human_grammar": "pending", "human_naturalness_es_419": "pending",
                "human_rpg_codes": "pending", "human_decision": "pending",
                "notes": None,
            })
    return {
        "schema": "ja-es-stage9-independent-bilingual-review-packet-v1",
        "evidence_report_sha256_by_stage": {str(n): hashes[n] for n in EXPECTED},
        "rubric_accepted_by_stage": {
            str(n): reports[n].get("rubric_accepted") for n in EXPECTED},
        "persistence_by_stage": {
            str(n): proofs[n].get("persistence_status") for n in EXPECTED},
        "total_items": len(rows), "items": rows,
        "human_review_completed": False, "human_review_approved": False,
        "reviewer_attestation": None,
        "public_synthetic_not_externally_blind": True,
        "automatic_approval_forbidden": True,
        "status": "REVIEW_PACKET_READY_HUMAN_REVIEW_PENDING",
    }

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipts", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    reports, proofs, hashes = read_receipts(args.receipts)
    packet = build_packet(reports, proofs, hashes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2,
                                      sort_keys=True) + "\n", encoding="utf-8")
    print("STAGE9_REVIEW_PACKET " + json.dumps({
        "total_items": packet["total_items"],
        "flagged": sum(bool(x["posthoc_screen_flags"]) for x in packet["items"]),
        "human_approval": False, "status": packet["status"],
    }, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
