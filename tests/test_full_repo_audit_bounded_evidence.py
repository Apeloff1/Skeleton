"""Bounded full-tree audit evidence regression, without running repository suites."""
from pathlib import Path
import tempfile
import unittest

from scripts.audit_sweep_20261106 import bounded_source_bytes
from scripts.audit_pytest_shard_20261106 import bounded_log_tail


class AuditEvidenceBoundsTests(unittest.TestCase):
    def test_small_source_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "small.py"
            path.write_bytes(b"print('ok')\n")
            self.assertEqual(bounded_source_bytes(path, limit=32), b"print('ok')\n")

    def test_oversized_source_fails_before_unbounded_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "large.py"
            path.write_bytes(b"c" * 2048)
            with self.assertRaisesRegex(ValueError, "byte bound"):
                bounded_source_bytes(path, limit=64)

    def test_bounded_tail_excludes_large_prefix_and_partial_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "large.log"
            path.write_bytes(b"X" * 256 + b"\nGOOD\nEND\n")
            self.assertEqual(bounded_log_tail(path, max_bytes=16, max_lines=2), "GOOD\nEND")

    def test_invalid_bounds_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "log"
            path.write_text("ok")
            with self.assertRaises(ValueError):
                bounded_log_tail(path, max_bytes=0)
            with self.assertRaises(ValueError):
                bounded_source_bytes(path, limit=-1)


if __name__ == "__main__":
    unittest.main()
