"""Offline contract tests for the pinned Qwen3 candidate."""
import unittest

from tools.qwen3_ja_es_candidate import (
    BASE_MODEL,
    CONTEXTUALIZE_NAME_CODES,
    DECLARED_LICENSE,
    LLAMA_CPP_RELEASE,
    MODEL_FILENAME,
    MODEL_REPO,
    MODEL_REVISION,
    MODEL_SHA256,
    PROTECT_NUMBERS,
    PROTECT_LITERALS_IN_CONTEXT,
    QUANTIZATION,
    SYSTEM_PROMPT,
    QwenTranslator,
)
from tools.independent_pivot_holdout import INDEPENDENT_CASES
from translation_lab.pipeline import TranslationRejected


class TestQwenCandidateContracts(unittest.TestCase):
    def test_model_and_runtime_are_pinned(self):
        self.assertEqual(BASE_MODEL, "Qwen/Qwen3-4B-Instruct-2507")
        self.assertEqual(MODEL_REPO, "lmstudio-community/Qwen3-4B-Instruct-2507-GGUF")
        self.assertRegex(MODEL_REVISION, r"^[0-9a-f]{40}$")
        self.assertEqual(MODEL_FILENAME, "Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
        self.assertRegex(MODEL_SHA256, r"^[0-9a-f]{64}$")
        self.assertEqual(DECLARED_LICENSE, "apache-2.0")
        self.assertEqual(QUANTIZATION, "Q4_K_M")
        self.assertEqual(LLAMA_CPP_RELEASE, "b12584")

    def test_control_codes_and_numbers_use_structural_protection(self):
        self.assertTrue(PROTECT_NUMBERS)
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
            "zxqphcode0000qxz",
            "exactly once",
            "grammatically correct spanish position",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prompt)

    def test_candidate_uses_the_same_twenty_case_development_set(self):
        self.assertEqual(len(INDEPENDENT_CASES), 20)
        self.assertEqual(len({case.id for case in INDEPENDENT_CASES}), 20)
        self.assertEqual(len({case.japanese for case in INDEPENDENT_CASES}), 20)

    def test_payload_uses_deterministic_non_streaming_chat_completion(self):
        payload = QwenTranslator.build_payload("明日は雨です。")
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(payload["top_p"], 1.0)
        self.assertEqual(payload["seed"], 42)
        self.assertEqual(payload["max_tokens"], 256)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][0]["content"], SYSTEM_PROMPT)
        self.assertIn("明日は雨です。", payload["messages"][1]["content"])

    def test_adapter_returns_model_text_without_target_side_repair(self):
        calls = []

        def fake_request(url, payload, timeout):
            calls.append((url, payload, timeout))
            return {
                "choices": [
                    {"message": {"content": "  Traducción original. \n"}}
                ]
            }

        translator = QwenTranslator(request_json=fake_request)
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

        translator = QwenTranslator(request_json=fake_request)
        with self.assertRaises(TranslationRejected):
            translator.translate("   ")
        self.assertEqual(calls, [])

    def test_invalid_model_response_is_rejected(self):
        translator = QwenTranslator(
            request_json=lambda _url, _payload, _timeout: {"choices": []}
        )
        with self.assertRaises(TranslationRejected):
            translator.translate("日本語")

    def test_server_request_errors_are_rejected_not_silently_repaired(self):
        def failing_request(_url, _payload, _timeout):
            raise RuntimeError("offline")

        translator = QwenTranslator(request_json=failing_request)
        with self.assertRaises(TranslationRejected):
            translator.translate("日本語")


if __name__ == "__main__":
    unittest.main()
