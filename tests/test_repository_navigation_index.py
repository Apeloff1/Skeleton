"""Read-only, full Git-tree inventory regression tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("repository_navigation", ROOT / "scripts" / "build_repository_navigation_index.py")
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


class RepositoryNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Navigation Tests"], check=True)
        self.write(".machine/repository.toml", """
[[zone]]
name = "ai"
prefixes = ["skeleton/ai/"]
owner = "ai-owner"
lifecycle = "canonical"
[[zone]]
name = "backend"
prefixes = ["backend/"]
owner = "backend-owner"
lifecycle = "canonical"
[[zone]]
name = "historical"
prefixes = ["satellites/"]
owner = "history-owner"
lifecycle = "historical"
""")
        common = "def evaluate(x):\n    # shared structured text\n    return len(str(x)) + len(str(x)) + len(str(x)) + len(str(x)) + len(str(x))\n"
        common = common + "\n" + "\n".join(f"def operation_{i}(value): return evaluate(value) + {i}" for i in range(25)) + "\n"
        self.write("skeleton/ai/game/engine.py", common)
        self.write("backend/game/engine.py", common)
        self.write("satellites/branch-snapshots/old/backend/game/engine.py", common.replace("len(str(x)) + len", "len(str(x)) +  len", 1))
        self.write("backend/game/unique.py", "print('unique')\n")
        self.write("backend/assets/a.bin", b"\x00\xff\x08")
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "test"], check=True)
        self.out = self.root / ".machine" / "navigation"

    def write(self, path: str, data: str | bytes) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.encode() if isinstance(data, str) else data)

    def test_full_tree_includes_satellites_binary_and_configuration(self) -> None:
        summary = M.build(self.root, self.out)
        self.assertEqual(summary["file_count"], 6)
        self.assertEqual(summary["exact_duplicate_groups"], 1)
        self.assertEqual(summary["exact_extra_copies"], 1)
        self.assertEqual(summary["unclassified_files"], 1)
        rows = [json.loads(line) for line in (self.out / "files.jsonl").read_text().splitlines()]
        self.assertEqual(rows, sorted(rows, key=lambda row: row["path"]))
        self.assertEqual(next(row for row in rows if row["path"] == "backend/assets/a.bin")["size"], 3)
        self.assertEqual(next(row for row in rows if row["path"] == "skeleton/ai/game/engine.py")["owner"], "ai-owner")
        duplicates = json.loads((self.out / "exact-duplicates.json").read_text())["data"]
        self.assertEqual(duplicates[0]["paths"], ["backend/game/engine.py", "skeleton/ai/game/engine.py"])

    def test_near_duplicate_classification_is_content_verified_and_non_destructive(self) -> None:
        M.build(self.root, self.out, near_limit=20, near_threshold=0.7)
        near = json.loads((self.out / "near-duplicates.json").read_text())["data"]
        self.assertGreaterEqual(near["candidate_pairs_inspected"], 1)
        self.assertGreaterEqual(len(near["content_verified_matches"]), 1)
        self.assertTrue(all(row["classification"] == "review-required" for row in near["content_verified_matches"]))
        self.assertTrue((self.root / "backend/game/unique.py").exists())

    def test_query_is_bounded_and_commit_bound(self) -> None:
        summary = M.build(self.root, self.out, near_limit=0)
        result = M.query(self.out, "engine", max_bytes=1024)
        self.assertEqual(result["commit"], summary["commit"])
        self.assertEqual(result["total_hits"], 3)
        self.assertTrue(all("owner" in row for row in result["hits"]))
        self.assertFalse((self.out / "files.jsonl.tmp").exists())

    def test_query_rejects_tampered_shard(self) -> None:
        M.build(self.root, self.out, near_limit=0)
        with (self.out / "files.jsonl").open("a", encoding="utf-8") as file:
            file.write('{"path":"injected.py"}\n')
        with self.assertRaisesRegex(M.InventoryError, "corrupt navigation shard"):
            M.query(self.out, "engine")

    def test_query_rejects_wrong_commit(self) -> None:
        M.build(self.root, self.out, near_limit=0)
        with self.assertRaisesRegex(M.InventoryError, "stale"):
            M.query(self.out, "engine", expected_commit="0" * 40)

    def test_readonly_index_does_not_move_canonical_code(self) -> None:
        before = M.git(self.root, "ls-tree", "-r", "HEAD")
        M.build(self.root, self.out, near_limit=2)
        after = M.git(self.root, "ls-tree", "-r", "HEAD")
        self.assertEqual(before, after)
        self.assertEqual(M.git(self.root, "status", "--porcelain", "--untracked-files=no"), b"")

    def test_idempotent_build(self) -> None:
        first = M.build(self.root, self.out, near_limit=0)
        second = M.build(self.root, self.out, near_limit=0)
        self.assertEqual(first, second)
        for name in first["indexes"]:
            import hashlib
            self.assertEqual(first["artifact_digests"][name], hashlib.sha256((self.out / name).read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
