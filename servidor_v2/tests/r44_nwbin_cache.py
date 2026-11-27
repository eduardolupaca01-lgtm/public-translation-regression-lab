"""Verify only authored R44 fixture rows; never write to a game cache."""
import json
import sqlite3
import sys
import unicodedata
from contextlib import closing
from pathlib import Path

def normalize(value):
    return unicodedata.normalize("NFC", value).strip()

def verify(database, result_file):
    result=json.loads(result_file.read_text(encoding="utf-8"))
    assert result["ok"] is True
    uri=database.resolve(strict=True).as_uri()+"?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        for lang, source, shown in (
            ("en", "Please close the wooden door.", result["en"]),
            ("ja", "橋を渡ってください。", result["ja"]),
        ):
            with closing(conn.execute(
                "SELECT translated FROM translations WHERE source=? AND original=?",
                (lang, source),
            )) as cursor:
                rows=cursor.fetchall()
                assert len(rows)==1, "IA_R44_CACHE_KEY_MISSING_OR_DUPLICATED"
                assert normalize(rows[0][0])==normalize(shown), "IA_R44_CACHE_PAINT_MISMATCH"
    print("IA_R44_SQLITE_NATIVE_PAINT_VERIFIED")

if __name__=="__main__":
    verify(Path(sys.argv[1]),Path(sys.argv[2]))
