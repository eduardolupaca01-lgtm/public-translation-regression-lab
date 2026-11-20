"""Offline contract tests for the two-stage pivot evaluation."""
import unittest

from tools.pivot_holdout import (
    DECLARED_LICENSE, EN_ES_MODEL_ID, JA_EN_MODEL_ID
)
from tools.unseen_holdout import HOLDOUT_CASES


class TestPivotHoldoutContracts(unittest.TestCase):
    def test_both_pivot_models_have_expected_public_provenance(self):
        self.assertEqual(JA_EN_MODEL_ID, "Helsinki-NLP/opus-mt-ja-en")
        self.assertEqual(EN_ES_MODEL_ID, "Helsinki-NLP/opus-mt-en-es")
        self.assertEqual(DECLARED_LICENSE, "apache-2.0")

    def test_pivot_uses_same_fixed_holdout(self):
        self.assertEqual(len(HOLDOUT_CASES), 10)
        self.assertEqual(len({case.japanese for case in HOLDOUT_CASES}), 10)


if __name__ == "__main__":
    unittest.main()
