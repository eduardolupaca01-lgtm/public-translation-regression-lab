"""Offline contract tests for the permissive-license model comparison."""
import unittest

from tools.permissive_holdout import MODEL_SPECS
from tools.unseen_holdout import HOLDOUT_CASES


class TestPermissiveHoldoutContracts(unittest.TestCase):
    def test_candidate_models_have_explicit_public_provenance(self):
        self.assertEqual(set(MODEL_SPECS), {"marian", "m2m100"})
        self.assertEqual(
            MODEL_SPECS["marian"].model_id, "Helsinki-NLP/opus-mt-ja-es"
        )
        self.assertEqual(MODEL_SPECS["marian"].declared_license, "apache-2.0")
        self.assertEqual(
            MODEL_SPECS["m2m100"].model_id, "facebook/m2m100_418M"
        )
        self.assertEqual(MODEL_SPECS["m2m100"].declared_license, "mit")

    def test_both_models_use_the_same_fixed_ten_case_holdout(self):
        self.assertEqual(len(HOLDOUT_CASES), 10)
        self.assertEqual(len({case.japanese for case in HOLDOUT_CASES}), 10)


if __name__ == "__main__":
    unittest.main()
