"""New Japanese sources, semantic rubric failures and cold restart remain honest."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.stage5_dialogue_cases import (
    STAGE5_CASES, _semantic_errors, manifest, source_sets_disjoint,
)
from tools.stage5_dialogue_neural_research import translate_phase, verify_phase


class TestStage5DialogueNeuralResearch(unittest.TestCase):
    def test_new_source_manifest_is_disjoint_and_contains_no_spanish_answers(self):
        frozen = manifest()
        self.assertEqual(frozen["count"], 16)
        self.assertTrue(frozen["source_only"])
        self.assertFalse(frozen["includes_spanish_reference_answers"])
        self.assertTrue(source_sets_disjoint())
        self.assertEqual(len({x.id for x in STAGE5_CASES}), 16)
        self.assertTrue(any("\\N[" in x.japanese for x in STAGE5_CASES))
        self.assertTrue(any("\\V[" in x.japanese for x in STAGE5_CASES))
        self.assertTrue(any("\r\n" in x.japanese for x in STAGE5_CASES))
        self.assertTrue(all(set(x) == {"case", "source", "risk"}
                            for x in frozen["cases"]))
        self.assertFalse(frozen["professional_quality_approved"])

    def test_witness_role_inversion_is_rejected_even_with_all_keywords(self):
        case = next(x for x in STAGE5_CASES if x.id == "unseen_courier")
        bad = "El repartidor dijo que vino anoche, pero aún no ha visto a nadie."
        faults = _semantic_errors(case, bad)
        self.assertIn("WITNESS_ACTOR_REVERSED", faults)
        self.assertIn("WITNESS_OBJECT_RELATION_UNVERIFIED", faults)
        good = "El repartidor dijo que había venido anoche, pero nadie lo ha visto."
        self.assertNotIn("WITNESS_ACTOR_REVERSED", _semantic_errors(case, good))
        self.assertNotIn("WITNESS_OBJECT_RELATION_UNVERIFIED",
                         _semantic_errors(case, good))

    def test_feminine_sword_wrong_pronoun_is_semantic_failure(self):
        case = next(x for x in STAGE5_CASES if x.id == "mika_sword_return")
        wrong = "La espada es de Mika, no mía. Mañana devuélvelo a ella."
        self.assertIn("SWORD_FEMININE_OBJECT_MASCULINE_PRONOUN",
                      _semantic_errors(case, wrong))
        good = "Esta espada es de Mika, no mía. Devuélvela a ella mañana."
        self.assertNotIn("SWORD_FEMININE_OBJECT_MASCULINE_PRONOUN",
                         _semantic_errors(case, good))

    def test_explicit_we_and_calendar_negation_have_distinct_guards(self):
        sister = next(x for x in STAGE5_CASES if x.id == "map_we_go_together")
        self.assertIn("EXPLICIT_WE_PLURAL_AGENT_LOST",
                      _semantic_errors(sister,
                         "Mi hermana menor encontró el mapa; pienso ir juntos al bosque."))
        days = next(x for x in STAGE5_CASES if x.id == "friday_to_monday")
        self.assertIn("EXCLUDED_TUESDAY_LOST",
                      _semantic_errors(days,
                        "La reserva pasó de viernes a lunes y también a martes."))

    def test_empty_inference_never_creates_semantically_accepted_rows(self):
        calls = []
        class BrokenModel:
            def translate(self, text):
                calls.append(text)
                return ""
            def close(self):
                pass

        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "stage5"
            status = translate_phase(
                workspace, None,
                model_loader=lambda: (BrokenModel(), [{"repo_id": "synthetic"}]),
            )
            self.assertEqual(status, 1)
            self.assertTrue(calls)
            report = json.loads(
                (workspace / "stage5-neural-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["rubric_accepted"], 0)
            self.assertEqual(report["rejected"], 16)
            self.assertEqual(report["review_queue_pending"], 16)
            self.assertFalse(report["professional_quality_approved"])
            self.assertEqual(verify_phase(workspace), 0)
            cold = json.loads(
                (workspace / "stage5-cold-restart-proof.json").read_text(encoding="utf-8")
            )
            self.assertEqual(cold["persistence_status"], "PASS")
            self.assertEqual(cold["rubric_status"], "FAIL")
            self.assertFalse(cold["models_loaded_during_restart"])

    def test_cold_restart_requires_receipts(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(verify_phase(Path(root)), 1)


if __name__ == "__main__":
    unittest.main()
