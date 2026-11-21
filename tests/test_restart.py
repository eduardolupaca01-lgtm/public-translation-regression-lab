"""Tests for cold-restart persistence accounting."""
import unittest

from translation_lab.restart import verify_candidate_persistence


class FakeCountable:
    def __init__(self, total=0, statuses=None):
        self.total = total
        self.statuses = dict(statuses or {})

    def count(self, status=None):
        if status is None:
            return self.total
        return self.statuses.get(status, 0)


class TestCandidatePersistence(unittest.TestCase):
    def test_partial_quality_run_with_pending_reviews_is_persisted(self):
        cache = FakeCountable(total=16)
        queue = FakeCountable(
            total=4, statuses={"pending": 4, "approved": 0}
        )
        self.assertEqual(
            verify_candidate_persistence(
                cache, queue, accepted_count=16, rejected_count=4,
                prefix="QWEN8B",
            ),
            [],
        )

    def test_fully_accepted_run_has_empty_review_queue(self):
        cache = FakeCountable(total=20)
        queue = FakeCountable(total=0)
        self.assertEqual(
            verify_candidate_persistence(
                cache, queue, accepted_count=20, rejected_count=0,
                prefix="MADLAD",
            ),
            [],
        )

    def test_missing_cache_row_is_detected(self):
        cache = FakeCountable(total=15)
        queue = FakeCountable(total=5, statuses={"pending": 5})
        self.assertEqual(
            verify_candidate_persistence(
                cache, queue, accepted_count=16, rejected_count=4,
                prefix="QWEN",
            ),
            ["QWEN_CACHE_ROW_COUNT_MISMATCH",
             "QWEN_REVIEW_QUEUE_PENDING_COUNT_MISMATCH",
             "QWEN_REVIEW_QUEUE_TOTAL_COUNT_MISMATCH"],
        )

    def test_human_approval_cannot_change_automatic_score(self):
        cache = FakeCountable(total=17)
        queue = FakeCountable(
            total=4, statuses={"pending": 3, "approved": 1}
        )
        errors = verify_candidate_persistence(
            cache, queue, accepted_count=16, rejected_count=4,
            prefix="QWEN8BTHINK",
        )
        self.assertIn(
            "QWEN8BTHINK_HUMAN_REVIEW_CHANGED_AUTOMATIC_RESULT", errors
        )
        self.assertIn(
            "QWEN8BTHINK_REVIEW_QUEUE_PENDING_COUNT_MISMATCH", errors
        )

    def test_extra_review_rows_are_detected(self):
        cache = FakeCountable(total=16)
        queue = FakeCountable(
            total=5, statuses={"pending": 4, "rejected": 1}
        )
        self.assertEqual(
            verify_candidate_persistence(
                cache, queue, accepted_count=16, rejected_count=4,
                prefix="MADLAD",
            ),
            ["MADLAD_REVIEW_QUEUE_TOTAL_COUNT_MISMATCH"],
        )

    def test_negative_counts_and_invalid_prefix_are_rejected(self):
        cache = FakeCountable()
        queue = FakeCountable()
        with self.assertRaises(ValueError):
            verify_candidate_persistence(
                cache, queue, accepted_count=-1, rejected_count=1,
                prefix="QWEN",
            )
        with self.assertRaises(ValueError):
            verify_candidate_persistence(
                cache, queue, accepted_count=0, rejected_count=0,
                prefix="",
            )


if __name__ == "__main__":
    unittest.main()
