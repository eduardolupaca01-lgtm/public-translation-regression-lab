"""The neural holdout must quarantine every rejected proposal for human review."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.unseen_holdout import translate_phase
from translation_lab.cache import DurableTranslationCache
from translation_lab.review_queue import ReviewQueue


class _AlwaysWrongModel:
    def translate(self, _fragment: str) -> str:
        return "traducción incorrecta"


class TestHoldoutReviewQueueIntegration(unittest.TestCase):
    def test_all_rejected_outputs_are_saved_for_review_not_in_accepted_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "fresh-run"
            with patch(
                "tools.unseen_holdout._load_public_research_model",
                return_value=(_AlwaysWrongModel(), [{"model_id": "test-fake"}]),
            ):
                result = translate_phase(workspace)

            self.assertEqual(result, 1)
            report = json.loads(
                (workspace / "holdout-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["accepted"], 0)
            self.assertEqual(report["rejected"], 10)
            self.assertEqual(report["review_queue_pending"], 10)
            self.assertTrue((workspace / "review-queue.json").is_file())

            with DurableTranslationCache(workspace / "cache") as cache:
                self.assertEqual(cache.count(), 0)

            with ReviewQueue(workspace / "cache") as queue:
                self.assertEqual(queue.count("pending"), 10)
                for case in report["cases"]:
                    item = queue.get(case["review_item_id"])
                    self.assertIsNotNone(item)
                    self.assertEqual(item.status, "pending")
                    self.assertEqual(item.original, case["source"])
                    self.assertEqual(item.context["case_id"], case["case"])
                    self.assertIn("raw_model_attempts", item.context)


if __name__ == "__main__":
    unittest.main()
