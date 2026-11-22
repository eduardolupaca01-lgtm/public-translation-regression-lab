"""Uniform neural translation quality calibration: no reference target edits."""
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.qwen3_8b_thinking_ja_es_candidate import Qwen8BThinkingTranslator
from tools.stage4_source_complete_candidate import (
    GENERATION_VARIANT,
    SOURCE_ACCURACY_GUIDANCE,
    SOURCE_COMPLETE_PROMPT,
    SOURCE_PROMPT_SHA256,
    SourceCompleteThinkingTranslator,
    load_quality_model,
)
from tools.qwen3_stage3_holdout import THINKING_REQUEST_TIMEOUT_SECONDS


class TestStage4SourceCompleteCandidate(unittest.TestCase):
    def test_uniform_request_changes_only_system_prompt(self):
        for japanese in (
            "明日は駅の前で会いましょう。",
            "妹は宿題を終えたら公園へ行きます。",
            r"\N[7]は午後3時に来ます。",
        ):
            original = Qwen8BThinkingTranslator.build_payload(japanese)
            revised = SourceCompleteThinkingTranslator.build_payload(japanese)
            self.assertEqual(original["model"], revised["model"])
            self.assertEqual(original["messages"][1], revised["messages"][1])
            self.assertEqual(revised["messages"][0]["content"], SOURCE_COMPLETE_PROMPT)
            for key in (
                "temperature", "top_p", "top_k", "min_p",
                "presence_penalty", "seed", "max_tokens", "stream",
            ):
                self.assertEqual(original[key], revised[key])
            self.assertIn("/think", revised["messages"][1]["content"])
        self.assertEqual(len(SOURCE_PROMPT_SHA256), 64)
        self.assertEqual(
            GENERATION_VARIANT, "uniform_spatial_agent_agreement_calibration_v1",
        )

    def test_prompt_never_contains_case_specific_spanish_answers(self):
        prompt = SOURCE_ACCURACY_GUIDANCE.casefold()
        self.assertIn("spatial relationship", prompt)
        self.assertIn("agreement", prompt)
        self.assertIn("japanese ambiguity", prompt)
        self.assertNotIn("nos vemos en la estacion", prompt)
        self.assertNotIn("pienso ir al parque juntos", prompt)
        self.assertNotIn("manzana azul", prompt)
        self.assertNotIn("frente a la estacion", prompt)

    def test_response_passes_through_raw_after_removing_reasoning(self):
        requests = []
        def stub(url, payload, timeout):
            requests.append((url, payload, timeout))
            return {
                "choices": [{"message": {
                    "content": "<think>Private test notes.</think>\nUna traducción."}
                }]
            }
        model = SourceCompleteThinkingTranslator(request_json=stub)
        self.assertEqual(model.translate("原文"), "Una traducción.")
        self.assertEqual(len(requests), 1)
        self.assertIs(requests[0][1]["messages"][0]["content"], SOURCE_COMPLETE_PROMPT)
        self.assertEqual(requests[0][2], 180)

    def test_pinned_loader_preserves_sampling_and_uniform_cpu_timeout(self):
        calls = []
        class Fake:
            endpoint = "http://127.0.0.1:8080"
            process = None
            log_handle = None
            def request_json(self, url, payload, timeout):
                calls.append((url, payload, timeout))
                return {"choices": []}

        provenance = [{
            "repo_id": "Qwen/Qwen3-8B-GGUF",
            "revision": "pinned", "sha256": "a"*64,
            "reasoning_mode": "think",
        }]
        with patch(
            "tools.stage4_source_complete_candidate.thinking._load_model",
            return_value=(Fake(), provenance),
        ):
            model, data = load_quality_model(
                Path("/tmp/llama-server"), Path("/tmp/research-candidate")
            )
        payload = model.build_payload("文章。")
        model.request_json("http://localhost/test", payload, 180)
        self.assertEqual(calls[0][2], THINKING_REQUEST_TIMEOUT_SECONDS)
        self.assertIs(calls[0][1], payload)
        self.assertEqual(data[0]["translation_system_prompt_sha256"],
                         SOURCE_PROMPT_SHA256)
        self.assertFalse(data[0]["target_side_repairs"])
        self.assertFalse(data[0]["reference_spanish_provided_to_model"])


if __name__ == "__main__":
    unittest.main()
