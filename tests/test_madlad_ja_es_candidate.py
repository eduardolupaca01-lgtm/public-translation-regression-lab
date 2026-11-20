"""Offline contract tests for the pinned MADLAD candidate adapters."""
from types import SimpleNamespace
import unittest

from tools.madlad_ja_es_candidate import (
    CT2_VERSION,
    MODEL_SPECS,
    MadladTranslator,
)
from tools.independent_pivot_holdout import INDEPENDENT_CASES
from translation_lab.pipeline import TranslationRejected


class FakeTokenizer:
    def __init__(self):
        self.last_prompt = None

    def encode(self, text):
        self.last_prompt = text
        return [11, 12, 13]

    def convert_ids_to_tokens(self, ids):
        return ["source-" + str(value) for value in ids]

    def convert_tokens_to_ids(self, tokens):
        return [21 for _ in tokens]

    def decode(self, ids, skip_special_tokens=True):
        return "Salida original del modelo."


class FakeCTranslate2:
    def __init__(self):
        self.last_batch = None
        self.kwargs = None

    def translate_batch(self, batch, **kwargs):
        self.last_batch = batch
        self.kwargs = kwargs
        return [SimpleNamespace(hypotheses=[["target-token"]])]


class TestMadladCandidateContracts(unittest.TestCase):
    def test_both_candidates_are_pinned_to_immutable_revisions(self):
        self.assertEqual(set(MODEL_SPECS), {"base", "es419"})
        for candidate, spec in MODEL_SPECS.items():
            with self.subTest(candidate=candidate):
                self.assertRegex(spec["revision"], r"^[0-9a-f]{40}$")
                self.assertEqual(spec["declared_license"], "apache-2.0")
                self.assertEqual(spec["base_model"], "google/madlad400-3b-mt")
                self.assertEqual(spec["quantization"] in {
                    "int8", "int8_float16"
                }, True)

    def test_spanish_target_tags_are_not_interchanged(self):
        self.assertEqual(MODEL_SPECS["base"]["target_tag"], "<2es>")
        self.assertEqual(MODEL_SPECS["es419"]["target_tag"], "<2es_419>")

    def test_both_candidates_use_the_same_fixed_twenty_case_set(self):
        self.assertEqual(len(INDEPENDENT_CASES), 20)
        self.assertEqual(len({case.id for case in INDEPENDENT_CASES}), 20)
        self.assertEqual(len({case.japanese for case in INDEPENDENT_CASES}), 20)

    def test_adapter_prepends_the_selected_target_tag_and_returns_raw_decode(self):
        for candidate in ("base", "es419"):
            with self.subTest(candidate=candidate):
                tokenizer = FakeTokenizer()
                engine = FakeCTranslate2()
                adapter = MadladTranslator(
                    tokenizer,
                    engine,
                    MODEL_SPECS[candidate]["target_tag"],
                )
                output = adapter.translate("日本語の原文です。")
                self.assertEqual(output, "Salida original del modelo.")
                self.assertEqual(
                    tokenizer.last_prompt,
                    MODEL_SPECS[candidate]["target_tag"] + " 日本語の原文です。",
                )
                self.assertEqual(engine.kwargs["beam_size"], 4)
                self.assertEqual(engine.kwargs["max_decoding_length"], 256)
                self.assertEqual(engine.kwargs["no_repeat_ngram_size"], 3)
                self.assertEqual(len(engine.last_batch), 1)

    def test_empty_source_is_rejected_before_model_inference(self):
        tokenizer = FakeTokenizer()
        engine = FakeCTranslate2()
        adapter = MadladTranslator(tokenizer, engine, "<2es>")
        with self.assertRaises(TranslationRejected):
            adapter.translate("   ")
        self.assertIsNone(engine.last_batch)

    def test_context_overflow_is_rejected_before_model_inference(self):
        tokenizer = FakeTokenizer()

        def too_long(_text):
            return list(range(513))

        tokenizer.encode = too_long
        engine = FakeCTranslate2()
        adapter = MadladTranslator(tokenizer, engine, "<2es>")
        with self.assertRaises(TranslationRejected):
            adapter.translate("日本語")
        self.assertIsNone(engine.last_batch)

    def test_runtime_version_is_pinned(self):
        self.assertEqual(CT2_VERSION, "4.8.2")


if __name__ == "__main__":
    unittest.main()
