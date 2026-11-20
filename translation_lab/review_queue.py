"""Durable, fail-closed human review queue sharing the accepted SQLite cache.

Rejected model output is stored here, never in the translations table. A
human-approved correction is structurally revalidated and promoted to the
accepted cache in the same SQLite transaction as its approval/audit event.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from collections.abc import Callable, Mapping
from typing import Any

from .pipeline import TranslationRejected, validate_translation

STATUSES = ("pending", "approved", "rejected", "superseded")


class ReviewQueueError(RuntimeError):
    """Base class for review queue state and persistence errors."""


class ReviewNotFound(ReviewQueueError):
    """The requested review item does not exist."""


class ReviewConflict(ReviewQueueError):
    """The item changed or an accepted translation already exists."""


class InvalidReviewState(ReviewQueueError):
    """The requested transition is not allowed from the current state."""


@dataclass(frozen=True)
class ReviewItem:
    item_id: str
    source: str
    target: str
    original: str
    proposed: str
    reason: str
    context: dict[str, Any]
    status: str
    revision: int
    created_at: str
    updated_at: str
    reviewer: str | None
    correction: str | None
    decision_notes: str | None
    approved_at: str | None


class ReviewQueue:
    """Append-only review history and atomic promotion into translation cache."""

    def __init__(self, directory: str | Path):
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "translation-cache.sqlite3"
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout=30000")
        self.connection.execute("PRAGMA journal_mode=DELETE")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS translations(
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    original TEXT NOT NULL,
                    translated TEXT NOT NULL,
                    PRIMARY KEY(source, target, original)
                )
            """)
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS review_queue_items(
                    item_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    original TEXT NOT NULL,
                    proposed TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(
                        status IN ('pending','approved','rejected','superseded')
                    ),
                    revision INTEGER NOT NULL CHECK(revision > 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    reviewer TEXT,
                    correction TEXT,
                    decision_notes TEXT,
                    approved_at TEXT
                )
            """)
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS review_queue_status_created
                ON review_queue_items(status, created_at, item_id)
            """)
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS review_queue_source_target_original
                ON review_queue_items(source, target, original, status)
            """)
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS review_queue_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL REFERENCES review_queue_items(item_id),
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS review_queue_events_item
                ON review_queue_events(item_id, event_id)
            """)

    @contextmanager
    def _transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _actor(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("REVIEW_ACTOR_REQUIRED")
        return value.strip()

    @staticmethod
    def _row_to_item(row: sqlite3.Row | None) -> ReviewItem | None:
        if row is None:
            return None
        return ReviewItem(
            item_id=row["item_id"],
            source=row["source"],
            target=row["target"],
            original=row["original"],
            proposed=row["proposed"],
            reason=row["reason"],
            context=json.loads(row["context_json"]),
            status=row["status"],
            revision=row["revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            reviewer=row["reviewer"],
            correction=row["correction"],
            decision_notes=row["decision_notes"],
            approved_at=row["approved_at"],
        )

    def _event(
        self,
        *,
        item_id: str,
        event_type: str,
        actor: str,
        from_status: str | None,
        to_status: str | None,
        revision: int,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        self.connection.execute("""
            INSERT INTO review_queue_events(
                item_id,event_type,actor,from_status,to_status,
                revision,payload_json,created_at
            ) VALUES(?,?,?,?,?,?,?,?)
        """, (
            item_id, event_type, actor, from_status, to_status, revision,
            json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True),
            self._now(),
        ))

    @staticmethod
    def _make_id(source: str, target: str, original: str, proposed: str) -> str:
        identity = json.dumps(
            [source, target, original, proposed],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def enqueue(
        self,
        source: str,
        target: str,
        original: str,
        proposed: str,
        *,
        reason: str,
        context: Mapping[str, Any] | None = None,
        actor: str = "system",
    ) -> ReviewItem:
        if source not in {"ja", "en"}:
            raise ValueError("REVIEW_SOURCE_MUST_BE_JA_OR_EN")
        if not isinstance(target, str) or not target.strip() or target == source:
            raise ValueError("REVIEW_TARGET_REQUIRED")
        if not isinstance(original, str) or not original.strip():
            raise ValueError("REVIEW_ORIGINAL_REQUIRED")
        if not isinstance(proposed, str):
            raise TypeError("REVIEW_PROPOSED_MUST_BE_TEXT")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("REVIEW_REASON_REQUIRED")
        if context is not None and not isinstance(context, Mapping):
            raise TypeError("REVIEW_CONTEXT_MUST_BE_A_MAPPING")
        actor = self._actor(actor)
        context_json = json.dumps(
            dict(context or {}), ensure_ascii=False, sort_keys=True
        )
        item_id = self._make_id(source, target, original, proposed)
        now = self._now()
        with self._transaction():
            cursor = self.connection.execute("""
                INSERT OR IGNORE INTO review_queue_items(
                    item_id,source,target,original,proposed,reason,context_json,
                    status,revision,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,'pending',1,?,?)
            """, (
                item_id, source, target, original, proposed, reason.strip(),
                context_json, now, now,
            ))
            if cursor.rowcount == 1:
                self._event(
                    item_id=item_id,
                    event_type="queued",
                    actor=actor,
                    from_status=None,
                    to_status="pending",
                    revision=1,
                    payload={"reason": reason.strip()},
                )
        item = self.get(item_id)
        if item is None:
            raise ReviewQueueError("REVIEW_ENQUEUE_PERSISTENCE_FAILED")
        return item

    def get(self, item_id: str) -> ReviewItem | None:
        row = self.connection.execute(
            "SELECT * FROM review_queue_items WHERE item_id=?",
            (item_id,),
        ).fetchone()
        return self._row_to_item(row)

    def list_items(
        self,
        *,
        status: str | None = "pending",
        limit: int = 100,
    ) -> list[ReviewItem]:
        if status is not None and status not in STATUSES:
            raise ValueError("UNKNOWN_REVIEW_STATUS")
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise ValueError("REVIEW_LIMIT_OUT_OF_RANGE")
        if status is None:
            rows = self.connection.execute("""
                SELECT * FROM review_queue_items
                ORDER BY created_at, item_id LIMIT ?
            """, (limit,)).fetchall()
        else:
            rows = self.connection.execute("""
                SELECT * FROM review_queue_items WHERE status=?
                ORDER BY created_at, item_id LIMIT ?
            """, (status, limit)).fetchall()
        return [self._row_to_item(row) for row in rows]

    def count(self, status: str | None = None) -> int:
        if status is not None and status not in STATUSES:
            raise ValueError("UNKNOWN_REVIEW_STATUS")
        if status is None:
            row = self.connection.execute(
                "SELECT COUNT(*) FROM review_queue_items"
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT COUNT(*) FROM review_queue_items WHERE status=?",
                (status,),
            ).fetchone()
        return int(row[0])

    def events(self, item_id: str) -> list[dict[str, Any]]:
        if self.get(item_id) is None:
            raise ReviewNotFound("REVIEW_ITEM_NOT_FOUND:" + item_id)
        rows = self.connection.execute("""
            SELECT event_id,item_id,event_type,actor,from_status,to_status,
                   revision,payload_json,created_at
            FROM review_queue_events
            WHERE item_id=? ORDER BY event_id
        """, (item_id,)).fetchall()
        return [{
            "event_id": row["event_id"],
            "item_id": row["item_id"],
            "event_type": row["event_type"],
            "actor": row["actor"],
            "from_status": row["from_status"],
            "to_status": row["to_status"],
            "revision": row["revision"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        } for row in rows]

    def _record_validation_failure(
        self,
        item_id: str,
        expected_revision: int,
        actor: str,
        error: Exception,
    ) -> None:
        with self._transaction():
            row = self.connection.execute("""
                SELECT status,revision FROM review_queue_items WHERE item_id=?
            """, (item_id,)).fetchone()
            if row is None:
                raise ReviewNotFound("REVIEW_ITEM_NOT_FOUND:" + item_id)
            if row["revision"] != expected_revision:
                raise ReviewConflict("REVIEW_REVISION_CHANGED")
            if row["status"] != "pending":
                raise InvalidReviewState("REVIEW_ITEM_NOT_PENDING")
            self._event(
                item_id=item_id,
                event_type="approval_validation_failed",
                actor=actor,
                from_status="pending",
                to_status="pending",
                revision=expected_revision,
                payload={
                    "error_type": type(error).__name__,
                    "error": str(error)[:1200],
                },
            )

    def approve(
        self,
        item_id: str,
        correction: str,
        *,
        actor: str,
        expected_revision: int,
        human_verified: bool = False,
        notes: str,
        required_terms: tuple[str, ...] = (),
        quality_validator: Callable[[str], None] | None = None,
        replace_existing: bool = False,
    ) -> ReviewItem:
        actor = self._actor(actor)
        if human_verified is not True:
            raise ValueError("EXPLICIT_HUMAN_SEMANTIC_VERIFICATION_REQUIRED")
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError("REVIEW_DECISION_NOTES_REQUIRED")
        if not isinstance(expected_revision, int) or expected_revision < 1:
            raise ValueError("EXPECTED_REVIEW_REVISION_REQUIRED")
        if not isinstance(correction, str) or not correction.strip():
            raise ValueError("NON_EMPTY_REVIEW_CORRECTION_REQUIRED")
        item = self.get(item_id)
        if item is None:
            raise ReviewNotFound("REVIEW_ITEM_NOT_FOUND:" + item_id)
        if item.status != "pending":
            raise InvalidReviewState("REVIEW_ITEM_NOT_PENDING")
        if item.revision != expected_revision:
            raise ReviewConflict("REVIEW_REVISION_CHANGED")

        try:
            validate_translation(
                item.original,
                correction,
                source=item.source,
                required_terms=required_terms,
            )
            if quality_validator is not None:
                quality_validator(correction)
        except Exception as exc:
            self._record_validation_failure(
                item_id, expected_revision, actor, exc
            )
            raise

        now = self._now()
        correction_hash = hashlib.sha256(
            correction.encode("utf-8")
        ).hexdigest()
        conflict_message: str | None = None
        with self._transaction():
            current = self.connection.execute("""
                SELECT * FROM review_queue_items WHERE item_id=?
            """, (item_id,)).fetchone()
            if current is None:
                raise ReviewNotFound("REVIEW_ITEM_NOT_FOUND:" + item_id)
            if current["revision"] != expected_revision:
                raise ReviewConflict("REVIEW_REVISION_CHANGED")
            if current["status"] != "pending":
                raise InvalidReviewState("REVIEW_ITEM_NOT_PENDING")

            existing = self.connection.execute("""
                SELECT translated FROM translations
                WHERE source=? AND target=? AND original=?
            """, (item.source, item.target, item.original)).fetchone()
            if existing is not None and existing["translated"] != correction:
                if not replace_existing:
                    conflict_message = "ACCEPTED_TRANSLATION_EXISTS_REPLACE_FLAG_REQUIRED"
                    self._event(
                        item_id=item_id,
                        event_type="approval_conflict_existing_translation",
                        actor=actor,
                        from_status="pending",
                        to_status="pending",
                        revision=expected_revision,
                        payload={
                            "existing_sha256": hashlib.sha256(
                                existing["translated"].encode("utf-8")
                            ).hexdigest(),
                            "correction_sha256": correction_hash,
                        },
                    )
            if conflict_message is None:
                self.connection.execute("""
                    INSERT INTO translations(source,target,original,translated)
                    VALUES(?,?,?,?)
                    ON CONFLICT(source,target,original)
                    DO UPDATE SET translated=excluded.translated
                """, (item.source, item.target, item.original, correction))
                self.connection.execute("""
                    UPDATE review_queue_items
                    SET status='approved',reviewer=?,correction=?,decision_notes=?,
                        approved_at=?,updated_at=?,revision=revision+1
                    WHERE item_id=?
                """, (
                    actor, correction, notes.strip(), now, now, item_id,
                ))
                self._event(
                    item_id=item_id,
                    event_type="approved",
                    actor=actor,
                    from_status="pending",
                    to_status="approved",
                    revision=expected_revision + 1,
                    payload={
                        "human_verified": True,
                        "quality_validator_used": quality_validator is not None,
                        "required_terms": list(required_terms),
                        "correction": correction,
                        "correction_sha256": correction_hash,
                        "notes": notes.strip(),
                        "replace_existing": replace_existing,
                    },
                )
                other_rows = self.connection.execute("""
                    SELECT item_id,revision FROM review_queue_items
                    WHERE source=? AND target=? AND original=?
                      AND item_id<>? AND status='pending'
                """, (item.source, item.target, item.original, item_id)).fetchall()
                for other in other_rows:
                    self.connection.execute("""
                        UPDATE review_queue_items
                        SET status='superseded',updated_at=?,revision=revision+1
                        WHERE item_id=?
                    """, (now, other["item_id"]))
                    self._event(
                        item_id=other["item_id"],
                        event_type="superseded_by_approved_correction",
                        actor=actor,
                        from_status="pending",
                        to_status="superseded",
                        revision=other["revision"] + 1,
                        payload={"approved_item_id": item_id},
                    )
        if conflict_message is not None:
            raise ReviewConflict(conflict_message)
        approved = self.get(item_id)
        if approved is None:
            raise ReviewQueueError("REVIEW_APPROVAL_PERSISTENCE_FAILED")
        return approved

    def reject(
        self,
        item_id: str,
        *,
        actor: str,
        expected_revision: int,
        reason: str,
    ) -> ReviewItem:
        actor = self._actor(actor)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("REJECTION_REASON_REQUIRED")
        with self._transaction():
            row = self.connection.execute("""
                SELECT status,revision FROM review_queue_items WHERE item_id=?
            """, (item_id,)).fetchone()
            if row is None:
                raise ReviewNotFound("REVIEW_ITEM_NOT_FOUND:" + item_id)
            if row["revision"] != expected_revision:
                raise ReviewConflict("REVIEW_REVISION_CHANGED")
            if row["status"] != "pending":
                raise InvalidReviewState("REVIEW_ITEM_NOT_PENDING")
            now = self._now()
            self.connection.execute("""
                UPDATE review_queue_items
                SET status='rejected',reviewer=?,decision_notes=?,
                    updated_at=?,revision=revision+1
                WHERE item_id=?
            """, (actor, reason.strip(), now, item_id))
            self._event(
                item_id=item_id,
                event_type="rejected",
                actor=actor,
                from_status="pending",
                to_status="rejected",
                revision=expected_revision + 1,
                payload={"reason": reason.strip()},
            )
        item = self.get(item_id)
        if item is None:
            raise ReviewQueueError("REVIEW_REJECTION_PERSISTENCE_FAILED")
        return item

    def revise(
        self,
        item_id: str,
        proposed: str,
        *,
        actor: str,
        expected_revision: int,
        reason: str,
    ) -> ReviewItem:
        actor = self._actor(actor)
        if not isinstance(proposed, str):
            raise TypeError("REVIEW_PROPOSED_MUST_BE_TEXT")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("REVISION_REASON_REQUIRED")
        with self._transaction():
            row = self.connection.execute("""
                SELECT status,revision,proposed FROM review_queue_items
                WHERE item_id=?
            """, (item_id,)).fetchone()
            if row is None:
                raise ReviewNotFound("REVIEW_ITEM_NOT_FOUND:" + item_id)
            if row["revision"] != expected_revision:
                raise ReviewConflict("REVIEW_REVISION_CHANGED")
            if row["status"] not in {"rejected", "superseded"}:
                raise InvalidReviewState("ONLY_REJECTED_OR_SUPERSEDED_ITEMS_CAN_REOPEN")
            old_status = row["status"]
            old_proposed_hash = hashlib.sha256(
                row["proposed"].encode("utf-8")
            ).hexdigest()
            now = self._now()
            self.connection.execute("""
                UPDATE review_queue_items
                SET proposed=?,reason=?,status='pending',
                    reviewer=NULL,correction=NULL,decision_notes=NULL,
                    approved_at=NULL,updated_at=?,revision=revision+1
                WHERE item_id=?
            """, (proposed, reason.strip(), now, item_id))
            self._event(
                item_id=item_id,
                event_type="reopened_with_revision",
                actor=actor,
                from_status=old_status,
                to_status="pending",
                revision=expected_revision + 1,
                payload={
                    "previous_proposed_sha256": old_proposed_hash,
                    "new_proposed": proposed,
                    "reason": reason.strip(),
                },
            )
        item = self.get(item_id)
        if item is None:
            raise ReviewQueueError("REVIEW_REVISION_PERSISTENCE_FAILED")
        return item

    def snapshot(self) -> dict[str, Any]:
        items = self.list_items(status=None, limit=1000)
        event_rows = self.connection.execute("""
            SELECT event_id,item_id,event_type,actor,from_status,to_status,
                   revision,payload_json,created_at
            FROM review_queue_events ORDER BY event_id
        """).fetchall()
        return {
            "schema": "translation-human-review-queue-v1",
            "database": self.path.name,
            "items": [asdict(item) for item in items],
            "events": [{
                "event_id": row["event_id"],
                "item_id": row["item_id"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "from_status": row["from_status"],
                "to_status": row["to_status"],
                "revision": row["revision"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            } for row in event_rows],
        }

    def export_snapshot(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
        return destination

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ReviewQueue":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="List review queue items")
    list_parser.add_argument("--workspace", required=True, type=Path)
    list_parser.add_argument("--status", choices=STATUSES + ("all",), default="pending")
    list_parser.add_argument("--limit", type=int, default=100)

    show_parser = commands.add_parser("show", help="Show an item and its audit events")
    show_parser.add_argument("--workspace", required=True, type=Path)
    show_parser.add_argument("--id", required=True)

    enqueue_parser = commands.add_parser("enqueue", help="Add a rejected candidate")
    enqueue_parser.add_argument("--workspace", required=True, type=Path)
    enqueue_parser.add_argument("--source", required=True)
    enqueue_parser.add_argument("--target", required=True)
    enqueue_parser.add_argument("--original", required=True)
    enqueue_parser.add_argument("--proposed", default="")
    enqueue_parser.add_argument("--reason", required=True)
    enqueue_parser.add_argument("--actor", default="operator")

    approve_parser = commands.add_parser("approve", help="Approve a human-corrected translation")
    approve_parser.add_argument("--workspace", required=True, type=Path)
    approve_parser.add_argument("--id", required=True)
    approve_parser.add_argument("--expected-revision", required=True, type=int)
    approve_parser.add_argument("--reviewer", required=True)
    approve_parser.add_argument("--correction", required=True)
    approve_parser.add_argument("--notes", required=True)
    approve_parser.add_argument("--human-verified", action="store_true", required=True)
    approve_parser.add_argument("--replace-existing", action="store_true")

    reject_parser = commands.add_parser("reject", help="Reject a candidate")
    reject_parser.add_argument("--workspace", required=True, type=Path)
    reject_parser.add_argument("--id", required=True)
    reject_parser.add_argument("--expected-revision", required=True, type=int)
    reject_parser.add_argument("--reviewer", required=True)
    reject_parser.add_argument("--reason", required=True)

    revise_parser = commands.add_parser("revise", help="Reopen a rejected item with a new proposal")
    revise_parser.add_argument("--workspace", required=True, type=Path)
    revise_parser.add_argument("--id", required=True)
    revise_parser.add_argument("--expected-revision", required=True, type=int)
    revise_parser.add_argument("--reviewer", required=True)
    revise_parser.add_argument("--proposed", required=True)
    revise_parser.add_argument("--reason", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        with ReviewQueue(args.workspace) as queue:
            if args.command == "list":
                status = None if args.status == "all" else args.status
                _emit([asdict(item) for item in queue.list_items(
                    status=status, limit=args.limit
                )])
            elif args.command == "show":
                item = queue.get(args.id)
                if item is None:
                    raise ReviewNotFound("REVIEW_ITEM_NOT_FOUND:" + args.id)
                _emit({"item": asdict(item), "events": queue.events(args.id)})
            elif args.command == "enqueue":
                item = queue.enqueue(
                    args.source, args.target, args.original, args.proposed,
                    reason=args.reason, actor=args.actor,
                )
                _emit(asdict(item))
            elif args.command == "approve":
                item = queue.approve(
                    args.id, args.correction,
                    actor=args.reviewer,
                    expected_revision=args.expected_revision,
                    human_verified=args.human_verified,
                    notes=args.notes,
                    replace_existing=args.replace_existing,
                )
                _emit(asdict(item))
            elif args.command == "reject":
                item = queue.reject(
                    args.id, actor=args.reviewer,
                    expected_revision=args.expected_revision,
                    reason=args.reason,
                )
                _emit(asdict(item))
            elif args.command == "revise":
                item = queue.revise(
                    args.id, args.proposed,
                    actor=args.reviewer,
                    expected_revision=args.expected_revision,
                    reason=args.reason,
                )
                _emit(asdict(item))
        return 0
    except (ReviewQueueError, TranslationRejected, ValueError, TypeError) as exc:
        print(type(exc).__name__ + ":" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
