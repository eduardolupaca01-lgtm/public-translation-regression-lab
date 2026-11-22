"""No scripted target repairs or case-specific references in two-pass inference."""
import unittest
from tools.qwen3_8b_two_pass_ja_es_candidate import (
    GENERATION_VARIANT, SECOND_PASS_SYSTEM, TwoPassQwen8BTranslator,
)
from tools.qwen3_8b_ja_es_candidate import MODEL_REPO, MODEL_SHA256
from tools.independent_pivot_holdout import INDEPENDENT_CASES
from translation_lab.pipeline import TranslationRejected


class TestQwen8BTwoPass(unittest.TestCase):
    def test_two_passes_use_pinned_model_and_source_at_every_stage(self):
        source = r"明日、\N[3]は午後6時に戻ります。"
        draft = "Mañana volverá a las seis de la tarde."
        first = TwoPassQwen8BTranslator.build_payload(source)
        review = TwoPassQwen8BTranslator.build_review_payload(source, draft)
        self.assertEqual(first["model"], review["model"])
        self.assertIn(source, first["messages"][1]["content"])
        self.assertIn(source, review["messages"][1]["content"])
        self.assertIn(draft, review["messages"][1]["content"])
        self.assertIn(r"\N[3]", review["messages"][1]["content"])
        self.assertEqual(review["seed"], 513)
        self.assertEqual(review["temperature"], 0.0)
        self.assertFalse(review["stream"])
        self.assertIn("independently reviewing", SECOND_PASS_SYSTEM)
        self.assertEqual(len(INDEPENDENT_CASES), 20)
        self.assertEqual(len(MODEL_SHA256), 64)
        self.assertEqual(MODEL_REPO, "Qwen/Qwen3-8B-GGUF")
        self.assertEqual(GENERATION_VARIANT, "uniform_neural_two_pass_revision")

    def test_reviewed_neural_output_is_returned_without_post_edit(self):
        calls = []
        def request(url, payload, timeout):
            calls.append((url, payload, timeout))
            if len(calls) == 1:
                return {"choices": [{"message": {"content": "Borrador con error."}}]}
            return {"choices": [{"message": {"content": "Texto final fiel."}}]}

        adapter = TwoPassQwen8BTranslator(request_json=request)
        self.assertEqual(
            adapter.translate("日本語です。"), "Texto final fiel."
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(adapter.review_history[0]["draft"], "Borrador con error.")
        self.assertEqual(adapter.review_history[0]["reviewed"], "Texto final fiel.")
        self.assertIn("Borrador con error.", calls[1][1]["messages"][1]["content"])
        self.assertEqual(calls[0][2], 180)
        self.assertEqual(calls[1][2], 180)

    def test_failed_second_pass_never_approves_unchecked_draft(self):
        calls = []
        def request(_url, _payload, _timeout):
            calls.append(True)
            if len(calls) == 1:
                return {"choices": [{"message": {"content": "Borrador."}}]}
            return {"choices": [{"message": {"content": " "}}]}

        adapter = TwoPassQwen8BTranslator(request_json=request)
        with self.assertRaises(TranslationRejected):
            adapter.translate("日本語です。")
        self.assertIsNone(adapter.review_history[0]["reviewed"])
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
