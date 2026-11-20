"""Multi-process SQLite acceptance, not evidence of neural translation quality."""
from pathlib import Path
import json
import tempfile
import unittest

from tools.cache_stress import sample, stress
from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import validate_translation


class TestPublicCacheConcurrency(unittest.TestCase):
    def test_synthetic_inputs_preserve_numbers_codes_and_line_endings(self):
        for i in range(36):
            source, value = sample(i)
            with self.subTest(index=i):
                validate_translation(source, value, source="ja")
                if i % 3 == 0:
                    self.assertIn(r"\V[12]", source)
                    self.assertIn(r"\V[12]", value)
                if i % 5 == 0:
                    self.assertIn("\r\n", source)
                    self.assertIn("\r\n", value)

    def test_concurrent_duplicate_requests_use_one_producer_across_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "stress"
            code = stress(workspace, cases=10, workers=4)
            receipt = json.loads(
                (workspace / "cache-stress-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(code, 0, receipt)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(receipt["fake_model_calls"], 10)
            self.assertEqual(receipt["total_requests"], 40)
            self.assertEqual(receipt["duplicate_fake_model_calls"], 0)
            self.assertTrue(receipt["restart_without_model_calls"])
            self.assertTrue(receipt["stale_policy_recovered"])
            self.assertTrue(receipt["worker_crash_recovered"])
            with DurableTranslationCache(workspace / "cache") as cache:
                self.assertEqual(cache.count(), 12)


if __name__ == "__main__":
    unittest.main()
