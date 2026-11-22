"""Post-hoc, read-only semantic diagnostic of original Qwen3-8B neural output.

Never repair/rewrite model text or claim professional translation approval.
Known-case detectors are retrospective, not a replacement for blind evaluation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from tools.stage3_readiness import source_only_manifest
from tools.stage4_rpg_stress_cases import STRESS_CASES, manifest as rpg_manifest
from tools.unseen_holdout import HOLDOUT_CASES


def fold(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(c)
    )


def known_risks(group: str, case: str, translated: str) -> tuple[list, list]:
    target = fold(translated)
    hard, review = [], []
    def add(where, code, why):
        where.append({"source_set": group, "case": case,
                      "code": code, "evidence": why})
    if group == "calibration" and case == "sister_homework":
        if re.search(r"\b(?:pienso|planeo|pretendo)\s+(?:ir|salir|volver)\b.{0,85}\bjunt[oa]s\b", target):
            add(hard, "SINGULAR_INTENT_PLURAL_JUNTOS",
                "First-person singular 'pienso ir' with plural 'juntos' is ungrammatical")
    if group == "calibration" and case == "red_and_blue_apples":
        if re.search(r"\bmanzan\w*\s+azul(?:es)?\b", target):
            add(review, "AOI_APPLE_COLOR_CONTEXT",
                "青いリンゴ normally refers to green apples; a fantasy color needs context")
    if group == "rpg" and case == "speaker_item_owner":
        if re.search(r"\b(?:devuelvelo|devuelvanlo|regresalo|retornalo)\b", target):
            add(hard, "SWORD_OBJECT_GENDER_DISAGREEMENT",
                "The explicit noun 'espada' is feminine, but 'devuélvelo' has masculine agreement")
    if group == "rpg" and case == "reported_speech_no_arrival":
        if re.search(r"\b(?:aun|todavia)\s+no\s+ha\s+visto\s+a\s+nadie\b", target):
            add(hard, "SEER_SEEN_ROLE_INVERSION",
                "まだ誰も彼を見ていません: nobody has seen him, NOT he has seen nobody")
    if group == "rpg" and case == "appointment_rebooked":
        if re.search(r"\breserva\s+de\s+martes\b", target):
            add(review, "WEEKDAY_PREPOSITION_FLUENCY_REVIEW",
                "Check 'reserva de martes' against idiomatic 'reserva del martes'")
    if group == "rpg" and case == "quest_item_quantities":
        if re.search(r"\bpildoras?\b", target):
            add(review, "KUSURI_FORM_SPECIFICITY_REVIEW",
                "薬 does not specify pill form; visual or narrative context needed")
    return hard, review


def check_source_evidence(label, report, proof, manifest, expected, known, expected_status, accepted_field):
    errors = []
    rows = report.get("cases") or []
    ids = [r.get("case") for r in rows if isinstance(r, dict)]
    if (len(ids) != len(known) or len(set(ids)) != len(known)
        or set(ids) != set(known)):
        errors.append(label + "_CASE_SET_MISMATCH")
    if (manifest.get("sha256") != expected.get("sha256")
        or manifest.get("cases") != expected.get("cases")
        or report.get("manifest_sha256") != expected.get("sha256")):
        errors.append(label + "_SOURCE_MANIFEST_MISMATCH")
    if (report.get("status") != expected_status
        or report.get(accepted_field) != len(known) or report.get("rejected") != 0):
        errors.append(label + "_AUTOMATIC_RECEIPT_INVALID")
    if (proof.get("persistence_status") != "PASS"
        or proof.get("models_loaded_during_restart") is not False
        or proof.get("persistence_errors") or proof.get("errors")):
        errors.append(label + "_COLD_RESTART_INVALID")
    for row in rows:
        if not isinstance(row, dict):
            errors.append(label + "_MALFORMED_ROW")
            continue
        cid, value = row.get("case"), row.get("translated")
        if cid not in known:
            errors.append(label + "_UNKNOWN_CASE")
            continue
        if (row.get("source") != known[cid]
            or not isinstance(value, str) or not value.strip()
            or not row.get("raw_model_attempts")):
            errors.append(label + "_RAW_OUTPUT_MISSING:" + cid)
            continue
        if row.get("sha256") != hashlib.sha256(value.encode("utf-8")).hexdigest():
            errors.append(label + "_OUTPUT_HASH_MISMATCH:" + cid)
        required = "accepted" if label == "calibration" else "structurally_accepted"
        if row.get("status") != required:
            errors.append(label + "_ROW_STATUS_CHANGED:" + cid)
    return errors


def audit(cal, cp, cm, cs, rpg, rp, rm):
    errors = check_source_evidence(
        "calibration", cal, cp, cm, source_only_manifest(),
        {c.id: c.japanese for c in HOLDOUT_CASES}, "PASS", "accepted"
    ) + check_source_evidence(
        "rpg", rpg, rp, rm, rpg_manifest(),
        {c.id: c.japanese for c in STRESS_CASES},
        "STRUCTURAL_PASS_BILINGUAL_REVIEW_PENDING", "structurally_accepted"
    )
    if cp.get("status") != "PASS" or cp.get("quality_status") != "PASS":
        errors.append("CALIBRATION_RESTART_QUALITY_FAIL")
    if (rp.get("status") != "STRUCTURAL_PASS_BILINGUAL_REVIEW_PENDING"
        or rp.get("structural_status") != "PASS"):
        errors.append("RPG_RESTART_STRUCTURE_FAIL")
    if cs.get("promotion_approved") is not False or cs.get("human_review_completed") is not False:
        errors.append("CALIBRATION_APPROVAL_RECEIPT_INVALID")
    if rpg.get("professional_quality_approved") is not False or rpg.get("bilingual_review_required") is not True:
        errors.append("RPG_APPROVAL_RECEIPT_INVALID")
    if cal.get("backend_executed") is not True or rpg.get("model_executed") is not True:
        errors.append("REAL_MODEL_EXECUTION_NOT_PROVEN")
    if cal.get("target_side_repairs") is not False or rpg.get("target_repairs") is not False:
        errors.append("ILLEGAL_TARGET_SIDE_REPAIR")
    hard, review = [], []
    for group, rows in (("calibration", cal.get("cases") or []), ("rpg", rpg.get("cases") or [])):
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("translated"), str):
                h, c = known_risks(group, row.get("case"), row["translated"])
                hard.extend(h)
                review.extend(c)
    return {
        "schema": "ja-es-stage5-cross-run-semantic-audit-v1",
        "status": ("EVIDENCE_INVALID" if errors else
                   "SEMANTIC_BLOCKED" if hard else "HUMAN_BILINGUAL_REVIEW_REQUIRED"),
        "source_run_ids": {"calibration": 44908793937, "rpg": 44908983065},
        "calibration_automatic_accepted": cal.get("accepted"),
        "rpg_structurally_accepted": rpg.get("structurally_accepted"),
        "calibration_restart_persistence": cp.get("persistence_status"),
        "rpg_restart_persistence": rp.get("persistence_status"),
        "integrity_errors": errors,
        "hard_semantic_issues": hard,
        "context_review_issues": review,
        "human_bilingual_review_completed": False,
        "independent_blind_benchmark": False,
        "promotion_approved": False,
        "original_model_outputs_unchanged": True,
        "note": "Post-hoc detectors on previously observed neural outputs; NOT comprehensive translation QA"
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    names = ("calibration-report", "calibration-restart", "calibration-manifest",
             "calibration-screen", "rpg-report", "rpg-restart", "rpg-manifest")
    for name in names:
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    files = [getattr(args, name.replace("-", "_")) for name in names]
    result = audit(*(json.loads(path.read_text(encoding="utf-8")) for path in files))
    result["input_sha256"] = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in zip(names, files)
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("STAGE5_SEMANTIC_AUDIT " + json.dumps({
        "status": result["status"],
        "hard_issues": result["hard_semantic_issues"],
        "context_review": result["context_review_issues"],
        "integrity_errors": result["integrity_errors"],
        "promotion_approved": False,
    }, ensure_ascii=True, sort_keys=True), flush=True)
    return 0 if result["status"] == "HUMAN_BILINGUAL_REVIEW_REQUIRED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
