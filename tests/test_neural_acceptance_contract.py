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

    def test_friend_is_angry_agent_without_inventing_speaker(self):
        case = next(c for c in acceptance.CASES if c.id == "preparation")
        acceptable = "Si no te preparas rápido, tus amigos se enojarán."
        self.assertEqual(acceptance._semantic_errors(case, acceptable), [])

    def test_mere_keywords_do_not_certify_club_membership(self):
        case = next(c for c in acceptance.CASES if c.id == "sports")
        wrong = ("Estoy en el equipo de fútbol. Mi amigo es nadador. "
                 "Nuestra escuela es un centro de fútbol. "
                 "Hay un nuevo profesor en el equipo de natación.")
        errors = acceptance._semantic_errors(case, wrong)
        self.assertIn("FRIEND_SWIMMING_CLUB_MEMBERSHIP_NOT_DEMONSTRATED", errors)

    def test_ungrounded_ampm_is_rejected_after_correct_numerals(self):
        case = next(c for c in acceptance.CASES if c.id == "numbers_and_code")
        errors = acceptance._semantic_errors(
            case, r"\V[12]El plan es a las 12:30 p. m."
        )
        self.assertIn("UNSUPPORTED_AM_PM_ADDED", errors)
        self.assertEqual(
            acceptance._semantic_errors(case, r"\V[12]El plan es a las 12:30."),
            []
        )

    def test_explicit_evening_correction_is_source_grounded_and_receipted(self):
        source = "夕方に図書館へ行きます。"
        corrected, edits = acceptance._restore_reviewed_time_terms(
            source, "Voy a la biblioteca por la noche."
        )
        self.assertEqual(corrected, "Voy a la biblioteca al atardecer.")
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["source_anchor"], "夕方")
        self.assertEqual(edits[0]["basis"], "reviewed_ja_es_terminology")
        for other in ("夜に図書館へ行きます。", "夕方と夜に行きます。"):
            unchanged, edits = acceptance._restore_reviewed_time_terms(
                other, "Voy a la biblioteca por la noche."
            )
            self.assertEqual(unchanged, "Voy a la biblioteca por la noche.")
            self.assertEqual(edits, [])

    def test_unsupported_joy_and_early_school_eras_are_detected(self):
        club = next(c for c in acceptance.CASES if c.id == "club")
        childhood = next(c for c in acceptance.CASES if c.id == "childhood")
        self.assertTrue(acceptance._semantic_errors(
            club, "Las actividades del club se reanudan. ¡Es un placer!"
        ))
        self.assertTrue(acceptance._semantic_errors(
            childhood, "Hanako es amiga de infancia. Su casa está al lado. "
                       "Somos amigos desde la escuela."
        ))

    def test_wrong_greeting_name_and_speaker_is_not_accepted(self):
        greeting = next(c for c in acceptance.CASES if c.id == "greeting")
        self.assertTrue(acceptance._semantic_errors(
            greeting, "¡Buenos días, Goro! No llegamos tarde hoy."
        ))

    def test_reject_ungrammatical_short_model_outputs(self):
        samples = {item.id: item for item in acceptance.CASES}
        cases = (
            ("greeting", "Taro ¡Buenas mañanas! No llegaste tarde."),
            ("waking", "Ya es mañana. Vamos a levantarnos."),
            ("line_breaks", "Voy a la escuela.\r\nMañana es vacaciones."),
            ("sports", "Mi amigo está en el club de natación. "
                       "Nuestra escuela está lleno de fútbol. "
                       "Tenemos un nuevo profesor de natación."),
        )
        for case_id, bad in cases:
            with self.subTest(case=case_id):
                self.assertTrue(acceptance._semantic_errors(samples[case_id], bad))

    def test_evening_glossary_respects_sentence_initial_capitalization(self):
        result, edits = acceptance._restore_reviewed_time_terms(
            "夕方に行きます。", "Por la noche iré al parque."
        )
        self.assertEqual(result, "Al atardecer iré al parque.")
        self.assertEqual(len(edits), 1)

    def test_model_report_never_mislabels_nllb_as_m2m100(self):
        from tools.direct_marian_acceptance import _report_schema
        self.assertEqual(
            _report_schema("REAL_NEURAL_PUBLIC_NLLB_RESEARCH_NOT_ORIGINAL_PRIVATE_MODEL"),
            "public-real-direct-nllb-research-ja-es-v1"
        )
        with self.assertRaises(ValueError):
            _report_schema("UNRECOGNIZED_MODEL")

    def test_quality_callback_rejects_false_positive_model_output(self):
        from translation_lab.pipeline import TranslationRejected
        from tools.neural_acceptance import _require_semantic_fidelity
        sample = next(c for c in acceptance.CASES if c.id == "sports")
        with self.assertRaises(TranslationRejected):
            _require_semantic_fidelity(
                sample, "Mi amigo es un club de natación. "
                        "Nuestra escuela está llena de fútbol."
            )

    def test_cousin_and_misassigned_childhood_actor_must_fail(self):
        case = next(c for c in acceptance.CASES if c.id == "childhood")
        for bad in (
            "Hanako es mi prima. La casa está al lado. "
            "Es mi amigo desde que era estudiante de primaria.",
            "Hanako es mi niñez. La casa está al lado. "
            "Es estudiante de primaria.",
        ):
            errors = acceptance._semantic_errors(case, bad)
            self.assertIn("CHILDHOOD_FRIENDSHIP_NOT_DEMONSTRATED", errors)
        valid = ("Hanako es mi amiga de la infancia. Nuestras casas están juntas. "
                 "Somos amigas desde la primaria.")
        self.assertEqual(acceptance._semantic_errors(case, valid), [])

    def test_time_sense_morning_is_derived_from_original_only(self):
        result, edits = acceptance._restore_reviewed_time_terms(
            "もう朝です。起きましょう。",
            "Ya es mañana. Vamos a levantarnos.",
        )
        self.assertEqual(result, "Ya es de mañana. Vamos a levantarnos.")
        self.assertEqual(edits[0]["source_anchor"], "もう朝")
        result2, edits2 = acceptance._restore_reviewed_time_terms(
            "明日は休みです。",
            "Ya es mañana. Vamos a levantarnos.",
        )
        self.assertEqual(result2, "Ya es mañana. Vamos a levantarnos.")
        self.assertFalse(edits2)

    def test_unstated_meridiem_is_removed_without_changing_time(self):
        original = r"\V[12]の予定は12時30分です。"
        output, edits = acceptance._restore_reviewed_time_terms(
            original, r"\V[12]El plan es a las 12:30 p.m."
        )
        self.assertEqual(output, r"\V[12]El plan es a las 12:30.")
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["source_anchor"], "12時30分")
        for qualified in ("午後12時30分です。", "午前12時30分です。"):
            result, edits = acceptance._restore_reviewed_time_terms(
                qualified, "El plan es a las 12:30 p.m."
            )
            self.assertEqual(result, "El plan es a las 12:30 p.m.")
            self.assertFalse(edits)

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
