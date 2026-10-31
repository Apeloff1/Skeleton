"""Fail-closed regression tests for exhaustive canonical domain-suite sharding."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.run_domain_suite_shard import EXCLUDED, discover, partition


class CanonicalDomainShards(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for i, size in enumerate((30, 70, 12, 40, 20, 25, 50, 18)):
            (self.root / f"test_case_{i}.py").write_text("x" * size, encoding="utf-8")
        (self.root / EXCLUDED).write_text("excluded advisory", encoding="utf-8")
        (self.root / "custom_test.py").write_text("def test_not_collected(): pass", encoding="utf-8")

    def test_exhaustive_disjoint_and_stable(self) -> None:
        original = discover(self.root)
        first = partition(self.root, 4)
        self.assertEqual(first, partition(self.root, 4))
        flattened = [path for shard in first for path in shard]
        self.assertEqual(len(flattened), len(original))
        self.assertEqual(set(flattened), set(original))
        self.assertEqual(len(set(flattened)), len(flattened))
        self.assertTrue(all(shard for shard in first))
        self.assertNotIn(self.root / EXCLUDED, flattened)
        self.assertNotIn(self.root / "custom_test.py", flattened)

    def test_invalid_or_empty_inventory_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            partition(self.root, 0)
        with self.assertRaises(ValueError):
            partition(self.root, 100)
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(ValueError):
                discover(Path(empty))

    def test_pytest_file_pattern_is_respected(self) -> None:
        self.assertTrue(all(p.name.startswith("test_") for p in discover(self.root)))

    def test_linked_test_module_fails_closed(self) -> None:
        (self.root / "test_link.py").symlink_to(self.root / "test_case_0.py")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            discover(self.root)

    def test_nested_test_files_are_not_dropped(self) -> None:
        nested = self.root / "nested"
        nested.mkdir()
        target = nested / "test_nested.py"
        target.write_text("def test_nested(): pass", encoding="utf-8")
        self.assertIn(target, discover(self.root))
        self.assertIn(target, [p for shard in partition(self.root, 4) for p in shard])


if __name__ == "__main__":
    unittest.main()
