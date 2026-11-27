"""Regression for the XP real-OPUS acceptance harness, no model files."""
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

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

    def test_worker_shutdown_always_precedes_fixture_cleanup(self):
        engine=Path("synthetic-engine")
        root=Path("synthetic-root")
        good=SimpleNamespace(returncode=0,stdout=(
            b'IA_RPGXP_EXPANDED_RESULT "Escuchame, poderoso rey!"\n'
            b'IA_RPGXP_REAL_OPUS_INSTALLED_NATIVE_CONTRACT_PASS\n'),stderr=b"")
        bad=SimpleNamespace(returncode=1,stdout=b"",stderr=b"semantic test failure")
        for result,error in ((good,None),(bad,AssertionError),
            (subprocess.TimeoutExpired("ruby",160),subprocess.TimeoutExpired)):
            events=[]
            def execute(*args,**kwargs):
                events.append("ruby")
                if isinstance(result,Exception):raise result
                return result
            def closed(path):
                self.assertEqual(path,engine)
                events.append("worker closed")
            with patch.object(probe.subprocess,"run",side_effect=execute), \
                 patch.object(probe,"wait_closed",side_effect=closed):
                if error is None:
                    self.assertEqual(probe.run_native_probe(root,engine),"Escuchame, poderoso rey!")
                else:
                    with self.assertRaises(error):
                        probe.run_native_probe(root,engine)
            self.assertEqual(events,["ruby","worker closed"])

    def test_expanded_reader_checks_exact_key_without_leaking_handles(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"probe.sqlite3"
            with closing(sqlite3.connect(str(path))) as conn:
                conn.execute("CREATE TABLE translations (source TEXT, original TEXT, translated TEXT)")
                conn.execute("INSERT INTO translations VALUES (?,?,?)",
                             ("en",probe.EXPANDED_SOURCE,"Escúchame, poderoso rey!"))
                conn.execute("INSERT INTO translations VALUES (?,?,?)",
                             ("en","Other phrase","Otra frase"))
                conn.commit()
            self.assertEqual(probe.read_expanded_translation(path),"Escúchame, poderoso rey!")
            path.unlink()

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"missing.sqlite3"
            with self.assertRaises(FileNotFoundError):
                probe.read_translation_count(path)
            self.assertFalse(path.exists())


if __name__=="__main__":
    unittest.main()
