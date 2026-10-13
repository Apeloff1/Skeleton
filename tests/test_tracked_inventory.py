"""Regression tests for the read-only, pinned-commit repository atlas."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from skeleton.repo_machine.tracked_inventory import (
    TrackedAtlasError,
    build_from_git,
    parse_tree,
    publish,
)


class ParseTreeTests(unittest.TestCase):
    def test_nul_delimited_paths_preserve_tabs_and_newlines(self) -> None:
        sha = b"a" * 40
        record = b"100644 blob " + sha + b" 3\todd\tname\n.py\0"
        parsed = parse_tree(record)
        self.assertEqual(parsed[0]["path"], "odd\tname\n.py")
        self.assertEqual(parsed[0]["size"], 3)

    def test_gitlink_and_symlink_modes_remain_distinct(self) -> None:
        sha = b"a" * 40
        raw = (
            b"120000 blob " + sha + b" 6\tlink\0"
            + b"160000 commit " + sha + b" -\tmodules/external\0"
        )
        parsed = parse_tree(raw)
        self.assertEqual([row["mode"] for row in parsed], ["120000", "160000"])
        self.assertIsNone(parsed[1]["size"])

    def test_reject_incomplete_ambiguous_and_truncated_trees(self) -> None:
        sha = b"a" * 40
        good = b"100644 blob " + sha + b" 1\tsrc/a.py\0"
        for data in (
            good[:-1],
            good + good,
            good.replace(b"src/a.py", b"../escape.py"),
            good.replace(b"blob", b"commit"),
            good.replace(b" 1\t", b" -\t"),
        ):
            with self.subTest(data=data[:45]), self.assertRaises(TrackedAtlasError):
                parse_tree(data)
        with self.assertRaises(TrackedAtlasError):
            parse_tree(good, max_files=0)


@unittest.skipUnless(shutil.which("git"), "Git executable is required")
class TrackedGitAtlasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self._git("init", "-q")
        machine = self.root / ".machine"
        machine.mkdir()
        (machine / "repository.toml").write_text(
            '[repository]\n'
            'schema_version = 1\n'
            'name = "fixture"\n'
            'default_owner = "example"\n'
            '[policy]\n'
            'require_tests_for_code = false\n'
            '[[zone]]\n'
            'name = "application"\n'
            'prefixes = ["src/"]\n'
            'owner = "app-team"\n'
            'lifecycle = "canonical"\n'
            '[[zone]]\n'
            'name = "snapshots"\n'
            'prefixes = ["satellites/"]\n'
            'owner = "archive-team"\n'
            'lifecycle = "transitional"\n',
            encoding="utf-8",
        )
        (self.root / "src").mkdir()
        (self.root / "src" / "one.py").write_text("print('same')\n", encoding="utf-8")
        (self.root / "src" / "two.py").write_text("print('same')\n", encoding="utf-8")
        (self.root / "src" / "other.py").write_text("print('different')\n", encoding="utf-8")
        self._git("add", ".")
        self._git("-c", "user.name=Atlas Test", "-c", "user.email=atlas@example.invalid",
                  "commit", "-qm", "fixture")

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True
        )
        return result.stdout.strip()

    def test_whole_tree_deterministic_and_exacts(self) -> None:
        artifacts = build_from_git(self.root)
        self.assertEqual(artifacts, build_from_git(self.root))
        manifest = json.loads(artifacts["manifest.json"])
        self.assertEqual(manifest["tracked_entries"], 4)
        self.assertEqual(manifest["source_commit"], self._git("rev-parse", "HEAD"))
        self.assertEqual(manifest["coverage"], "complete")
        self.assertEqual(manifest["exact_duplicate_groups"], 1)
        self.assertEqual(manifest["exact_duplicate_paths"], 2)
        rows = [json.loads(line) for line in artifacts["files.jsonl"].splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["zone"] for r in rows if r["path"].startswith("src/")}, {"application"})
        dup = json.loads(artifacts["exact-duplicates.json"])
        self.assertEqual(dup["groups"][0]["paths"], ["src/one.py", "src/two.py"])
        self.assertEqual(dup["groups"][0]["mode"], "100644")

    def test_stale_inventory_fails_check_and_uncommitted_changes_are_ignored(self) -> None:
        expected = build_from_git(self.root)
        out = self.root / "out"
        publish(expected, out)
        publish(expected, out, check=True)
        (self.root / "src" / "one.py").write_text("not committed\n", encoding="utf-8")
        self.assertEqual(build_from_git(self.root), expected)
        (out / "files.jsonl").write_bytes(b"damaged\n")
        with self.assertRaises(TrackedAtlasError):
            publish(expected, out, check=True)

    def test_new_commit_changes_inventory_and_leaves_old_snapshot_stale(self) -> None:
        old = build_from_git(self.root)
        (self.root / "src" / "new.py").write_text("print('new')\n", encoding="utf-8")
        self._git("add", "src/new.py")
        self._git("-c", "user.name=Atlas Test", "-c", "user.email=atlas@example.invalid",
                  "commit", "-qm", "add")
        new = build_from_git(self.root)
        self.assertNotEqual(old["manifest.json"], new["manifest.json"])
        self.assertEqual(json.loads(new["manifest.json"])["tracked_entries"], 5)
        out = self.root / "out"
        publish(old, out)
        with self.assertRaises(TrackedAtlasError):
            publish(new, out, check=True)


if __name__ == "__main__":
    unittest.main()
