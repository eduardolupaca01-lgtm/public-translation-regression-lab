"""Stage7 source-only RPG dialogue stress safeguards."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.stage7_dialogue_cases import (
    STAGE7_CASES, REQUIRED, _semantic_errors, manifest, source_sets_disjoint
)
from tools.stage7_dialogue_neural_research import translate_phase, verify_phase


class TestStage7(unittest.TestCase):
    def test_new_unseen_sources_no_reference_answers(self):
        m = manifest()
        self.assertEqual(m["count"],12)
        self.assertTrue(source_sets_disjoint())
        self.assertTrue(m["source_only"])
        self.assertFalse(m["reference_spanish_provided_to_model"])
        self.assertFalse(m["human_bilingual_approval"])
        self.assertFalse(m["model_inference_executed"])
        self.assertEqual(set(REQUIRED),{c.id for c in STAGE7_CASES})
        self.assertTrue(any("\\N[" in c.japanese for c in STAGE7_CASES))
        self.assertTrue(any("\\V[" in c.japanese for c in STAGE7_CASES))
        self.assertTrue(any("\r\n" in c.japanese for c in STAGE7_CASES))
        self.assertTrue(all(set(x)=={"case","source","risk"} for x in m["cases"]))

    def test_material_relation_inversions_are_rejected(self):
        by={c.id:c for c in STAGE7_CASES}
        self.assertIn("WRONG_PERSON_READ_THE_LETTER",_semantic_errors(
            by["sara_tom_unread_letter"],
            "Sara le dio una carta a Tom, pero Sara no la ha leído todavía."
        ))
        self.assertIn("MIKA_WITNESS_ROLE_REVERSED",_semantic_errors(
            by["nobody_saw_mika_depart"],
            "Mika salió de la ciudad, pero ella no ha visto a nadie."
        ))
        self.assertIn("STRICT_INEQUALITY_CHANGED_TO_INCLUSIVE",_semantic_errors(
            by["medicine_variable_strict_gt"],
            r"Si \V[2] es mayor o igual a 1, usa una medicina; de lo contrario, no."
        ))
        self.assertIn("TORCH_ORDER_REVERSED",_semantic_errors(
            by["torch_bridge_order"],
            "Antes de cruzar el puente, encender la antorcha. Después, apagarla."
        ))


    def test_real_neural_rejections_are_not_permitted_as_false_positive_successes(self):
        by={c.id:c for c in STAGE7_CASES}
        mika_good="Según se dice, Mika salió del pueblo, pero nadie la vio salir."
        self.assertEqual(_semantic_errors(by["nobody_saw_mika_depart"],mika_good),[])
        mika_bad="Parece que Mika salió del pueblo, pero ella no ha visto a nadie."
        self.assertIn("MIKA_WITNESS_ROLE_REVERSED",
                      _semantic_errors(by["nobody_saw_mika_depart"],mika_bad))
        torch_gender="Por favor, apague la antorcha antes de cruzar el puente. Después de cruzar, no hay problema si lo enciende nuevamente."
        bad=_semantic_errors(by["torch_bridge_order"],torch_gender)
        self.assertNotIn("RELIGHT_MISSING",bad)
        self.assertIn("TORCH_FEMININE_OBJECT_MASCULINE_PRONOUN",bad)
        torch_good="Apague la antorcha antes de cruzar el puente. Después de cruzar puede encenderla de nuevo."
        self.assertEqual(_semantic_errors(by["torch_bridge_order"],torch_good),[])
        torch_substitution="Apague la vela antes de cruzar el puente. Después de cruzar puede encenderla de nuevo."
        self.assertIn("TORCH_MISSING",
                      _semantic_errors(by["torch_bridge_order"],torch_substitution))

    def test_model_can_not_reverse_medicine_if_then_logic_and_still_pass(self):
        by={c.id:c for c in STAGE7_CASES}
        source=by["medicine_variable_strict_gt"]
        inverted=r"\V[2] es mayor que 1 solo si utilice un medicamento. De lo contrario, no lo utilice."
        self.assertIn("MEDICINE_PREMISE_AND_CONSEQUENCE_REVERSED",
                      _semantic_errors(source,inverted))
        valid_condition_first=r"Solo si \V[2] es mayor que 1, utilice una medicina; de lo contrario no la use."
        self.assertEqual(_semantic_errors(source,valid_condition_first),[])
        valid_action_first=r"Utilice una medicina solo si \V[2] es mayor que 1. De lo contrario, no la use."
        self.assertEqual(_semantic_errors(source,valid_action_first),[])

    def test_empty_mock_outputs_are_quarantined_and_durable(self):
        class Bad:
            def translate(self,text): return ""
            def close(self): pass
        with tempfile.TemporaryDirectory() as root:
            work=Path(root)/"stage7"
            status=translate_phase(work,None,model_loader=lambda:(Bad(),[{"repo_id":"synthetic"}]))
            self.assertEqual(status,1)
            report=json.loads((work/"stage7-neural-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["rubric_accepted"],0)
            self.assertEqual(report["rejected"],12)
            self.assertEqual(report["review_queue_pending"],12)
            self.assertFalse(report["professional_quality_approved"])
            self.assertEqual(verify_phase(work),0)
            proof=json.loads((work/"stage7-cold-restart-proof.json").read_text(encoding="utf-8"))
            self.assertEqual(proof["rubric_status"],"FAIL")
            self.assertEqual(proof["persistence_status"],"PASS")
            self.assertFalse(proof["models_loaded_during_restart"])


if __name__ == "__main__":
    unittest.main()
