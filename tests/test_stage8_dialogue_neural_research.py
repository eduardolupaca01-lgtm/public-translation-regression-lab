"""Stage8 locked Japanese-only semantic evaluation: no target-side repairs."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.stage8_dialogue_cases import (
    STAGE8_CASES, REQUIRED, _semantic_errors, manifest, source_sets_disjoint,
)
from tools.stage8_dialogue_neural_research import (
    translate_phase, verify_phase, Stage8NameFidelityTranslator,
    GENERATION_VARIANT, PROMPT_SHA256, STAGE8_SYSTEM_PROMPT,
)
from tools.stage8_katakana_readings import (
    katakana_romanization, source_katakana_readings, phonetic_sidecar,
)


class TestStage8SourceOnlyResearch(unittest.TestCase):
    def test_sources_new_and_frozen_without_spanish_reference_answers(self):
        frozen=manifest()
        self.assertTrue(source_sets_disjoint())
        self.assertEqual(frozen["count"],12)
        self.assertEqual(len({c.japanese for c in STAGE8_CASES}),12)
        self.assertEqual(len({c.id for c in STAGE8_CASES}),12)
        self.assertEqual({c.id for c in STAGE8_CASES},set(REQUIRED))
        self.assertTrue(frozen["source_only"])
        self.assertFalse(frozen["reference_spanish_provided_to_model"])
        self.assertFalse(frozen["model_inference_executed"])
        self.assertFalse(frozen["human_review_complete"])
        self.assertFalse(frozen["professional_quality_approved"])
        self.assertTrue(any("\\N[" in c.japanese for c in STAGE8_CASES))
        self.assertTrue(any("\\V[" in c.japanese for c in STAGE8_CASES))
        self.assertTrue(any("\r\n" in c.japanese for c in STAGE8_CASES))
        self.assertTrue(all(set(x)=={"case","source","risk"} for x in frozen["cases"]))

    def test_nonnegated_shield_sale_vs_prohibition_are_not_confused(self):
        cases={c.id:c for c in STAGE8_CASES}
        source=cases["variable_sword_sell_not_shield"]
        good=r"\N[3] Si \V[8] es mayor que 2, venda la espada. No venda el escudo."
        errors=_semantic_errors(source,good)
        self.assertEqual(errors,[])
        wrong=r"\N[3] Si \V[8] es mayor que 2, no venda la espada. Venda el escudo."
        self.assertIn("SELLS_SHIELD_INSTEAD_OF_SWORD",_semantic_errors(source,wrong))

    def test_taro_mika_and_aria_sara_roles_are_checked(self):
        cases={c.id:c for c in STAGE8_CASES}
        self.assertIn("MIKA_WRONGLY_SEES_HANA",_semantic_errors(
            cases["taro_hana_mika_witness"],
            "Taro vio a Hana salir de la estación y Mika también la vio.",
        ))
        self.assertIn("ASKS_SARA_INSTEAD_OF_ARIA",_semantic_errors(
            cases["two_speakers_aria_sara"],
            "Aria tiene la llave. Mejor pregunte a Sara en lugar de Aria.",
        ))

    def test_sunday_plural_and_inclusive_bound_equivalences(self):
        by={c.id:c for c in STAGE8_CASES}
        good_shop="La tienda abre a las 10 de la mañana y cierra a las 6 de la tarde. No abre los domingos."
        self.assertEqual(_semantic_errors(by["shop_hours_sunday"],good_shop),[])
        bad_shop="La tienda abre a las 10 de la mañana y cierra a las 6 de la tarde. Abre los domingos."
        self.assertIn("SUNDAY_CLOSED_MISSING",_semantic_errors(by["shop_hours_sunday"],bad_shop))
        bounds=r"\V[5] es 4 o menos, no abra esta puerta. Si es 5 o más, se puede abrir."
        self.assertEqual(_semantic_errors(by["variable_boundary_two_cases"],bounds),[])
        reversed_bounds=r"Si \V[5] es 4 o menos, puede abrir la puerta. Si es 5 o más, no abra la puerta."
        err=_semantic_errors(by["variable_boundary_two_cases"],reversed_bounds)
        self.assertIn("LOWER_BOUND_WRONGLY_PERMITS_OPENING",err)
        self.assertIn("UPPER_BOUND_WRONGLY_FORBIDS_OPENING",err)

    def test_source_derived_phonetics_are_not_spanish_reference_answers(self):
        import hashlib
        self.assertEqual(GENERATION_VARIANT, "stage8_uniform_name_phonetics_and_permissions_v6")
        self.assertEqual(PROMPT_SHA256, hashlib.sha256(
            STAGE8_SYSTEM_PROMPT.encode("utf-8")).hexdigest())
        by = {c.id:c for c in STAGE8_CASES}
        case = by["taro_hana_mika_witness"]
        readings = dict(source_katakana_readings(case.japanese))
        self.assertEqual(readings["ハナ"], "Hana")
        self.assertEqual(readings["ミカ"], "Mika")
        self.assertEqual(katakana_romanization("アリア"), "Aria")
        self.assertEqual(katakana_romanization("サラ"), "Sara")
        payload = Stage8NameFidelityTranslator.build_payload(case.japanese)
        self.assertEqual(payload["messages"][0]["content"], STAGE8_SYSTEM_PROMPT)
        prompt = payload["messages"][1]["content"]
        self.assertIn(case.japanese, prompt)
        self.assertIn("ハナ = Hana", prompt)
        self.assertIn("ミカ = Mika", prompt)
        self.assertNotIn("Hanako", prompt)
        self.assertNotIn("Taro vio a Hana", prompt)
        self.assertEqual(phonetic_sidecar("薬を三つ買いました。"), "")

    def test_permission_faithful_subjunctive_vs_negated_inversion(self):
        sample = {c.id:c for c in STAGE8_CASES}["variable_boundary_two_cases"]
        good = r"Si \\V[5] es 4 o menos, no abra esta puerta. Si es 5 o más, está bien que la abra."
        self.assertEqual(_semantic_errors(sample, good), [])
        allowed = r"Si \\V[5] es 4 o menos, no abra esta puerta. Si es 5 o más, está permitido abrirla."
        self.assertEqual(_semantic_errors(sample, allowed), [])
        wrong = r"Si \\V[5] es 4 o menos, no abra esta puerta. Si es 5 o más, no está bien que la abra."
        self.assertIn("UPPER_BOUND_WRONGLY_FORBIDS_OPENING", _semantic_errors(sample, wrong))
        wrong2 = r"Si \\V[5] es 4 o menos, no abra esta puerta. Si es 5 o más, no se puede abrirla."
        self.assertIn("UPPER_BOUND_WRONGLY_FORBIDS_OPENING", _semantic_errors(sample, wrong2))

    def test_japanese_name_must_not_be_extended_or_shortened(self):
        by={c.id:c for c in STAGE8_CASES}
        for altered in ("Han","Hanako"):
            with self.subTest(altered=altered):
                value=f"Taro vio a {altered} salir de la estación, pero Mika no la vio salir."
                self.assertIn("HANA_MISSING",_semantic_errors(by["taro_hana_mika_witness"],value))

    def test_empty_model_cannot_reuse_a_successful_cache_or_claim_quality(self):
        class NullModel:
            def translate(self,text): return ""
            def close(self): pass
        with tempfile.TemporaryDirectory() as tmp:
            space=Path(tmp)/"stage8"
            rc=translate_phase(
                space,None,model_loader=lambda:(NullModel(),[{"repo_id":"synthetic"}])
            )
            self.assertEqual(rc,1)
            report=json.loads(
                (space/"stage8-neural-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["rubric_accepted"],0)
            self.assertEqual(report["rejected"],12)
            self.assertEqual(report["review_queue_pending"],12)
            self.assertFalse(report["professional_quality_approved"])
            self.assertEqual(verify_phase(space),0)
            proof=json.loads(
                (space/"stage8-cold-restart-proof.json").read_text(encoding="utf-8")
            )
            self.assertEqual(proof["rubric_status"],"FAIL")
            self.assertEqual(proof["persistence_status"],"PASS")
            self.assertFalse(proof["models_loaded_during_restart"])


if __name__ == "__main__":
    unittest.main()
