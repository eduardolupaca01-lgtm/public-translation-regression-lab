"""Regression coverage for sanitized PyInstaller build-warning reporting."""
import unittest
from audit_pyinstaller_warnings import summarize


class WarningAuditTests(unittest.TestCase):
    def test_import_kinds_and_context(self):
        counts, rows, unparsed = summarize(
            "missing module named posix - imported by os (conditional), pathlib (optional)\n"
            "missing module named 'org.python' - imported by copy (optional)\n"
            "excluded module named tkinter - imported by sample (top-level)\n"
            "invalid module named example - imported by another (delayed, conditional)\n"
        )
        self.assertEqual(dict(counts), {"missing": 2, "excluded": 1, "invalid": 1})
        self.assertEqual(unparsed, 0)
        self.assertIn(("missing", "posix", "conditional,optional",
                       "os(conditional);pathlib(optional)"), rows)
        self.assertIn(("invalid", "example", "conditional,delayed",
                       "another(conditional,delayed)"), rows)

    def test_unknown_lines_are_not_emitted_as_paths(self):
        counts, rows, unparsed = summarize(
            "missing module named C:\\private\\module - imported by app (top-level)\n"
            "missing module named safe - imported by C:\\private\\source.py (optional)\n"
            "some raw diagnostic C:\\private\\source.py\n"
        )
        self.assertEqual(dict(counts), {"missing": 1})
        self.assertEqual(rows, [("missing", "safe", "unclassified", "unclassified")])
        self.assertEqual(unparsed, 1)


if __name__ == "__main__":
    unittest.main()
