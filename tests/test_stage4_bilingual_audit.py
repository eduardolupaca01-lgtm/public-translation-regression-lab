"""Stage4 audit must not confuse keyword success with human quality approval."""
import copy
import hashlib
import unittest

from tools.qwen3_8b_thinking_ja_es_candidate import (
    MODEL_REPO, MODEL_REVISION, MODEL_SHA256,
)
from tools.stage3_readiness import source_only_manifest
from tools.stage4_bilingual_audit import screen_stage3
from tools.stage4_rpg_stress_cases import STRESS_CASES, manifest
from tools.independent_pivot_holdout import INDEPENDENT_CASES
from tools.unseen_holdout import HOLDOUT_CASES

SYNTHETIC_GOOD_TRANSLATIONS = {
    "rainy_meeting": (
        "Mañana por la tarde nos veremos frente a la estación. "
        "Si llueve, esperaré en la entrada de la biblioteca."
    ),
    "closed_shop": "Ayer fui a comprar medicinas, pero la tienda ya estaba cerrada.",
    "sister_homework": (
        "Mi hermana menor todavía no ha terminado la tarea. "
        "Cuando termine, iremos juntas al parque."
    ),
    "red_and_blue_apples": (
        "En esta caja hay tres manzanas rojas. No hay ninguna manzana verde."
    ),
    "teacher_and_children": (
        "El maestro dijo: «Guarden silencio», pero los niños siguieron riéndose."
    ),
    "delayed_train": (
        "Como el tren está retrasado, la reunión comenzará dentro de treinta minutos."
    ),
    "brother_city_roles": "Mi hermano mayor vive en Tokio, pero yo vivo en Osaka.",
    "second_corner": (
        "Siga derecho por esta calle y gire a la derecha en la segunda esquina."
    ),
    "speaker_control_code": r"\N[7] vendrá mañana a las tres de la tarde.",
    "shop_hours_line_break": (
        "Hoy la tienda está cerrada.\r\nMañana abre a las 10 de la mañana."
    ),
}


def synthetic_receipts():
    frozen = source_only_manifest()
    frozen["promotion_evidence"] = {
        "development_report_sha256": "a" * 64,
        "cold_restart_proof_sha256": "b" * 64,
    }
    rows = []
    for sample in HOLDOUT_CASES:
        translated = SYNTHETIC_GOOD_TRANSLATIONS[sample.id]
        rows.append({
            "case": sample.id,
            "source": sample.japanese,
            "status": "accepted",
            "translated": translated,
            "sha256": hashlib.sha256(translated.encode("utf-8")).hexdigest(),
            "raw_model_attempts": [
                {"mode": "fixture", "source_fragment": sample.japanese,
                 "raw_output": translated}
            ],
        })
    report = {
        "schema": "public-qwen3-8b-stage3-ten-dialogue-v1",
        "candidate_schema": "public-qwen3-8b-thinking-ja-es-candidate-v1",
        "status": "PASS",
        "backend_executed": True,
        "research_only": True,
        "accepted": 10,
        "rejected": 0,
        "cache_rows": 10,
        "review_queue_total": 0,
        "source_count": 10,
        "human_approvals": False,
        "target_side_repairs": False,
        "manifest_sha256": frozen["sha256"],
        "promotion_evidence": frozen["promotion_evidence"],
        "model_provenance": [{
            "repo_id": MODEL_REPO, "revision": MODEL_REVISION,
            "sha256": MODEL_SHA256, "reasoning_mode": "think",
        }],
        "cases": rows,
    }
    proof = {
        "status": "PASS",
        "accepted": 10, "required": 10,
        "quality_status": "PASS", "persistence_status": "PASS",
        "models_loaded_during_restart": False,
        "errors": [], "quality_errors": [], "persistence_errors": [],
    }
    return report, proof, frozen


def replace_translation(report, case_id, value):
    row = next(x for x in report["cases"] if x["case"] == case_id)
    row["translated"] = value
    row["sha256"] = hashlib.sha256(value.encode("utf-8")).hexdigest()
    row["raw_model_attempts"][0]["raw_output"] = value


