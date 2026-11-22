"""Stage3 cannot be entered by partial scores or human-edited candidates."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_stage3_readiness import valid_receipts
from tools.qwen3_stage3_holdout import (
    THINKING_REQUEST_TIMEOUT_SECONDS,
    THINKING_SCHEMA,
    _load_pinned_model,
    translate_phase,
    verify_phase,
)
from tools.unseen_holdout import HOLDOUT_CASES


class TestQwen8BStage3(unittest.TestCase):
    def test_thinking_timeout_is_uniform_and_preserves_request_payload(self):
        calls = []

        class FakeModel:
            def __init__(self):
                self.request_json = self.send

            def send(self, url, payload, timeout):
                calls.append((url, payload, timeout))
                return {"choices": []}

        model = FakeModel()
        provenance = [{"repo_id": "Qwen/Qwen3-8B-GGUF"}]
        with patch(
            "tools.qwen3_stage3_holdout.thinking._load_model",
            return_value=(model, provenance),
        ):
            loaded, metadata = _load_pinned_model(
                THINKING_SCHEMA, Path("/tmp/pinned-server"), Path("/tmp/research")
            )

        self.assertIs(model, loaded)
        self.assertEqual(THINKING_REQUEST_TIMEOUT_SECONDS, 720)
        self.assertEqual(metadata[0]["http_request_timeout_seconds"], 720)
        payload = {
            "model": "Qwen3-8B-GGUF",
            "seed": 42,
            "messages": [{"role": "user", "content": "明日の午後、駅で会いましょう。"}],
        }
        loaded.request_json("http://localhost/test", payload, 180)
        loaded.request_json("http://localhost/test", payload, 900)
        self.assertEqual(calls[0], ("http://localhost/test", payload, 720))
        self.assertEqual(calls[1], ("http://localhost/test", payload, 900))
        self.assertIs(calls[0][1], payload)

    def test_partial_development_blocks_before_workspace_and_model_loading(self):
        report, proof = valid_receipts()
        report["cases"] = report["cases"][:17]
        report["accepted"] = 17
        report["rejected"] = 3
        report["cache_rows"] = 17
        report["review_queue_total"] = 3
        was_loaded = []

        def forbidden_loader():
            was_loaded.append(True)
            raise AssertionError("MODEL_SHOULD_NOT_LOAD")

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            dev = base / "dev.json"
            restart = base / "restart.json"
            target = base / "stage3"
            dev.write_text(json.dumps(report), encoding="utf-8")
            restart.write_text(json.dumps(proof), encoding="utf-8")
            result = translate_phase(
                target, dev, restart, None, model_loader=forbidden_loader
            )
            self.assertEqual(result, 1)
            self.assertFalse(target.exists())
            self.assertFalse(was_loaded)

    def test_rejected_raw_outputs_remain_pending_after_cold_restart(self):
        report, proof = valid_receipts()
        calls = []

        class StubTranslator:
            def translate(self, text):
                calls.append(text)
                return "Traducción incompleta."

            def close(self):
                pass

        def stub_loader():
            return StubTranslator(), [report["models"][0]]

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            dev = base / "dev.json"
            restart = base / "restart.json"
            target = base / "stage3"
            dev.write_text(json.dumps(report), encoding="utf-8")
            restart.write_text(json.dumps(proof), encoding="utf-8")

            self.assertEqual(
                translate_phase(
                    target, dev, restart, None,
                    model_loader=stub_loader,
                ), 1
            )
            self.assertTrue(calls)
            raw = json.loads(
                (target / "stage3-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(raw["status"], "FAIL")
            self.assertEqual(raw["accepted"], 0)
            self.assertEqual(raw["rejected"], 10)
            self.assertEqual(raw["cache_rows"], 0)
            self.assertEqual(raw["review_queue_pending"], 10)

            self.assertEqual(verify_phase(target), 0)
            cold = json.loads(
                (target / "stage3-restart-proof.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(cold["status"], "QUALITY_FAIL_PERSISTENCE_PASS")
            self.assertEqual(cold["persistence_status"], "PASS")
            self.assertEqual(cold["quality_status"], "FAIL")
            self.assertFalse(cold["models_loaded_during_restart"])

    def test_cold_restart_requires_receipts_not_just_a_directory(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(verify_phase(Path(root)), 1)

    def test_source_only_holdout_is_disjoint_and_nonempty(self):
        from tools.stage3_readiness import source_only_manifest
        from tools.independent_pivot_holdout import INDEPENDENT_CASES
        self.assertEqual(len(HOLDOUT_CASES), 10)
        manifest = source_only_manifest()
        self.assertEqual(manifest["count"], 10)
        self.assertEqual(
            [case["source"] for case in manifest["cases"]],
            [case.japanese for case in HOLDOUT_CASES],
        )
        self.assertFalse(
            {case.japanese for case in HOLDOUT_CASES}
            & {case.japanese for case in INDEPENDENT_CASES}
        )
        self.assertTrue(
            all(set(c) == {"case", "source"} for c in manifest["cases"])
        )


if __name__ == "__main__":
    unittest.main()
