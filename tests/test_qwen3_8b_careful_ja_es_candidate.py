"""Contract checks for a uniform, source-only Qwen3-8B prompt variant."""
import unittest

from tools.qwen3_8b_careful_ja_es_candidate import (
    CAREFUL_PROMPT, CarefulQwen8BTranslator,
)
from tools.qwen3_8b_ja_es_candidate import Qwen8BTranslator
from tools.independent_pivot_holdout import INDEPENDENT_CASES


class TestCarefulQwen8B(unittest.TestCase):
    def test_payload_keeps_raw_japanese_codes_and_pinned_model(self):
        source = r"明日、\N[3]は午後6時に戻ります。"
        first = Qwen8BTranslator.build_payload(source)
        variant = CarefulQwen8BTranslator.build_payload(source)
        self.assertEqual(first["model"], variant["model"])
        self.assertEqual(first["messages"][1], variant["messages"][1])
        self.assertIn(source, variant["messages"][1]["content"])
        self.assertIn("/no_think", variant["messages"][1]["content"])
        self.assertEqual(variant["messages"][0]["content"], CAREFUL_PROMPT)
        self.assertEqual(variant["temperature"], 0.25)
        self.assertEqual(variant["top_p"], 0.93)
        self.assertEqual(variant["seed"], 512)
        self.assertFalse(variant["stream"])
        self.assertEqual(len(INDEPENDENT_CASES), 20)

    def test_prompt_is_uniform_and_has_no_reference_translations(self):
        prompt = CAREFUL_PROMPT.casefold()
        self.assertIn("preserve every", prompt)
        self.assertIn("idiomatic latin american spanish", prompt)
        self.assertIn("unspecified agent", prompt)
        self.assertNotIn("el pedido de tres libros llegó con dos", prompt)

    def test_adapter_does_not_repair_model_text(self):
        calls = []
        def fake_request(url, payload, timeout):
            calls.append((url, payload, timeout))
            return {"choices": [{"message": {"content": " Traducción original. \n"}}]}
        translator = CarefulQwen8BTranslator(request_json=fake_request)
        self.assertEqual(translator.translate("私は日本語です。"), "Traducción original.")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], 180)
        self.assertEqual(calls[0][1]["messages"][0]["content"], CAREFUL_PROMPT)


if __name__ == "__main__":
    unittest.main()
