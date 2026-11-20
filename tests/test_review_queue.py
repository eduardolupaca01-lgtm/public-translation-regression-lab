"""Persistence, fail-closed approval and audit tests for the human review queue."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import TranslationRejected
from translation_lab.review_queue import (
    InvalidReviewState,
    ReviewConflict,
    ReviewQueue,
    ReviewQueueError,
)


class TestHumanReviewQueue(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "cache"

    def tearDown(self):
        self.temp.cleanup()

    def enqueue(self, proposed="La escuela."):
        with ReviewQueue(self.workspace) as queue:
            return queue.enqueue(
                "ja", "es", "学校。", proposed,
                reason="SEMANTIC_VALIDATION_FAILED",
                context={"case_id": "school", "attempts": [{"raw_output": proposed}]},
            )

    def test_rejected_candidate_is_durable_but_never_accepted(self):
        item = self.enqueue("La escuela.")
        with DurableTranslationCache(self.workspace) as cache:
            self.assertIsNone(cache.get("ja", "es", "学校。"))
            self.assertEqual(cache.count(), 0)
        with ReviewQueue(self.workspace) as queue:
            restored = queue.get(item.item_id)
            self.assertEqual(restored.status, "pending")
            self.assertEqual(restored.proposed, "La escuela.")
            self.assertEqual(restored.context["case_id"], "school")
            self.assertEqual(queue.count("pending"), 1)

    def test_enqueue_is_idempotent_and_survives_restart(self):
        first = self.enqueue()
        with ReviewQueue(self.workspace) as queue:
            second = queue.enqueue(
                "ja", "es", "学校。", "La escuela.",
                reason="A_DIFFERENT_OBSERVATION",
            )
            self.assertEqual(first.item_id, second.item_id)
            self.assertEqual(queue.count(), 1)
            self.assertEqual(len(queue.events(first.item_id)), 2)
            self.assertEqual(
                queue.events(first.item_id)[-1]["event_type"],
                "duplicate_observed",
            )
            self.assertEqual(
                queue.events(first.item_id)[-1]["payload"]["reason"],
                "A_DIFFERENT_OBSERVATION",
            )
        with ReviewQueue(self.workspace) as queue:
            self.assertEqual(queue.get(first.item_id).revision, 1)

    def test_empty_candidate_can_be_queued_without_entering_cache(self):
        item = self.enqueue("")
        self.assertEqual(item.proposed, "")
        with DurableTranslationCache(self.workspace) as cache:
            self.assertEqual(cache.count(), 0)

    def test_structural_failure_is_audited_and_keeps_item_pending(self):
        with ReviewQueue(self.workspace) as queue:
            item = queue.enqueue(
                "ja", "es", r"\N[7]学校。", "La escuela.",
                reason="CONTROL_CODE_LOST",
            )
            with self.assertRaisesRegex(
                TranslationRejected, "ORIGINAL_CONTROL_CODES_CHANGED"
            ):
                queue.approve(
                    item.item_id, "La escuela.",
                    actor="reviewer", expected_revision=1,
                    human_verified=True,
                    notes="Revisé el texto y detecté pérdida del código.",
                )
            self.assertEqual(queue.get(item.item_id).status, "pending")
            self.assertEqual(
                queue.events(item.item_id)[-1]["event_type"],
                "approval_validation_failed",
            )
        with DurableTranslationCache(self.workspace) as cache:
            self.assertEqual(cache.count(), 0)

    def test_semantic_validator_failure_is_audited_without_promotion(self):
        with ReviewQueue(self.workspace) as queue:
            item = queue.enqueue(
                "ja", "es", "学校。", "La escuela.",
                reason="ROLE_RELATION_UNCERTAIN",
            )

            def reject_semantics(_candidate):
                raise TranslationRejected("SUBJECT_ROLE_NOT_VERIFIED")

            with self.assertRaisesRegex(
                TranslationRejected, "SUBJECT_ROLE_NOT_VERIFIED"
            ):
                queue.approve(
                    item.item_id, "La escuela.",
                    actor="reviewer", expected_revision=1,
                    human_verified=True,
                    notes="La revisión semántica no confirma el sujeto.",
                    quality_validator=reject_semantics,
                )
            self.assertEqual(queue.get(item.item_id).status, "pending")
            self.assertEqual(
                queue.events(item.item_id)[-1]["payload"]["error"],
                "SUBJECT_ROLE_NOT_VERIFIED",
            )
        with DurableTranslationCache(self.workspace) as cache:
            self.assertEqual(cache.count(), 0)

    def test_semantic_policy_requires_matching_validator(self):
        with ReviewQueue(self.workspace) as queue:
            item = queue.enqueue(
                "ja", "es", "雨が降ったら待っています。", "Cuando llueve, espero.",
                reason="SEMANTIC_VALIDATION_FAILED",
                context={
                    "case_id": "rainy_meeting",
                    "semantic_policy": "unseen_holdout_v1",
                },
            )
            with self.assertRaisesRegex(
                ReviewQueueError, "REVIEW_SEMANTIC_VALIDATOR_REQUIRED"
            ):
                queue.approve(
                    item.item_id, "Cuando llueve, espero.",
                    actor="reviewer", expected_revision=1,
                    human_verified=True,
                    notes="Revisé el texto.",
                )
            self.assertEqual(queue.get(item.item_id).status, "pending")

    def test_human_verification_and_notes_are_mandatory(self):
        with ReviewQueue(self.workspace) as queue:
            item = queue.enqueue(
                "ja", "es", "学校。", "La escuela.", reason="NEEDS_REVIEW"
            )
            with self.assertRaisesRegex(
                ValueError, "EXPLICIT_HUMAN_SEMANTIC_VERIFICATION_REQUIRED"
            ):
                queue.approve(
                    item.item_id, "La escuela.",
                    actor="reviewer", expected_revision=1,
                    human_verified=False, notes="No se verificó el significado.",
                )
            with self.assertRaisesRegex(ValueError, "REVIEW_DECISION_NOTES_REQUIRED"):
                queue.approve(
                    item.item_id, "La escuela.",
                    actor="reviewer", expected_revision=1,
                    human_verified=True, notes=" ",
                )
            self.assertEqual(queue.get(item.item_id).status, "pending")

    def test_approval_promotes_atomically_and_supersedes_competing_candidates(self):
        with DurableTranslationCache(self.workspace) as cache, ReviewQueue(self.workspace) as queue:
            first = queue.enqueue(
                "ja", "es", "学校。", "La escuela.",
                reason="CANDIDATE_A",
            )
            second = queue.enqueue(
                "ja", "es", "学校。", "El colegio.",
                reason="CANDIDATE_B",
            )
            approved = queue.approve(
                first.item_id, "El colegio.",
                actor="reviewer", expected_revision=1,
                human_verified=True,
                notes="Verifiqué el significado y la referencia al lugar.",
            )
            self.assertEqual(approved.status, "approved")
            self.assertEqual(approved.reviewer, "reviewer")
            self.assertEqual(approved.correction, "El colegio.")
            self.assertEqual(cache.get("ja", "es", "学校。"), "El colegio.")
            self.assertEqual(cache.count(), 1)
            self.assertEqual(queue.get(second.item_id).status, "superseded")
            self.assertEqual(
                queue.events(first.item_id)[-1]["event_type"], "approved"
            )
            with self.assertRaises(InvalidReviewState):
                queue.approve(
                    second.item_id, "El colegio.",
                    actor="reviewer", expected_revision=1,
                    human_verified=True, notes="No debe aprobarse dos veces.",
                )

    def test_existing_accepted_value_requires_explicit_replacement(self):
        with DurableTranslationCache(self.workspace) as cache, ReviewQueue(self.workspace) as queue:
            cache.put("ja", "es", "学校。", "La escuela.")
            item = queue.enqueue(
                "ja", "es", "学校。", "El colegio.",
                reason="REVIEWED_ALTERNATIVE",
            )
            with self.assertRaisesRegex(
                ReviewConflict, "REPLACE_FLAG_REQUIRED"
            ):
                queue.approve(
                    item.item_id, "El colegio.",
                    actor="reviewer", expected_revision=1,
                    human_verified=True,
                    notes="La corrección revisada es más precisa.",
                )
            self.assertEqual(cache.get("ja", "es", "学校。"), "La escuela.")
            self.assertEqual(queue.get(item.item_id).status, "pending")
            approved = queue.approve(
                item.item_id, "El colegio.",
                actor="reviewer", expected_revision=1,
                human_verified=True,
                notes="Confirmé que reemplaza la versión anterior.",
                replace_existing=True,
            )
            self.assertEqual(approved.status, "approved")
            self.assertEqual(cache.get("ja", "es", "学校。"), "El colegio.")

    def test_stale_revision_cannot_approve_reopened_item(self):
        with ReviewQueue(self.workspace) as queue:
            item = queue.enqueue(
                "ja", "es", "学校。", "La escuela.", reason="NEEDS_REVIEW"
            )
            rejected = queue.reject(
                item.item_id, actor="reviewer", expected_revision=1,
                reason="La propuesta necesita corrección.",
            )
            reopened = queue.revise(
                item.item_id, "El colegio.",
                actor="reviewer", expected_revision=rejected.revision,
                reason="Se incorporó una propuesta corregida.",
            )
            self.assertEqual(reopened.status, "pending")
            self.assertEqual(reopened.revision, 3)
            with self.assertRaises(ReviewConflict):
                queue.approve(
                    item.item_id, "El colegio.",
                    actor="reviewer", expected_revision=2,
                    human_verified=True,
                    notes="Intento obsoleto.",
                )
            approved = queue.approve(
                item.item_id, "El colegio.",
                actor="reviewer", expected_revision=3,
                human_verified=True,
                notes="Verifiqué la nueva revisión.",
            )
            self.assertEqual(approved.status, "approved")

    def test_snapshot_exports_items_and_append_only_events(self):
        item = self.enqueue()
        destination = self.workspace / "review-queue.json"
        with ReviewQueue(self.workspace) as queue:
            queue.export_snapshot(destination)
        data = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "translation-human-review-queue-v1")
        self.assertEqual(data["items"][0]["item_id"], item.item_id)
        self.assertEqual(data["events"][0]["event_type"], "queued")


if __name__ == "__main__":
    unittest.main()
