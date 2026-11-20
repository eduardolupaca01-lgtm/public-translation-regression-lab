"""Minimal durable SQLite cache for public, offline acceptance checks."""
from __future__ import annotations
from pathlib import Path
import sqlite3
import errno
import hashlib
import os
import time
from contextlib import contextmanager
from collections.abc import Callable

from .pipeline import validate_translation, TranslationRejected


class DurableTranslationCache:
    """Persistent translation store: never write rejected or empty translations."""

    def __init__(self, directory: str | Path):
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "translation-cache.sqlite3"
        # Bounded 256-stripe cross-process advisory locks. Unlike a SQLite
        # write transaction around inference, unrelated keys can translate
        # concurrently, while identical requests share exactly one producer.
        self._guard_directory = folder / ".singleflight-locks"
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.execute("PRAGMA busy_timeout=30000")
        self.connection.execute("PRAGMA journal_mode=DELETE")
        self.connection.execute("PRAGMA synchronous=FULL")
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


    @contextmanager
    def _singleflight(self, source: str, target: str, original: str):
        """Coordinate same-key misses between unrelated OS processes.

        Lock files are deliberately bounded to 256 stripes and contain no
        user text. Kernel advisory locks release when a worker crashes.
        They protect translate_or_get callers; direct put remains a deliberate
        administrative overwrite and is not an inference single-flight call.
        """
        digest = hashlib.sha256(
            repr((source, target, original)).encode("utf-8")
        ).digest()
        self._guard_directory.mkdir(parents=True, exist_ok=True)
        lock_path = self._guard_directory / f"stripe-{digest[0]:02x}.lock"
        deadline = time.monotonic() + 60.0
        with lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                # A one-byte region is required by Windows msvcrt.locking.
                handle.write(b"\x00")
                handle.flush()
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(
                            handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                        )
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError("CACHE_SINGLEFLIGHT_LOCK_TIMEOUT") from exc
                    time.sleep(0.025)
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def get(self, source: str, target: str, original: str, *,
            required_terms: tuple[str, ...] = (),
            quality_validator: Callable[[str], None] | None = None) -> str | None:
        row = self.connection.execute("""
            SELECT translated FROM translations
             WHERE source=? AND target=? AND original=?
        """, (source, target, original)).fetchone()
        if row is None:
            return None
        value = row[0]
        try:
            validate_translation(original, value, source=source, required_terms=required_terms)
            if quality_validator is not None:
                quality_validator(value)
        except TranslationRejected:
            return None
        return value

    def put(self, source: str, target: str, original: str, translated: str, *,
            required_terms: tuple[str, ...] = (),
            quality_validator: Callable[[str], None] | None = None) -> None:
        validate_translation(original, translated, source=source, required_terms=required_terms)
        if quality_validator is not None:
            quality_validator(translated)
        with self.connection:
            self.connection.execute("""
                INSERT INTO translations(source,target,original,translated)
                VALUES(?,?,?,?)
                ON CONFLICT(source,target,original)
                DO UPDATE SET translated=excluded.translated
            """, (source, target, original, translated))

    def translate_or_get(
        self,
        source: str, target: str, original: str,
        translator: Callable[[str], str],
        *, required_terms: tuple[str, ...] = (),
        quality_validator: Callable[[str], None] | None = None,
    ) -> str:
        cached = self.get(
            source, target, original, required_terms=required_terms,
            quality_validator=quality_validator,
        )
        if cached is not None:
            return cached
        with self._singleflight(source, target, original):
            # A different process may have finished while this worker waited.
            cached = self.get(
                source, target, original, required_terms=required_terms,
                quality_validator=quality_validator,
            )
            if cached is not None:
                return cached
            result = translator(original)
            self.put(
                source, target, original, result,
                required_terms=required_terms,
                quality_validator=quality_validator,
            )
            return result

    def count(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM translations").fetchone()[0]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