class TestStage4BilingualScreen(unittest.TestCase):
    def test_coherent_synthetic_text_does_not_claim_human_approval(self):
        report, proof, frozen = synthetic_receipts()
        result = screen_stage3(report, proof, frozen)
        self.assertEqual(result["hard_issues"], [])
        self.assertEqual(result["context_review_issues"], [])
        self.assertEqual(result["errors"], [])
        self.assertEqual(
            result["status"], "AUTOMATED_SCREEN_PASS_HUMAN_REVIEW_PENDING"
        )
        self.assertFalse(result["promotion_approved"])
        self.assertFalse(result["human_review_completed"])

    def test_missing_front_and_ungrammatical_joint_intent_are_blocked(self):
        report, proof, frozen = synthetic_receipts()
        replace_translation(
            report, "rainy_meeting",
            "Mañana por la tarde, nos vemos en la estación. "
            "Si llueve, esperaré en la entrada de la biblioteca.",
        )
        replace_translation(
            report, "sister_homework",
            "La hermana menor aún no ha terminado sus tareas. "
            "Cuando termine, pienso ir al parque juntos.",
        )
        replace_translation(
            report, "red_and_blue_apples",
            "En esta caja hay tres manzanas rojas. No hay ninguna manzana azul.",
        )
        result = screen_stage3(report, proof, frozen)
        self.assertEqual(result["status"], "BLOCKED")
        hard = {x["code"] for x in result["hard_issues"]}
        review = {x["code"] for x in result["context_review_issues"]}
        self.assertIn("STATION_FRONT_LOCATION_OMITTED", hard)
        self.assertIn("SINGULAR_INTENT_PLURAL_ADVERB_DISAGREEMENT", hard)
        self.assertIn("AOI_APPLE_BLUE_VS_GREEN_CONTEXT_REVIEW", review)
        self.assertIn("SIBLING_RELATIONSHIP_REFERENCE_REVIEW", review)
        self.assertFalse(result["promotion_approved"])

    def test_missing_or_forged_receipts_cannot_pass_quality_screen(self):
        report, proof, frozen = synthetic_receipts()
        report["cases"][0]["translated"] = "Alterado sin actualizar comprobante."
        result = screen_stage3(report, proof, frozen)
        self.assertIn("STAGE3_TRANSLATION_SHA256_MISMATCH:rainy_meeting",
                      result["errors"])
        report, proof, frozen = synthetic_receipts()
        proof["persistence_status"] = "FAIL"
        self.assertIn("STAGE3_COLD_RESTART_NOT_PROVEN",
                      screen_stage3(report, proof, frozen)["errors"])
        report, proof, frozen = synthetic_receipts()
        report["cases"].pop()
        self.assertIn("STAGE3_CASE_COUNT_OR_IDS_CHANGED",
                      screen_stage3(report, proof, frozen)["errors"])

    def test_ambiguity_is_not_silently_approved(self):
        report, proof, frozen = synthetic_receipts()
        replace_translation(report, "red_and_blue_apples",
            "No hay ninguna manzana azul. La caja tiene tres manzanas rojas.")
        result = screen_stage3(report, proof, frozen)
        self.assertEqual(result["status"], "BILINGUAL_REVIEW_REQUIRED")
        self.assertFalse(result["promotion_approved"])

    def test_next_stage_cases_are_source_only_and_nonoverlapping(self):
        out = manifest()
        self.assertEqual(out["count"], 12)
        self.assertTrue(out["source_only"])
        self.assertFalse(out["model_inference_executed"])
        self.assertEqual(len({c.id for c in STRESS_CASES}), 12)
        all_old = {c.japanese for c in HOLDOUT_CASES}
        all_old.update(c.japanese for c in INDEPENDENT_CASES)
        self.assertFalse({c.japanese for c in STRESS_CASES} & all_old)
        self.assertTrue(any("\\N[" in c.japanese for c in STRESS_CASES))
        self.assertTrue(any("\\V[" in c.japanese for c in STRESS_CASES))
        self.assertTrue(any("\r\n" in c.japanese for c in STRESS_CASES))
        self.assertNotIn('"translated"', str(out["cases"]))


if __name__ == "__main__":
    unittest.main()
