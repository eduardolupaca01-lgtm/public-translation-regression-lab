"""RPG semantic audit must flag role inversion even after structural 12/12."""
from __future__ import annotations

import hashlib
import unittest

from tools.qwen3_8b_thinking_ja_es_candidate import MODEL_REPO, MODEL_REVISION, MODEL_SHA256
from tools.stage4_rpg_semantic_audit import audit_receipts
from tools.stage4_rpg_stress_cases import STRESS_CASES, manifest
from tools.stage4_source_complete_candidate import GENERATION_VARIANT, SOURCE_PROMPT_SHA256


def synthetic_receipts():
    frozen = manifest()
    entries = []
    for case in STRESS_CASES:
        translation = "Traducción sintética sin garantías."
        entries.append({
            "case": case.id,
            "source": case.japanese,
            "status": "structurally_accepted",
            "translated": translation,
            "sha256": hashlib.sha256(translation.encode("utf-8")).hexdigest(),
            "raw_model_attempts": [{
                "source_fragment": case.japanese,
                "raw_output": translation,
                "mode": "fixture",
            }],
        })
    report = {
        "schema": "ja-es-stage4-rpg-exploratory-neural-v1",
        "status": "STRUCTURAL_PASS_BILINGUAL_REVIEW_PENDING",
        "model_executed": True,
        "structurally_accepted": len(STRESS_CASES),
        "rejected": 0,
        "cache_rows": len(STRESS_CASES),
        "review_queue_total": 0,
        "professional_quality_approved": False,
        "human_approvals": False,
        "reference_spanish_provided_to_model": False,
        "target_repairs": False,
        "generation_variant": GENERATION_VARIANT,
        "translation_system_prompt_sha256": SOURCE_PROMPT_SHA256,
        "model_provenance": [{
            "repo_id": MODEL_REPO,
            "revision": MODEL_REVISION,
            "sha256": MODEL_SHA256,
            "reasoning_mode": "think",
        }],
        "manifest_sha256": frozen["sha256"],
        "cases": entries,
    }
    proof = {
        "status": "STRUCTURAL_PASS_BILINGUAL_REVIEW_PENDING",
        "structural_status": "PASS",
        "persistence_status": "PASS",
        "required": len(STRESS_CASES),
        "structurally_accepted": len(STRESS_CASES),
        "models_loaded_during_restart": False,
        "errors": [],
        "quality_errors": [],
        "persistence_errors": [],
    }
    return report, proof, frozen


def overwrite(report, case_id, translation):
    row = next(x for x in report["cases"] if x["case"] == case_id)
    row["translated"] = translation
    row["sha256"] = hashlib.sha256(translation.encode("utf-8")).hexdigest()
    row["raw_model_attempts"][0]["raw_output"] = translation


class TestRpgSemanticAudit(unittest.TestCase):
    def test_reversing_who_saw_whom_is_not_a_quality_pass(self):
        report, proof, frozen = synthetic_receipts()
        overwrite(
            report, "reported_speech_no_arrival",
            "Él dijo que vendría. Sin embargo, aún no ha visto a nadie.",
        )
        outcome = audit_receipts(report, proof, frozen)
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertIn(
            "REVERSED_WITNESS_ACTOR_AND_OBJECT",
            {x["code"] for x in outcome["material_semantic_errors"]},
        )
        self.assertFalse(outcome["production_or_stage_promotion_approved"])

    def test_feminine_sword_must_not_take_masculine_pronoun(self):
        report, proof, frozen = synthetic_receipts()
        overwrite(
            report, "speaker_item_owner",
            r"\N[3]「Esta espada no es mía. Devuélvelo a \N[5].」",
        )
        outcome = audit_receipts(report, proof, frozen)
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertIn(
            "FEMININE_SWORD_MASCULINE_OBJECT_PRONOUN",
            {x["code"] for x in outcome["material_semantic_errors"]},
        )

    def test_faithful_role_does_not_trigger_inversion_false_positive(self):
        report, proof, frozen = synthetic_receipts()
        overwrite(
            report, "reported_speech_no_arrival",
            "Él dijo que vendría, pero nadie lo ha visto todavía.",
        )
        overwrite(
            report, "speaker_item_owner",
            r"\N[3]「Esta espada no es mía. Devuélvela a \N[5].」",
        )
        outcome = audit_receipts(report, proof, frozen)
        self.assertFalse(outcome["material_semantic_errors"])
        self.assertFalse(outcome["production_or_stage_promotion_approved"])

    def test_tampered_receipt_or_failed_restart_is_blocked(self):
        report, proof, frozen = synthetic_receipts()
        report["cases"][0]["translated"] = "Alterado."
        self.assertIn(
            "RPG_OUTPUT_SHA256_CHANGED:speaker_item_owner",
            audit_receipts(report, proof, frozen)["evidence_errors"],
        )
        report, proof, frozen = synthetic_receipts()
        proof["persistence_status"] = "FAIL"
        self.assertIn(
            "RPG_COLD_RESTART_EVIDENCE_INCOMPLETE",
            audit_receipts(report, proof, frozen)["evidence_errors"],
        )


if __name__ == "__main__":
    unittest.main()
