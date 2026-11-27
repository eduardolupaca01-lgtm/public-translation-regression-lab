"""Regression for the XP real-OPUS acceptance harness, no model files."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import probe_rpgxp_real as probe


class RPGXPAcceptanceCleanupTests(unittest.TestCase):
    def test_reader_releases_database_even_if_query_fails(self):
        # Retain the actual connection objects: relying on garbage collection
        # would hide the original Windows sharing violation.
        opened=[]
        connect=sqlite3.connect

        def tracked_connect(*args, **kwargs):
            connection=connect(*args, **kwargs)
            opened.append(connection)
            return connection

        with tempfile.TemporaryDirectory(prefix="ia-xp-cleanup-") as tmp:
            root=Path(tmp)
            for has_table in (True,False):
                path=root/("prueba # memoria %d.sqlite3"%has_table)
                with closing(connect(str(path))) as conn:
                    if has_table:
                        conn.execute("CREATE TABLE translations (id INTEGER)")
                        conn.executemany("INSERT INTO translations VALUES (?)",[(1,),(2,),(3,)])
                        conn.commit()
                    else:
                        conn.execute("CREATE TABLE other (id INTEGER)")
                        conn.commit()
                with patch.object(probe.sqlite3,"connect",side_effect=tracked_connect) as spy:
                    if has_table:
                        self.assertEqual(probe.read_translation_count(path),3)
                    else:
                        with self.assertRaises(sqlite3.OperationalError):
                            probe.read_translation_count(path)
                    self.assertTrue(spy.call_args.kwargs["uri"])
                    self.assertTrue(spy.call_args.args[0].endswith("?mode=ro"))
                with self.assertRaises(sqlite3.ProgrammingError):
                    opened[-1].execute("SELECT 1")
                # Windows refuses deletion when a connection still holds
                # the file. Require normal cleanup, not ignore_errors.
                path.unlink()
                self.assertFalse(path.exists())
        self.assertEqual(len(opened),2)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"missing.sqlite3"
            with self.assertRaises(FileNotFoundError):
                probe.read_translation_count(path)
            self.assertFalse(path.exists())


if __name__=="__main__":
    unittest.main()
