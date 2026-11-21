"""Synthetic contract tests: do not mistake fixtures for neural approval."""
import copy
import hashlib
import unittest

from test_independent_pivot_holdout import REFERENCE_TRANSLATIONS
from tools.independent_pivot_holdout import INDEPENDENT_CASES, SEMANTIC_POLICY_VERSION
from tools.qwen3_8b_thinking_ja_es_candidate import (
    MODEL_REPO, MODEL_REVISION, MODEL_SHA256,
)
from tools.stage3_readiness import promotion_errors, source_only_manifest
from tools.unseen_holdout import HOLDOUT_CASES


def valid_receipts():
    cases = []
    for case in INDEPENDENT_CASES:
        translated = REFERENCE_TRANSLATIONS[case.id]
        cases.append({
            "case": case.id, "source": case.japanese, "status": "accepted",
            "translated": translated,
            "sha256": hashlib.sha256(translated.encode("utf-8")).hexdigest(),
            "raw_model_attempts": [{"mode": "fixture", "raw_output": translated}],
        })
    report = {
        "schema": "public-qwen3-8b-thinking-ja-es-candidate-v1",
        "status": "PASS", "backend_executed": True,
        "accepted": 20, "rejected": 0, "required": 20,
        "cache_rows": 20, "review_queue_total": 0,
        "cases": cases,
        "expected_model": {
            "repo_id": MODEL_REPO, "revision": MODEL_REVISION,
            "sha256": MODEL_SHA256,
        },
        "models": [{
            "repo_id": MODEL_REPO, "sha256": MODEL_SHA256,
            "declared_license": "apache-2.0",
        }],
        "evaluation_policy": {
            "semantic_policy_version": SEMANTIC_POLICY_VERSION,
            "case_set_status": "published_development_regression_set_not_blind",
            "case_sources_unchanged": True,
            "human_approvals": False, "target_repairs": False,
            "source_paraphrases": False, "case_specific_retries": False,
            "glossary_edits": False, "all_cases_required": True,
        },
    }
    restart = {
        "status": "PASS", "accepted": 20, "required": 20,
        "quality_status": "PASS", "persistence_status": "PASS",
        "models_loaded_during_restart": False, "errors": [],
        "quality_errors": [], "persistence_errors": [],
    }
    return report, restart


class TestStage3Readiness(unittest.TestCase):
    def test_complete_synthetic_receipts_satisfy_promotion_contract(self):
        report, restart = valid_receipts()
        self.assertEqual(promotion_errors(report, restart), [])

    def test_complete_careful_candidate_requires_pinned_generation_metadata(self):
        report, restart = valid_receipts()
        report["schema"] = "public-qwen3-8b-careful-ja-es-candidate-v1"
        report["evaluation_policy"]["generation_variant"] = (
            "uniform_source_only_careful_prompt"
        )
        report["generation_parameters"] = {
            "temperature": 0.25, "top_p": 0.93,
            "seed": 512, "source_only_prompt": True,
        }
        self.assertEqual(promotion_errors(report, restart), [])
        report["generation_parameters"]["top_p"] = 1
        self.assertIn(
            "CAREFUL_GENERATION_PROVENANCE_CHANGED",
            promotion_errors(report, restart),
        )

    def test_two_pass_promotion_requires_full_neural_review_provenance(self):
        report, restart = valid_receipts()
        report["schema"] = "public-qwen3-8b-two-pass-ja-es-candidate-v1"
        report["evaluation_policy"].update({
            "generation_variant": "uniform_neural_two_pass_revision",
            "two_neural_passes_for_every_request": True,
            "scripted_target_repairs": False,
        })
        report["generation_parameters"] = {
            "draft": {"temperature": 0.25, "top_p": 0.93, "seed": 512},
            "review": {"temperature": 0.0, "top_p": 1.0, "seed": 513},
            "same_pinned_model_for_both": True,
        }
        report["neural_review_history"] = [
            {"source": "fixture", "draft": "draft", "reviewed": "reviewed"}
        ]
        self.assertEqual(promotion_errors(report, restart), [])
        del report["neural_review_history"]
        self.assertIn(
            "TWO_PASS_RAW_REVIEW_EVIDENCE_MISSING",
            promotion_errors(report, restart),
        )
        report["neural_review_history"] = [{"source": "fixture"}]
        report["generation_parameters"]["review"]["seed"] = 42
        self.assertIn(
            "TWO_PASS_GENERATION_PROVENANCE_CHANGED",
            promotion_errors(report, restart),
        )

    def test_partial_sixteen_of_twenty_does_not_promote(self):
        report, restart = valid_receipts()
        report["cases"] = report["cases"][:16]
        report["accepted"] = 16
        report["rejected"] = 4
        report["cache_rows"] = 16
        report["review_queue_total"] = 4
        self.assertIn(
            "DEVELOPMENT_NOT_FULLY_ACCEPTED",
            promotion_errors(report, restart),
        )

    def test_rejected_semantic_omission_and_changed_hash_both_block(self):
        report, restart = valid_receipts()
        target = next(row for row in report["cases"]
                      if row["case"] == "ordered_books_arrived")
        target["translated"] = "Los libros que pedí no fueron tres, sino dos."
        errors = promotion_errors(report, restart)
        self.assertIn(
            "SEMANTIC_CHECK_FAILED:ordered_books_arrived", errors
        )
        self.assertIn(
            "TRANSLATION_RECEIPT_HASH_MISMATCH:ordered_books_arrived", errors
        )

    def test_missing_optional_legacy_digest_still_requires_semantic_and_restart_proofs(self):
        report, restart = valid_receipts()
        for row in report["cases"]:
            del row["sha256"]
        self.assertEqual(promotion_errors(report, restart), [])
        restart["persistence_status"] = "FAIL"
        self.assertIn(
            "COLD_RESTART_PROOF_INCOMPLETE",
            promotion_errors(report, restart),
        )

    def test_changed_japanese_source_blocks_promotion(self):
        report, restart = valid_receipts()
        report["cases"][0]["source"] = "異なる文。"
        self.assertIn(
            "JAPANESE_SOURCE_CHANGED:meeting_time_contrast",
            promotion_errors(report, restart),
        )

    def test_restart_failure_and_human_approval_block(self):
        report, restart = valid_receipts()
        report["evaluation_policy"]["human_approvals"] = True
        restart["persistence_status"] = "FAIL"
        errors = promotion_errors(report, restart)
        self.assertIn("EVALUATION_POLICY_PROVENANCE_CHANGED", errors)
        self.assertIn("COLD_RESTART_PROOF_INCOMPLETE", errors)

    def test_next_stage_has_source_only_disjoint_frozen_cases(self):
        manifest = source_only_manifest()
        self.assertEqual(manifest["count"], 10)
        self.assertEqual(len(manifest["sha256"]), 64)
        self.assertEqual(len(HOLDOUT_CASES), 10)
        self.assertFalse(
            {case.japanese for case in HOLDOUT_CASES}
            & {case.japanese for case in INDEPENDENT_CASES}
        )
        self.assertTrue(all(set(case) == {"case", "source"}
                            for case in manifest["cases"]))
        self.assertNotIn("translated", str(manifest["cases"]))


if __name__ == "__main__":
    unittest.main()
