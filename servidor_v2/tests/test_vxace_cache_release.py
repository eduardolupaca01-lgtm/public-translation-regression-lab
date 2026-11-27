"""Regression for the exact Windows cache-handle leak in R31 acceptance."""
import json
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

    def test_bootloader_receipt_requires_matching_parent_and_integer_pid(self):
        receipt=self.cache.with_name("process.json")
        def write(parent,pid):
            receipt.write_text(json.dumps({"schema":"ia-vxace-process-v1",
                                           "game_pid":parent,"bootloader_pid":pid}),encoding="ascii")
        write(101,202)
        self.assertEqual(acceptance.bootloader_pid(receipt,101),202)
        self.assertIsNone(acceptance.bootloader_pid(receipt,102))
        for pid in (0,-1,True,"202",2**32):
            write(101,pid)
            self.assertIsNone(acceptance.bootloader_pid(receipt,101))
        receipt.write_text("x"*1025,encoding="ascii")
        self.assertIsNone(acceptance.bootloader_pid(receipt,101))

    def test_exit_wait_checks_result_not_only_process_signal(self):
        kernel=mock.Mock()
        kernel.WaitForSingleObject.return_value=0
        def result(handle,ptr):
            ptr._obj.value=0
            return 1
        kernel.GetExitCodeProcess.side_effect=result
        acceptance.wait_clean_exit(kernel,17,"WORKER")
        acceptance.wait_clean_exit(kernel,18,"BOOTLOADER")
        self.assertEqual(kernel.WaitForSingleObject.call_args_list,
                         [mock.call(17,35000),mock.call(18,35000)])
        kernel.WaitForSingleObject.return_value=258
        with self.assertRaisesRegex(AssertionError,"BOOTLOADER_DID_NOT_EXIT"):
            acceptance.wait_clean_exit(kernel,18,"BOOTLOADER")
        kernel.WaitForSingleObject.return_value=0
        def error(handle,ptr):
            ptr._obj.value=7
            return 1
        kernel.GetExitCodeProcess.side_effect=error
        with self.assertRaisesRegex(AssertionError,"BOOTLOADER_EXIT_7"):
            acceptance.wait_clean_exit(kernel,18,"BOOTLOADER")

    def test_missing_cache_is_not_created(self):
        missing=self.cache.with_name("missing.sqlite3")
        with self.assertRaisesRegex(AssertionError,"IA_VXACE_CACHE_MISSING"):
            acceptance.cache_rows(missing)
        self.assertFalse(missing.exists())

if __name__=="__main__":unittest.main()
