"""Stage6: source disjointness, stronger semantic checks and cold-persistence."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.stage6_dialogue_cases import (
    STAGE6_CASES, _semantic_errors, context_review_flags,
    manifest, source_sets_disjoint,
)
from tools.stage6_discourse_model import (
    GENERATION_VARIANT, PROMPT_SHA256, DISCOURSE_GUIDANCE, DISCOURSE_V3_GUIDANCE, DISCOURSE_V4_GUIDANCE,
    DiscourseThinkingTranslator, load_model,
)
from tools.stage4_source_complete_candidate import SourceCompleteThinkingTranslator
from tools.qwen3_stage3_holdout import THINKING_REQUEST_TIMEOUT_SECONDS
from tools.stage6_dialogue_neural_research import translate_phase, verify_phase


class TestStage6DiscourseResearch(unittest.TestCase):
    def test_source_manifest_is_frozen_disjoint_and_source_only(self):
        frozen = manifest()
        self.assertEqual(frozen["count"], 16)
        self.assertTrue(source_sets_disjoint())
        self.assertTrue(frozen["source_only"])
        self.assertFalse(frozen["spanish_reference_provided_to_model"])
        self.assertFalse(frozen["human_bilingual_approval"])
        self.assertEqual(len({x.id for x in STAGE6_CASES}), 16)
        self.assertTrue(any("\\N[" in x.japanese for x in STAGE6_CASES))
        self.assertTrue(any("\\V[" in x.japanese for x in STAGE6_CASES))
        self.assertTrue(any("\r\n" in x.japanese for x in STAGE6_CASES))
        self.assertTrue(all(set(row) == {"case", "source", "risk"} for row in frozen["cases"]))

    def test_missing_conditional_is_rejected_despite_numbers_and_door(self):
        case = next(x for x in STAGE6_CASES if x.id == "npc_two_condition_variables")
        bad = r"\N[4] \V[9] es 0, no se puede abrir la puerta. \V[9] es 1, se abre."
        errors = _semantic_errors(case, bad)
        self.assertIn("VARIABLE_IF_CLAUSE_MISSING", errors)
        self.assertIn("TWO_EXPLICIT_VARIABLE_CONDITIONS_MISSING", errors)
        good = r"\N[4] Si \V[9] es 0, no se puede abrir la puerta. Si \V[9] es 1, se puede abrir."
        self.assertEqual(_semantic_errors(case, good), [])

    def test_reversed_roles_and_sword_pronoun_are_blocked(self):
        person = next(x for x in STAGE6_CASES if x.id == "search_not_found_roles")
        self.assertIn(
            "FOUND_PERSON_ROLE_REVERSED",
            _semantic_errors(person,
                "Todos lo buscan, pero él no ha encontrado a nadie."),
        )
        sword = next(x for x in STAGE6_CASES if x.id == "sword_companion_return")
        self.assertIn(
            "SPANISH_SWORD_OBJECT_GENDER_WRONG",
            _semantic_errors(sword,
                "La espada es de ella. Primero métela en la funda y devuélvelo."),
        )


    def test_rejected_samples_are_semantically_faithful_not_false_failures(self):
        by_id = {x.id: x for x in STAGE6_CASES}
        collective = "Todos están buscándolo, pero aún no lo han encontrado."
        self.assertEqual(_semantic_errors(
            by_id["search_not_found_roles"], collective
        ), [])
        self.assertIn("FOUND_PERSON_ROLE_REVERSED", _semantic_errors(
            by_id["search_not_found_roles"],
            "Todos lo buscan, pero él no ha encontrado a nadie.",
        ))
        self.assertEqual(_semantic_errors(
            by_id["files_delete_only_old"],
            "Puedes eliminar los archivos antiguos, pero no borres los archivos nuevos.",
        ), [])
        self.assertEqual(_semantic_errors(
            by_id["permission_changed_today"],
            "Ayer podría haber entrado, pero hoy no se debe entrar.",
        ), [])
        self.assertIn(
            "PAST_PERMISSION_VS_COUNTERFACTUAL_POSSIBILITY_REVIEW",
            context_review_flags(
                by_id["permission_changed_today"],
                "Ayer podría haber entrado, pero hoy no se debe entrar.",
            )
        )

    def test_generic_spanish_agreement_and_name_inconsistency_are_not_accepted(self):
        by_id = {x.id: x for x in STAGE6_CASES}
        sword_bad = "El espada cuesta 1500 yenes y el escudo 900 yenes. Los dos 2400 yenes."
        self.assertIn("SPANISH_SWORD_ARTICLE_GENDER_MISMATCH",
            _semantic_errors(by_id["two_item_cost_total"], sword_bad))
        sword_good = "La espada cuesta 1500 yenes y el escudo 900 yenes. Juntos son 2400 yenes."
        self.assertNotIn("SPANISH_SWORD_ARTICLE_GENDER_MISMATCH",
            _semantic_errors(by_id["two_item_cost_total"], sword_good))
        changed = (r"\N[5] Sara tiene la llave."
                   "\r\n" + r"\N[3] Preguntemos a Sarah y no a Tom.")
        self.assertIn("INCONSISTENT_SARA_NAME_SPELLING",
            _semantic_errors(by_id["two_speakers_ask_sara"], changed))
        consistent = (r"\N[5] Sara tiene la llave."
                      "\r\n" + r"\N[3] Preguntemos a Sara y no a Tom.")
        self.assertNotIn("INCONSISTENT_SARA_NAME_SPELLING",
            _semantic_errors(by_id["two_speakers_ask_sara"], consistent))

    def test_uniform_prompt_and_sampler_differ_only_by_system_instructions(self):
        for japanese in [
            "彼は鍵を持っています。",
            r"\N[3]は明日の午後に戻ります。",
        ]:
            before = SourceCompleteThinkingTranslator.build_payload(japanese)
            after = DiscourseThinkingTranslator.build_payload(japanese)
            self.assertEqual(before["messages"][1], after["messages"][1])
            self.assertNotEqual(before["messages"][0], after["messages"][0])
            for key in ("seed","temperature","top_p","top_k","min_p",
                        "presence_penalty","max_tokens","stream"):
                self.assertEqual(before[key], after[key])
        self.assertIn("conditional", DISCOURSE_GUIDANCE.lower())
        self.assertIn("grammatical gender", DISCOURSE_GUIDANCE.lower())
        self.assertEqual(len(PROMPT_SHA256), 64)
        self.assertIn("every Spanish article", DISCOURSE_V3_GUIDANCE)
        self.assertIn("forward implication", DISCOURSE_V4_GUIDANCE)
        self.assertIn("speech act", DISCOURSE_V4_GUIDANCE)
        self.assertEqual(GENERATION_VARIANT, "uniform_dialogue_roles_condition_direction_v4")

    def test_loader_preserves_raw_output_payload_and_timeout(self):
        calls = []
        class Fake:
            endpoint = "http://127.0.0.1:8080"
            process = None
            log_handle = None
            def request_json(self, url, payload, timeout):
                calls.append((url, payload, timeout))
                return {"choices": []}

        with patch("tools.stage6_discourse_model.thinking._load_model", return_value=(
            Fake(), [{"repo_id": "Qwen/Qwen3-8B-GGUF", "reasoning_mode": "think"}]
        )):
            model, provenance = load_model(Path("/fake/server"), Path("/tmp/stage6"))
        raw = model.build_payload("原文。")
        model.request_json("http://localhost/test", raw, 180)
        self.assertIs(calls[0][1], raw)
        self.assertEqual(calls[0][2], THINKING_REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(provenance[0]["translation_system_prompt_sha256"],
                         PROMPT_SHA256)
        self.assertFalse(provenance[0]["target_side_repairs"])

    def test_empty_inference_rejected_and_cold_review_survives(self):
        class EmptyModel:
            def translate(self, text):
                return ""
            def close(self):
                pass

        with tempfile.TemporaryDirectory() as root:
            space = Path(root) / "stage6"
            code = translate_phase(
                space, None, model_loader=lambda: (
                    EmptyModel(), [{"repo_id": "synthetic"}]
                )
            )
            self.assertEqual(code, 1)
            report = json.loads((space/"stage6-neural-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["rubric_accepted"], 0)
            self.assertEqual(report["rejected"], 16)
            self.assertEqual(report["review_queue_pending"], 16)
            self.assertFalse(report["professional_quality_approved"])
            self.assertEqual(verify_phase(space), 0)
            proof = json.loads((space/"stage6-cold-restart-proof.json").read_text(encoding="utf-8"))
            self.assertEqual(proof["persistence_status"], "PASS")
            self.assertEqual(proof["rubric_status"], "FAIL")
            self.assertFalse(proof["models_loaded_during_restart"])


if __name__ == "__main__":
    unittest.main()
