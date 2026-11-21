"""Persistence checks for partially accepted neural translation candidates.

A rejected translation is expected to remain in the human-review queue. This
module distinguishes durable accepted rows from unresolved quality failures.
"""
from __future__ import annotations

from typing import Protocol


class Countable(Protocol):
    def count(self, status: str | None = None) -> int:
        """Return all rows, or rows matching a status."""


def verify_candidate_persistence(
    cache: Countable,
    review_queue: Countable,
    *,
    accepted_count: int,
    rejected_count: int,
    prefix: str,
) -> list[str]:
    """Check persistence without treating expected pending reviews as corruption.

    Quality acceptance is reported separately by each candidate runner. This
    helper only checks whether accepted translations and rejected review items
    survived a cold restart without human approvals changing the automatic run.
    """
    if accepted_count < 0 or rejected_count < 0:
        raise ValueError("NEGATIVE_CANDIDATE_ROW_COUNT")
    if not prefix or not prefix.replace("_", "").isalnum():
        raise ValueError("INVALID_CANDIDATE_ERROR_PREFIX")

    errors: list[str] = []
    if cache.count() != accepted_count:
        errors.append(prefix + "_CACHE_ROW_COUNT_MISMATCH")

    if review_queue.count("approved") != 0:
        errors.append(prefix + "_HUMAN_REVIEW_CHANGED_AUTOMATIC_RESULT")

    if review_queue.count("pending") != rejected_count:
        errors.append(prefix + "_REVIEW_QUEUE_PENDING_COUNT_MISMATCH")

    if review_queue.count() != rejected_count:
        errors.append(prefix + "_REVIEW_QUEUE_TOTAL_COUNT_MISMATCH")

    return errors
