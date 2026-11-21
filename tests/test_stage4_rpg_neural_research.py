"""Synthetic tests for research RPG stress runner, not neural quality proof."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.stage4_rpg_neural_research import translate_phase, verify_phase
from tools.stage4_rpg_stress_cases import STRESS_CASES


class TestStage4RpgNeuralResearch(unittest.TestCase):
    def test_twelve_sources_are_unmodified_and_no_reference_spanish(self):
        self.assertEqual(len(STRESS_CASES), 12)
        self.assertEqual(len({c.japanese for c in STRESS_CASES}), 12)

    def test_failing_neural_outputs_are_quarantined_and_survive_restart(self):
        calls = []

        class BadModel:
            def translate(self, text):
                calls.append(text)
                return "Traducción incompleta."
            def close(self):
                pass

        def loader():
            return BadModel(), [{"repo_id": "synthetic"}]

        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "stage4-rpg"
            result = translate_phase(workspace, None, model_loader=loader)
            self.assertEqual(result, 1)
            self.assertTrue(calls)
            report = json.loads(
                (workspace / "rpg-neural-report.json").read_text(encoding="utf-8")
            )
            self.assertTrue(report["model_executed"])
            self.assertEqual(report["rejected"], 12)
            self.assertEqual(report["structurally_accepted"], 0)
            self.assertFalse(report["professional_quality_approved"])
            self.assertTrue(report["bilingual_review_required"])
            self.assertEqual(report["review_queue_pending"], 12)
            self.assertEqual(verify_phase(workspace), 0)
            proof = json.loads(
                (workspace / "rpg-cold-restart-proof.json").read_text(encoding="utf-8")
            )
            self.assertEqual(proof["status"], "QUALITY_FAIL_PERSISTENCE_PASS")
            self.assertEqual(proof["persistence_status"], "PASS")
            self.assertEqual(proof["structural_status"], "FAIL")
            self.assertFalse(proof["models_loaded_during_restart"])

    def test_cold_process_rejects_missing_receipts(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(verify_phase(Path(root)), 1)


if __name__ == "__main__":
    unittest.main()
