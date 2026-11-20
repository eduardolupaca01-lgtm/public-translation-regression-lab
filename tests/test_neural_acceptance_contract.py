"""Dependency-free contract tests. These fakes are NOT neural model evidence."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from tools import neural_acceptance as acceptance
from translation_lab.cache import DurableTranslationCache


class FakeArgos:
    """Only for this unittest module; real acceptance downloads Argos models."""
    def translate(self, text: str, source: str, target: str) -> str:
        if (source, target) == ("ja", "en"):
            return "Thank you."
        if (source, target) == ("en", "es"):
            return "Gracias."
        raise AssertionError("Unexpected model route")


class TestRealNeuralHarnessContract(unittest.TestCase):
    def test_twelve_distinct_synthetic_cases(self):
        self.assertEqual(len(acceptance.CASES), 12)
        self.assertEqual(len({c.id for c in acceptance.CASES}), 12)
        self.assertTrue(all(c.japanese for c in acceptance.CASES))
        self.assertTrue(any("\\V[12]" in c.japanese for c in acceptance.CASES))
        self.assertTrue(any("\r\n" in c.japanese for c in acceptance.CASES))

    def test_semantic_checks_reject_missing_meaning(self):
        self.assertEqual(acceptance._semantic_missing(
            "Buenas tardes.", (("mañana",), ("tarde",))),
            [["mañana"]])
        self.assertEqual(acceptance._semantic_missing(
            "Gracias.", (("gracias", "agradez"),)), [])

    def test_reject_unfaithful_sports_relation_despite_keywords(self):
        case = next(sample for sample in acceptance.CASES
                    if sample.id == "sports")
        wrong = ("Estoy en el club de fútbol. Mi amigo es un club de natación. "
                 "Nuestra escuela está llena de fútbol. "
                 "Hay un nuevo profesor en la zona de natación.")
        issue = acceptance._semantic_errors(case, wrong)
        self.assertTrue(any("UNFAITHFUL_RELATIONSHIP" in x for x in issue))

    def test_reject_inverted_passive_actor_despite_keywords(self):
        case = next(sample for sample in acceptance.CASES
                    if sample.id == "preparation")
        wrong = "Si no te preparas, estarás enfadado con tus amigos."
        issue = acceptance._semantic_errors(case, wrong)
        self.assertTrue(any("PASSIVE_AGENT" in x or
                            "UNFAITHFUL_RELATIONSHIP" in x for x in issue))

    def test_reject_unrelated_numeric_fragments(self):
        case = next(sample for sample in acceptance.CASES
                    if sample.id == "numbers_and_code")
        wrong = r"\V[12]Cuadro12Hora30Contáctenos"
        self.assertIn("TIME_RELATION_NOT_PRESERVED",
                      acceptance._semantic_errors(case, wrong))

    def test_reject_language_selection_notice_as_translation(self):
        self.assertTrue(acceptance._model_boilerplate(
            "Sorry, this entry is only available in Japanese."))
        self.assertFalse(acceptance._model_boilerplate(
            "I will go to school tomorrow."))

    def test_numeric_context_reaches_model_and_remains_strict(self):
        from translation_lab.pipeline import translate_checked, TranslationRejected
        sample = r"\V[12]の予定は12時30分です。"
        calls = []

        def good(fragment):
            calls.append(fragment)
            return "El horario es a las 12:30."
        result = translate_checked(sample, good, protect_numbers=False)
        self.assertEqual(calls, ["の予定は12時30分です。"])
        self.assertIn(r"\V[12]", result)
        self.assertIn("12:30", result)
        with self.assertRaises(TranslationRejected):
            translate_checked(sample, lambda _: "El horario es a las 12:31.",
                              protect_numbers=False)

    def test_sentence_boundary_survives_model_omitted_stop(self):
        from translation_lab.pipeline import translate_checked
        phrases = {
            "もう朝です。": "Por la mañana",
            "起きましょう。": "Vamos a levantarnos.",
        }
        output = translate_checked("もう朝です。起きましょう。",
                                   lambda part: phrases[part])
        self.assertEqual(output, "Por la mañana. Vamos a levantarnos.")

    def test_setup_failure_is_explicit_and_never_an_approval(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "result"
            with mock.patch.object(acceptance, "_create_models",
                                   side_effect=RuntimeError("MODEL_DOWNLOAD_UNAVAILABLE")):
                code = acceptance.translate_phase(workspace)
            self.assertEqual(code, 1)
            receipt = json.loads((workspace / "neural-report.json").read_text())
            self.assertEqual(receipt["accepted"], 0)
            self.assertEqual(receipt["rejected"], 12)
            self.assertFalse(receipt["backend_executed"])
            self.assertIn("MODEL_DOWNLOAD_UNAVAILABLE", receipt["setup_error"])

    def test_fake_translation_failure_is_not_written_to_sqlite(self):
        sample = acceptance.Case(
            "fake_greeting", "ありがとうございます。", (("escuela",),))
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "result"
            with mock.patch.object(acceptance, "CASES", (sample,)), \
                 mock.patch.object(acceptance, "_create_models",
                                   return_value=(FakeArgos(), [])):
                self.assertEqual(acceptance.translate_phase(workspace), 1)
                self.assertEqual(acceptance.verify_phase(workspace), 1)
            with DurableTranslationCache(workspace / "cache") as cache:
                self.assertEqual(cache.count(), 0)

    def test_reopen_cache_in_second_process_does_not_call_model(self):
        # This is a deterministic storage/wiring test, NOT a successful model
        # inference claim. The separate CI workflow exercises actual models.
        sample = acceptance.Case(
            "fake_thanks", "ありがとうございます。", (("gracias",),))
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "result"
            with mock.patch.object(acceptance, "CASES", (sample,)), \
                 mock.patch.object(acceptance, "_create_models",
                                   return_value=(FakeArgos(), [])):
                self.assertEqual(acceptance.translate_phase(workspace), 0)
                self.assertEqual(acceptance.verify_phase(workspace), 0)
                proof = json.loads((workspace / "restart-proof.json").read_text())
                self.assertTrue(proof["models_loaded_during_restart"] is False)
                self.assertEqual(proof["accepted"], 1)


if __name__ == "__main__":
    unittest.main()
