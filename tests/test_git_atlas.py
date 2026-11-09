"""Regression tests for the exhaustive Git-based repository atlas."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.build_git_atlas import build, write
from scripts.query_git_atlas import query


POLICY = """
[repository]
schema_version = 1
name = "fixture"

[[zone]]
name = "runtime"
owner = "engine"
lifecycle = "canonical"
prefixes = ["app/"]

[[zone]]
name = "archive"
owner = "archive"
lifecycle = "historical"
prefixes = ["satellites/"]
"""


def command(root: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *arguments], stderr=subprocess.STDOUT
    ).decode().strip()


class GitAtlasTests(unittest.TestCase):
    def make_repository(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        command(root, "init", "-q")
        command(root, "config", "user.email", "fixture@example.invalid")
        command(root, "config", "user.name", "Fixture")
        (root / ".machine").mkdir()
        (root / ".machine/repository.toml").write_text(POLICY, encoding="utf-8")
        (root / "machine").mkdir()
        (root / "machine/architecture.json").write_text(
            json.dumps({"canonical_roots": [{"path": "app"}]}), encoding="utf-8"
        )
        (root / "machine/ai_file_tree.json").write_text(
            json.dumps({"mappings": [
                {"id": "AIFT-TEST", "source": "app/a.py", "destination": "app/ai/a.py"}
            ]}), encoding="utf-8"
        )
        (root / "app").mkdir()
        (root / "app/a.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "app/b.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "app/c.py").write_text("VALUE = 2\n", encoding="utf-8")
        (root / "satellites/branch-snapshots/test").mkdir(parents=True)
        (root / "satellites/branch-snapshots/test/a.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )
        (root / "app/link.py").symlink_to("a.py")
        command(root, "add", ".")
        command(root, "commit", "-qm", "fixture")
        return temporary, root

    def test_complete_git_inventory_exact_copies_and_feature_identity(self) -> None:
        temp, root = self.make_repository()
        with temp:
            summary, entries, duplicates, nav = build(root)
            files = {entry["path"]: entry for entry in entries}
            self.assertEqual(summary["tracked_entries"], 8)
            self.assertFalse(summary["truncated"])
            self.assertEqual(summary["symlinks"], 1)
            self.assertEqual(summary["snapshot_entries"], 1)
            self.assertEqual(files["app/a.py"]["feature"], "AIFT-TEST")
            self.assertEqual(files["app/a.py"]["owner"], "engine")
            self.assertEqual(files["app/link.py"]["mode"], "120000")
            self.assertEqual(files["app/link.py"]["type"], "blob")
            self.assertEqual(summary["extra_exact_copies"], 2)
            self.assertEqual(len(duplicates), 1)
            self.assertEqual(duplicates[0]["snapshot_copies"], 1)
            self.assertIn("app/a.py", duplicates[0]["paths"])
            self.assertTrue(nav["features"])
            self.assertEqual(summary["commit"], command(root, "rev-parse", "HEAD"))

    def test_snapshot_is_not_authorized_to_delete_and_is_counted(self) -> None:
        temp, root = self.make_repository()
        with temp:
            summary, _, dupes, _ = build(root)
            self.assertEqual(summary["destructive_actions"], "prohibited")
            self.assertTrue(all(group["disposition"] == "review_only_never_auto_delete" for group in dupes))

    def test_uncommitted_worktree_changes_do_not_poison_index(self) -> None:
        temp, root = self.make_repository()
        with temp:
            original = build(root)
            (root / "app/a.py").write_text("UNCOMMITTED = True\n", encoding="utf-8")
            (root / "app/new.py").write_text("untracked\n", encoding="utf-8")
            self.assertEqual(build(root), original)

    def test_deterministic_artifacts_and_receipt(self) -> None:
        temp, root = self.make_repository()
        with temp:
            first = root / "first"
            second = root / "second"
            a = write(root, first)
            b = write(root, second)
            self.assertEqual(a, b)
            for name, receipt in a["artifacts"].items():
                content = (first / name).read_bytes()
                self.assertEqual(content, (second / name).read_bytes())
                self.assertEqual(hashlib.sha256(content).hexdigest(), receipt["sha256"])
                self.assertEqual(len(content), receipt["size"])
            self.assertNotIn("summary.json", a["artifacts"])

    def test_revision_is_pinned_and_invalid_options_rejected(self) -> None:
        temp, root = self.make_repository()
        with temp:
            with self.assertRaisesRegex(ValueError, "revision"):
                build(root, "--all")
            with self.assertRaisesRegex(ValueError, "git rev-parse failed"):
                build(root, "missing-commit")
            sha = command(root, "rev-parse", "HEAD")
            self.assertEqual(build(root, sha)[0]["commit"], sha)

    def test_gitlink_retained_without_file_contents(self) -> None:
        temp, root = self.make_repository()
        with temp:
            sha = command(root, "rev-parse", "HEAD")
            command(root, "update-index", "--add", "--cacheinfo", f"160000,{sha},vendor/submodule")
            command(root, "commit", "-qm", "gitlink")
            summary, entries, _, _ = build(root)
            self.assertEqual(summary["gitlinks"], 1)
            link = next(item for item in entries if item["path"] == "vendor/submodule")
            self.assertEqual(link["type"], "commit")
            self.assertIsNone(link["size"])

    def test_case_collisions_reported_not_silently_collapsed(self) -> None:
        temp, root = self.make_repository()
        with temp:
            (root / "app/Case.py").write_text("A\n", encoding="utf-8")
            (root / "app/case.py").write_text("B\n", encoding="utf-8")
            command(root, "add", ".")
            command(root, "commit", "-qm", "collision")
            summary, entries, _, _ = build(root)
            self.assertEqual(summary["case_collision_count"], 1)
            self.assertEqual(len([item for item in entries if item["path"].lower() == "app/case.py"]), 2)

    def test_uncommitted_authority_change_fails_closed(self) -> None:
        temp, root = self.make_repository()
        with temp:
            policy = root / ".machine/repository.toml"
            policy.write_text(POLICY + "\n# dirty authority\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from pinned Git commit"):
                build(root)

    def test_symlink_output_fails_closed(self) -> None:
        temp, root = self.make_repository()
        with temp:
            output = root / "unsafe-index"
            output.symlink_to(root / "machine", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                write(root, output)

    def test_context_query_is_budgeted_and_sha_pinned(self) -> None:
        temp, root = self.make_repository()
        with temp:
            index = root / "atlas"
            write(root, index)
            result = query(root, index, "app", budget_bytes=1100, max_hits=2)
            self.assertTrue(result["hits"])
            self.assertEqual(result["commit"], command(root, "rev-parse", "HEAD"))
            self.assertLessEqual(len(json.dumps(result, sort_keys=True).encode()), 1100)
            self.assertEqual(result["retrieval"], "metadata_only_review_source_before_editing")

    def test_context_rejects_dirty_index_and_stale_commit(self) -> None:
        temp, root = self.make_repository()
        with temp:
            index = root / "atlas"
            write(root, index)
            navigation = index / "navigation.json"
            navigation.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity"):
                query(root, index, "app")
            write(root, index)
            (root / "app/new.py").write_text("VALUE = 5\n", encoding="utf-8")
            command(root, "add", "app/new.py")
            command(root, "commit", "-qm", "change checkout head")
            with self.assertRaisesRegex(ValueError, "stale atlas"):
                query(root, index, "app")

    def test_missing_canonical_authority_fails_closed(self) -> None:
        temp, root = self.make_repository()
        with temp:
            (root / "machine/architecture.json").unlink()
            with self.assertRaisesRegex(ValueError, "canonical repository policy"):
                build(root)


if __name__ == "__main__":
    unittest.main()
