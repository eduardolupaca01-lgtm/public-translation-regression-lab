"""Post-hoc source-aware linguistic audit of the original twelve RPG outputs.

The historic 12/12 structurally accepted receipts are never rewritten.
This screen checks errors that purely structural checks did not catch.
A passing screen still requires independent bilingual review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from tools.qwen3_8b_thinking_ja_es_candidate import MODEL_REPO, MODEL_REVISION, MODEL_SHA256
from tools.stage4_rpg_stress_cases import STRESS_CASES, manifest
from tools.stage4_source_complete_candidate import GENERATION_VARIANT, SOURCE_PROMPT_SHA256


SCHEMA = "ja-es-stage4-rpg-source-aware-audit-v1"


def fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in value if not unicodedata.combining(c))


def audit_receipts(report: dict, proof: dict, frozen: dict) -> dict:
    errors: list[str] = []
    hard: list[dict[str, str]] = []
    context: list[dict[str, str]] = []
    canonical = manifest()
    by_id = {case.id: case for case in STRESS_CASES}
    rows = report.get("cases") if isinstance(report.get("cases"), list) else []

    if (
        report.get("schema") != "ja-es-stage4-rpg-exploratory-neural-v1"
        or report.get("status") != "STRUCTURAL_PASS_BILINGUAL_REVIEW_PENDING"
        or report.get("model_executed") is not True
        or report.get("structurally_accepted") != len(by_id)
        or report.get("rejected") != 0
        or report.get("cache_rows") != len(by_id)
        or report.get("review_queue_total") != 0
        or report.get("professional_quality_approved") is not False
        or report.get("human_approvals") is not False
        or report.get("reference_spanish_provided_to_model") is not False
        or report.get("target_repairs") is not False
    ):
        errors.append("RPG_HISTORIC_STRUCTURAL_EVIDENCE_INCOMPLETE")

    if (
        proof.get("status") != "STRUCTURAL_PASS_BILINGUAL_REVIEW_PENDING"
        or proof.get("structural_status") != "PASS"
        or proof.get("persistence_status") != "PASS"
        or proof.get("required") != len(by_id)
        or proof.get("structurally_accepted") != len(by_id)
        or proof.get("models_loaded_during_restart") is not False
        or any(proof.get(k) for k in ("errors", "quality_errors", "persistence_errors"))
    ):
        errors.append("RPG_COLD_RESTART_EVIDENCE_INCOMPLETE")

    if (
        frozen.get("sha256") != canonical["sha256"]
        or frozen.get("cases") != canonical["cases"]
        or report.get("manifest_sha256") != canonical["sha256"]
    ):
        errors.append("RPG_JAPANESE_SOURCE_MANIFEST_CHANGED")

    models = report.get("model_provenance") or []
    if (
        len(models) != 1
        or models[0].get("repo_id") != MODEL_REPO
        or models[0].get("revision") != MODEL_REVISION
        or models[0].get("sha256") != MODEL_SHA256
        or models[0].get("reasoning_mode") != "think"
        or report.get("generation_variant") != GENERATION_VARIANT
        or report.get("translation_system_prompt_sha256") != SOURCE_PROMPT_SHA256
    ):
        errors.append("RPG_MODEL_OR_PROMPT_PROVENANCE_CHANGED")

    identifiers = [x.get("case") for x in rows if isinstance(x, dict)]
    if (
        len(rows) != len(by_id)
        or len(identifiers) != len(by_id)
        or set(identifiers) != set(by_id)
        or len(set(identifiers)) != len(by_id)
    ):
        errors.append("RPG_CASES_MISSING_DUPLICATED_OR_CHANGED")

    for row in rows:
        if not isinstance(row, dict):
            errors.append("RPG_MALFORMED_ROW")
            continue
        case_id = row.get("case")
        if case_id not in by_id:
            errors.append("RPG_UNKNOWN_CASE")
            continue
        value = row.get("translated")
        if (
            row.get("source") != by_id[case_id].japanese
            or row.get("status") != "structurally_accepted"
            or not isinstance(value, str)
            or not value.strip()
            or not row.get("raw_model_attempts")
        ):
            errors.append("RPG_SOURCE_OR_OUTPUT_RECEIPT_INVALID:" + case_id)
            continue
        if row.get("sha256") != hashlib.sha256(value.encode("utf-8")).hexdigest():
            errors.append("RPG_OUTPUT_SHA256_CHANGED:" + case_id)
        spanish = fold(value)

        if case_id == "speaker_item_owner":
            # In 'esta espada ... devuelvelo', the object is feminine singular.
            if re.search(r"\b(?:devuelvelo|devuelvalo|devolvelo|regresalo)\b", spanish):
                hard.append({
                    "case": case_id,
                    "code": "FEMININE_SWORD_MASCULINE_OBJECT_PRONOUN",
                    "reason": "The returned sword is feminine (espada); 'devuélvelo' disagrees",
                })
        elif case_id == "reported_speech_no_arrival":
            # 誰も彼を見ていません: nobody saw HIM, not he saw nobody.
            if re.search(
                r"\b(?:aun|todavia)?\s*no\s+(?:ha|han|habia|habian|vio|ve|vieron)"
                r"\s+visto\s+a\s+nadie\b|\bno\s+ha\s+visto\s+a\s+nadie\b",
                spanish,
            ):
                hard.append({
                    "case": case_id,
                    "code": "REVERSED_WITNESS_ACTOR_AND_OBJECT",
                    "reason": "Nobody has seen him; 'he has not seen anyone' reverses roles",
                })
            elif not re.search(
                r"\b(?:nadie|ninguna\s+persona)\b.{0,70}"
                r"\b(?:visto|vio|vieron|ve|observado|encontrado)\b|"
                r"\bno\s+(?:lo|le)\s+ha\s+visto\s+nadie\b",
                spanish,
            ):
                context.append({
                    "case": case_id,
                    "code": "WITNESS_ROLE_REQUIRES_BILINGUAL_REVIEW",
                    "reason": "Confirm that nobody has seen the mentioned man",
                })
        elif case_id == "rain_branching":
            if re.search(r"\bpase\s+por\s+(?:el|un)\s+puente\b", spanish):
                context.append({
                    "case": case_id,
                    "code": "BRIDGE_CROSSING_VS_PASSING_REVIEW",
                    "reason": "渡って denotes crossing the bridge, not merely passing by it",
                })
        elif case_id == "quest_item_quantities":
            if "pildora" in spanish:
                context.append({
                    "case": case_id,
                    "code": "MEDICINE_ITEM_FORM_NOT_SPECIFIED",
                    "reason": "薬 does not specify pills versus potions; inspect game item context",
                })

    status = (
        "BLOCKED" if errors or hard
        else "CONTEXT_REVIEW_REQUIRED" if context
        else "AUTOMATED_SEMANTIC_SCREEN_PASS_REVIEW_PENDING"
    )
    return {
        "schema": SCHEMA,
        "status": status,
        "historic_structural_result_preserved": report.get("structurally_accepted"),
        "evidence_errors": errors,
        "material_semantic_errors": hard,
        "contextual_review_flags": context,
        "original_model_outputs_untouched": True,
        "independent_bilingual_review_completed": False,
        "production_or_stage_promotion_approved": False,
        "note": "Post-hoc check on public research cases, not blind validation",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raw_files = {
        "report": args.report.read_bytes(),
        "proof": args.proof.read_bytes(),
        "manifest": args.manifest.read_bytes(),
    }
    result = audit_receipts(
        json.loads(raw_files["report"]),
        json.loads(raw_files["proof"]),
        json.loads(raw_files["manifest"]),
    )
    result["receipt_digests"] = {
        key: hashlib.sha256(value).hexdigest()
        for key, value in raw_files.items()
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "STAGE4_RPG_SEMANTIC_AUDIT "
        + json.dumps({
            "status": result["status"],
            "historic_score": result["historic_structural_result_preserved"],
            "material_errors": result["material_semantic_errors"],
            "context_flags": result["contextual_review_flags"],
            "evidence_errors": result["evidence_errors"],
            "promotion_approved": False,
        }, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    # Never return success for a flawed source-faithfulness result.
    return 0 if result["status"] == "AUTOMATED_SEMANTIC_SCREEN_PASS_REVIEW_PENDING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
