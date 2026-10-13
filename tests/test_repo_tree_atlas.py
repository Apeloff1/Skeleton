"""Regression contracts for the exhaustive, non-mutating Git-tree atlas."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from skeleton.repo_intelligence.tree_atlas import (
    AtlasError, _canonical, build, directory_index, exact_duplicates, feature_index, query, scan, write_index,
)


class RepositoryTreeAtlasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self._git("init", "-q")
        self._git("config", "user.name", "Atlas Test")
        self._git("config", "user.email", "atlas@example.invalid")
        self._write(".machine/repository.toml", (
            "[[zone]]\nname='ai'\nowner='ai-runtime'\nlifecycle='canonical'\n"
            "prefixes=['skeleton/ai/']\n"
            "[[zone]]\nname='history'\nowner='archive'\nlifecycle='historical'\n"
            "prefixes=['satellites/']\n"
            "[[zone]]\nname='misc'\nowner='repository-control-plane'\n"
            "prefixes=['machine/', 'scripts/']\n"
        ))
        self._write("machine/ai_file_tree.json", json.dumps({
            "mappings": [{"id": "AIFT-QUEST", "kind": "tree",
                          "source": "skeleton/ai/quest", "destination": "skeleton/ai/quests"}]
        }))
        self._write("skeleton/ai/quest/core.py", "def hello(): return 42\n")
        self._write("skeleton/ai/quests/core.py", "def hello(): return 42\n")
        self._write("satellites/branch-snapshots/archive/core.py", "def hello(): return 42\n")
        self._write("scripts/README.md", "machine map\n")
        self._commit()

    def _git(self, *args: str) -> str:
        run = subprocess.run(["git", *args], cwd=self.root, check=True,
                             capture_output=True, text=True)
        return run.stdout.strip()

    def _write(self, path: str, content: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _commit(self) -> None:
        self._git("add", ".")
        self._git("commit", "-qm", "fixture")

    def test_complete_tree_exact_duplicates_and_provenance(self) -> None:
        commit, tree, records = scan(self.root)
        self.assertEqual(commit, self._git("rev-parse", "HEAD"))
        self.assertEqual(tree, self._git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(len(records), 6)
        mapping = {r.path: r for r in records}
        self.assertEqual(mapping["skeleton/ai/quest/core.py"].feature, "AIFT-QUEST")
        self.assertEqual(mapping["skeleton/ai/quests/core.py"].feature, "AIFT-QUEST")
        self.assertEqual(mapping["satellites/branch-snapshots/archive/core.py"].lifecycle,
                         "historical-snapshot")
        twins = exact_duplicates(records)
        self.assertTrue(any(len(group["paths"]) == 3 for group in twins))
        features = {row["id"]: row for row in feature_index(records)}
        self.assertEqual(features["AIFT-QUEST"]["files"], 2)
        directories = {row["path"]: row for row in directory_index(records)}
        self.assertEqual(directories["skeleton/ai"]["files"], 2)
        self.assertEqual(directories["skeleton/ai/quest"]["immediate_files"], 1)

    def test_more_files_than_policy_limit_are_never_truncated(self) -> None:
        for i in range(90):
            self._write(f"skeleton/ai/test/file_{i:03d}.py", f"constant = {i}\n")
        self._commit()
        _head, _tree, files = scan(self.root)
        self.assertEqual(len(files), 96)
        self.assertEqual(len({f.path for f in files}), 96)

    def test_stable_outputs_and_stale_index_fail_closed(self) -> None:
        output = self.root / "atlas-output"
        manifest, files, copies, near = build(self.root)
        write_index(output, manifest, files, copies, near)
        initial = {p.name: p.read_bytes() for p in output.iterdir()}
        write_index(output, *build(self.root))
        self.assertEqual(initial, {p.name: p.read_bytes() for p in output.iterdir()})
        result = query(output, self.root, "quest", budget=500, limit=2)
        self.assertLessEqual(result["used_bytes"], 500)
        self.assertTrue(result["hits"])
        self._write("skeleton/ai/quest/core.py", "def hello(): return 43\n")
        self._commit()
        with self.assertRaisesRegex(AtlasError, "stale"):
            query(output, self.root, "quest")

    def test_near_duplicate_scan_is_explicitly_bounded(self) -> None:
        original = ("def calculate_health(value, armor):\n"
                    "    remaining = max(0, value - armor)\n"
                    "    return remaining\n") * 18
        self._write("skeleton/ai/quest/health.py", original)
        self._write("skeleton/ai/quests/health.py", original.replace("return remaining\n",
                              "return max(0, remaining)\n", 1))
        self._commit()
        manifest, files, duplicates, near = build(self.root, near_limit=100)
        self.assertFalse(near["exhaustive"])
        self.assertGreaterEqual(near["blobs_examined"], 2)
        self.assertTrue(any("health.py" in row["a"] for row in near["pairs"]))
        self.assertEqual(manifest["near_duplicate_exhaustive"], False)

    def test_symlinks_are_not_followed(self) -> None:
        link = self.root / "skeleton" / "ai" / "external"
        try:
            link.symlink_to("/etc/passwd")
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        self._git("add", "-A")
        self._git("commit", "-qm", "symlink")
        _commit, _tree, files = scan(self.root)
        target = next(f for f in files if f.path.endswith("/external"))
        self.assertEqual(target.mode, "120000")
        self.assertEqual(target.size, len("/etc/passwd"))
        self.assertFalse(any(f.path.startswith("skeleton/ai/external/") for f in files))

    def test_unsafe_paths_and_output_links_fail_closed(self) -> None:
        for path in ("../escape", "x//y", "/abs", "x/./y", "x/../y", "x\\y"):
            with self.subTest(path=path), self.assertRaises(AtlasError):
                _canonical(path)
        file = self.root / "output-link"
        try:
            file.symlink_to(self.root / "skeleton", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        with self.assertRaises(AtlasError):
            write_index(file, *build(self.root))


if __name__ == "__main__":
    unittest.main()
