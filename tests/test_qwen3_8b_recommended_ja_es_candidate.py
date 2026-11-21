"""Offline contract tests for the pinned Qwen3-8B recommended-sampling candidate."""
import unittest

from tools.qwen3_8b_recommended_ja_es_candidate import (
    MAX_OUTPUT_TOKENS,
    SERVER_CONTEXT,
    BASE_MODEL,
    CONTEXTUALIZE_NAME_CODES,
    DECLARED_LICENSE,
    LLAMA_CPP_RELEASE,
    MODEL_FILENAME,
    MODEL_REPO,
    MODEL_REVISION,
    MODEL_SHA256,
    MIN_P,
    PRESENCE_PENALTY,
    PROTECT_NUMBERS,
    TEMPERATURE,
    TOP_K,
    TOP_P,
    PROTECT_LITERALS_IN_CONTEXT,
    QUANTIZATION,
    SYSTEM_PROMPT,
    Qwen8BRecommendedTranslator,
)
from tools.independent_pivot_holdout import INDEPENDENT_CASES
from translation_lab.pipeline import TranslationRejected


class TestQwen8BRecommendedCandidateContracts(unittest.TestCase):
    def test_model_and_runtime_are_pinned(self):
        self.assertEqual(BASE_MODEL, "Qwen/Qwen3-8B")
        self.assertEqual(MODEL_REPO, "Qwen/Qwen3-8B-GGUF")
        self.assertRegex(MODEL_REVISION, r"^[0-9a-f]{40}$")
        self.assertEqual(MODEL_FILENAME, "Qwen3-8B-Q4_K_M.gguf")
        self.assertRegex(MODEL_SHA256, r"^[0-9a-f]{64}$")
        self.assertEqual(DECLARED_LICENSE, "apache-2.0")
        self.assertEqual(QUANTIZATION, "Q4_K_M")
        self.assertEqual(LLAMA_CPP_RELEASE, "b12584")
        self.assertEqual(SERVER_CONTEXT, 4096)
        self.assertEqual(MAX_OUTPUT_TOKENS, 512)
        self.assertEqual(TEMPERATURE, 0.7)
        self.assertEqual(TOP_P, 0.8)
        self.assertEqual(TOP_K, 20)
        self.assertEqual(MIN_P, 0.0)
        self.assertEqual(PRESENCE_PENALTY, 1.5)

    def test_numeric_literals_remain_visible_and_native_codes_stay_in_context(self):
        self.assertFalse(PROTECT_NUMBERS)
        self.assertFalse(CONTEXTUALIZE_NAME_CODES)
        self.assertTrue(PROTECT_LITERALS_IN_CONTEXT)

    def test_system_prompt_targets_faithful_latin_american_translation(self):
        prompt = " ".join(SYSTEM_PROMPT.casefold().split())
        for phrase in (
            "japanese-to-spanish",
            "latin america",
            "do not summarize",
            "grammatical person and number",
            "tense and aspect",
            "younger or older",
            "do not invent a recipient",
            "return only the translation",
            "妹 means",
            "hermana menor",
            "arabic digit sequence visible",
            "indirect-object pronoun",
            "arrive or be delivered",
            "not publish",
            "n[3]",
            "exactly once",
            "singular person",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prompt)

    def test_candidate_uses_the_same_twenty_case_development_set(self):
        self.assertEqual(len(INDEPENDENT_CASES), 20)
        self.assertEqual(len({case.id for case in INDEPENDENT_CASES}), 20)
        self.assertEqual(len({case.japanese for case in INDEPENDENT_CASES}), 20)

    def test_payload_uses_deterministic_non_streaming_chat_completion(self):
        source = "通常1000円ですが、今日は800円で買えます。"
        payload = Qwen8BRecommendedTranslator.build_payload(source)
        self.assertEqual(payload["temperature"], 0.7)
        self.assertEqual(payload["top_p"], 0.8)
        self.assertEqual(payload["top_k"], 20)
        self.assertEqual(payload["min_p"], 0.0)
        self.assertEqual(payload["presence_penalty"], 1.5)
        self.assertEqual(payload["seed"], 42)
        self.assertEqual(payload["max_tokens"], 512)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][0]["content"], SYSTEM_PROMPT)
        self.assertIn(source, payload["messages"][1]["content"])
        self.assertIn("1000", payload["messages"][1]["content"])
        self.assertIn("800", payload["messages"][1]["content"])
        self.assertNotIn(r"\V[987650]", payload["messages"][1]["content"])
        self.assertIn("/no_think", payload["messages"][1]["content"])

    def test_adapter_returns_model_text_without_target_side_repair(self):
        calls = []

        def fake_request(url, payload, timeout):
            calls.append((url, payload, timeout))
            return {
                "choices": [
                    {"message": {"content": "  Traducción original. \n"}}
                ]
            }

        translator = Qwen8BRecommendedTranslator(request_json=fake_request)
        output = translator.translate("日本語の原文です。")
        self.assertEqual(output, "Traducción original.")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].endswith("/v1/chat/completions"))
        self.assertEqual(calls[0][2], 180)

    def test_empty_source_does_not_call_model(self):
        calls = []

        def fake_request(url, payload, timeout):
            calls.append(url)
            return {}

        translator = Qwen8BRecommendedTranslator(request_json=fake_request)
        with self.assertRaises(TranslationRejected):
            translator.translate("   ")
        self.assertEqual(calls, [])

    def test_invalid_model_response_is_rejected(self):
        translator = Qwen8BRecommendedTranslator(
            request_json=lambda _url, _payload, _timeout: {"choices": []}
        )
        with self.assertRaises(TranslationRejected):
            translator.translate("日本語")

    def test_server_request_errors_are_rejected_not_silently_repaired(self):
        def failing_request(_url, _payload, _timeout):
            raise RuntimeError("offline")

        translator = Qwen8BRecommendedTranslator(request_json=failing_request)
        with self.assertRaises(TranslationRejected):
            translator.translate("日本語")


if __name__ == "__main__":
    unittest.main()
