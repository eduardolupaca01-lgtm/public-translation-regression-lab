"""Regression for the exact Windows cache-handle leak in R31 acceptance."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock
import test_vxace_real_worker as acceptance

class CacheReleaseTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="vxace cache close ")
        self.addCleanup(tmp.cleanup)
        self.cache=Path(tmp.name)/"translation-memory-v2.sqlite3"
        with closing(sqlite3.connect(self.cache)) as db:
            db.execute("CREATE TABLE translations(key_sha256 TEXT,created_unix INTEGER)")
            db.execute("INSERT INTO translations VALUES ('key',123)")
            db.commit()

    def assert_inspection_closed(self,fail_query=False):
        real_connect=sqlite3.connect
        opened=[]
        def tracked(*args,**kwargs):
            db=real_connect(*args,**kwargs)
            opened.append(db)  # Retain it: GC cannot mask a missing close().
            return db
        try:
            with mock.patch.object(acceptance.sqlite3,"connect",side_effect=tracked):
                if fail_query:
                    with self.assertRaises(sqlite3.OperationalError):
                        acceptance.cache_rows(self.cache)
                else:
                    self.assertEqual(acceptance.cache_rows(self.cache),{"key":123})
            self.assertEqual(len(opened),1)
            with self.assertRaises(sqlite3.ProgrammingError):
                opened[0].execute("SELECT 1")
            acceptance.assert_cache_released(self.cache)
        finally:
            for db in opened:
                db.close()

    def test_reader_closes_on_success(self):
        self.assert_inspection_closed()

    def test_reader_closes_on_query_error(self):
        with closing(sqlite3.connect(self.cache)) as db:
            db.execute("DROP TABLE translations")
            db.commit()
        self.assert_inspection_closed(fail_query=True)

    @unittest.skipUnless(os.name=="nt","Win32 sharing semantics")
    def test_exclusive_probe_detects_open_sqlite_handle(self):
        with closing(sqlite3.connect(self.cache)) as db:
            db.execute("SELECT * FROM translations").fetchall()
            with self.assertRaisesRegex(AssertionError,"IA_VXACE_CACHE_HANDLE_OPEN_WINERROR_"):
                acceptance.assert_cache_released(self.cache)
        acceptance.assert_cache_released(self.cache)

    def test_missing_cache_is_not_created(self):
        missing=self.cache.with_name("missing.sqlite3")
        with self.assertRaisesRegex(AssertionError,"IA_VXACE_CACHE_MISSING"):
            acceptance.cache_rows(missing)
        self.assertFalse(missing.exists())

if __name__=="__main__":unittest.main()
