"""Minimal durable SQLite cache for public, offline acceptance checks."""
from __future__ import annotations
from pathlib import Path
import sqlite3
from collections.abc import Callable

from .pipeline import validate_translation, TranslationRejected


class DurableTranslationCache:
    """Persistent translation store: never write rejected or empty translations."""

    def __init__(self, directory: str | Path):
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "translation-cache.sqlite3"
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

    def get(self, source: str, target: str, original: str, *,
            required_terms: tuple[str, ...] = ()) -> str | None:
        row = self.connection.execute("""
            SELECT translated FROM translations
             WHERE source=? AND target=? AND original=?
        """, (source, target, original)).fetchone()
        if row is None:
            return None
        value = row[0]
        try:
            validate_translation(original, value, source=source, required_terms=required_terms)
        except TranslationRejected:
            return None
        return value

    def put(self, source: str, target: str, original: str, translated: str, *,
            required_terms: tuple[str, ...] = ()) -> None:
        validate_translation(original, translated, source=source, required_terms=required_terms)
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
    ) -> str:
        cached = self.get(source, target, original, required_terms=required_terms)
        if cached is not None:
            return cached
        result = translator(original)
        self.put(source, target, original, result, required_terms=required_terms)
        return result

    def count(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM translations").fetchone()[0]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
