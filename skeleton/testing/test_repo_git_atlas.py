"""Focused contract tests for the complete Git-backed repository atlas."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from skeleton.repo_machine.git_atlas import AtlasError, inventory, write_artifacts


CONFIG = """
[repository]
schema_version = 1
name = "fixture"
default_owner = "repository-control-plane"
max_files = 100
max_file_bytes = 100000
max_context_bytes = 30000

[policy]
require_tests_for_code = false
require_readme_for_top_level_code = false
detect_dependency_cycles = false
detect_oversized_modules = false

[ignore]
prefixes = []
suffixes = []

[[zone]]
name = "source"
prefixes = ["src/"]
owner = "test-owner"
criticality = "medium"

[[zone]]
name = "machine"
prefixes = [".machine/"]
owner = "repository-control-plane"
criticality = "high"
"""


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments],
                   check=True, capture_output=True, timeout=20)


class GitAtlasTests(unittest.TestCase):
    def fixture(self) -> tempfile.TemporaryDirectory[str]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        git(root, "init", "-q")
        git(root, "config", "user.email", "atlas@example.invalid")
        git(root, "config", "user.name", "Atlas Test")
        (root / ".machine").mkdir()
        (root / "src").mkdir()
        (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
        (root / "src" / "first.py").write_text("x = 1\n", encoding="utf-8")
        (root / "src" / "second.py").write_text("x = 1\n", encoding="utf-8")
        (root / "src" / "different.py").write_text("x = 2\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "initial fixture")
        return temp

    def test_inventory_is_exhaustive_and_content_addressed(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            (root / "src" / "untracked.py").write_text("not tracked\n", encoding="utf-8")
            data = inventory(root)
            summary = data["summary"]
            self.assertTrue(summary["complete"])
            self.assertEqual(summary["tracked_entries"], 4)
            self.assertEqual(summary["blobs"], 4)
            self.assertEqual(summary["gitlinks"], 0)
            self.assertEqual(summary["exact_duplicate_groups"], 1)
            self.assertEqual(summary["exact_duplicate_excess_paths"], 1)
            self.assertEqual(data["exact_duplicates"][0]["paths"],
                             ["src/first.py", "src/second.py"])
            self.assertEqual(summary["zones"]["source"]["files"], 3)
            self.assertEqual(summary["features"]["source:first.py"], 1)
            self.assertNotIn("src/untracked.py", {entry["path"] for entry in data["files"]})

    def test_index_uses_committed_content_not_dirty_tree(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            before = inventory(root)
            (root / "src" / "first.py").write_text("changed and dirty\n", encoding="utf-8")
            after = inventory(root)
            self.assertEqual(before, after)
            git(root, "add", "src/first.py")
            git(root, "commit", "-qm", "tracked change")
            changed = inventory(root)
            self.assertNotEqual(changed["summary"]["tree"], before["summary"]["tree"])
            self.assertEqual(changed["summary"]["exact_duplicate_groups"], 0)

    def test_artifacts_are_deterministic_and_have_checksums(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            data = inventory(root)
            left, right = root / "left", root / "right"
            hashes = write_artifacts(data, left)
            self.assertEqual(hashes, write_artifacts(data, right))
            for name in ("files.jsonl", "exact-duplicates.json", "summary.json"):
                self.assertEqual((left / name).read_bytes(), (right / name).read_bytes())
            summary = json.loads((left / "summary.json").read_text())
            self.assertEqual(summary["artifact_sha256"], hashes)
            self.assertEqual(len((left / "files.jsonl").read_text().splitlines()), 4)

    def test_entry_limit_fails_closed(self) -> None:
        with self.fixture() as temp:
            with patch("skeleton.repo_machine.git_atlas.MAX_ENTRIES", 3):
                with self.assertRaisesRegex(AtlasError, "entry bound"):
                    inventory(temp)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_is_indexed_without_following_it(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            try:
                (root / "src" / "alias").symlink_to("first.py")
            except OSError:
                self.skipTest("creating a symlink not permitted")
            git(root, "add", "src/alias")
            git(root, "commit", "-qm", "tracked symlink")
            row = next(item for item in inventory(root)["files"]
                       if item["path"] == "src/alias")
            self.assertEqual(row["mode"], "120000")
            self.assertEqual(row["bytes"], len("first.py"))

    def test_rejects_wrong_root(self) -> None:
        with self.fixture() as temp:
            with self.assertRaises(AtlasError):
                inventory(Path(temp) / "src")


if __name__ == "__main__":
    unittest.main()
