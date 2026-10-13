"""Behavioral, safety and receipt regressions for Git atlas near-duplicate candidates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.build_git_atlas import write
from scripts.build_git_atlas_near import analyze, near_pairs, structural_digest, token_signature, _verify_file


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()


class NearDuplicateAtlasTests(unittest.TestCase):
    def repository(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        git(root, "init", "-q")
        git(root, "config", "user.name", "Fixture")
        git(root, "config", "user.email", "fixture@example.invalid")
        (root / ".machine").mkdir()
        (root / ".machine/repository.toml").write_text(
            '[[zone]]\nname = "code"\nowner = "code-team"\nprefixes = ["code/"]\n',
            encoding="utf-8",
        )
        (root / "machine").mkdir()
        (root / "machine/architecture.json").write_text(
            json.dumps({"canonical_roots": [{"path": "code"}]}),
            encoding="utf-8",
        )
        (root / "machine/ai_file_tree.json").write_text(
            '{"mappings": []}\n', encoding="utf-8"
        )
        (root / "code").mkdir()
        program = (
            "def calculate(number):\n"
            "    total = 0\n"
            "    for index in range(number):\n"
            "        total += index * index\n"
            "    return total\n"
        )
        (root / "code/a.py").write_text(program, encoding="utf-8")
        (root / "code/b.py").write_text(
            "# different comment but equivalent syntax\n" + program,
            encoding="utf-8",
        )
        (root / "code/c.py").write_text(
            program.replace("index * index", "index * 3"),
            encoding="utf-8",
        )
        git(root, "add", ".")
        git(root, "commit", "-qm", "fixture")
        return temp, root

    def test_ast_normalization_ignores_whitespace_and_comments(self) -> None:
        code = "def demo(value):\n    return value + 1\n"
        self.assertEqual(
            structural_digest(code, "a.py"),
            structural_digest("# note\n" + code.replace("value + 1", "value+1"), "b.py"),
        )
        self.assertNotEqual(structural_digest(code, "a.py"), structural_digest(
            code.replace("+ 1", "+ 2"), "a.py",
        ))

    def test_simhash_candidate_and_overflow_are_explicit(self) -> None:
        signature = token_signature(
            "def sample(alpha):\n    total = alpha * alpha\n"
            "    return total + sample(alpha) + sample(alpha)\n"
        )
        self.assertIsNotNone(signature)
        assert signature is not None
        record = {"simhash": signature[0], "words": signature[1],
                  "tokens": signature[2], "path": "one.py", "sha": "a" * 40}
        other = dict(record, path="two.py", sha="b" * 40)
        candidates, report = near_pairs([record, other])
        self.assertEqual(len(candidates), 1)
        self.assertTrue(report["candidate_search_complete"])
        third = dict(record, path="three.py", sha="c" * 40)
        excluded, report = near_pairs([record, other, third], max_bucket=2)
        self.assertEqual(excluded, [])
        self.assertGreater(report["overflow_buckets"], 0)
        self.assertFalse(report["candidate_search_complete"])

    def test_end_to_end_git_verified_structural_groups_and_receipts(self) -> None:
        temp, root = self.repository()
        with temp:
            index = root / "index"
            write(root, index)
            report = analyze(root, index, index)
            self.assertGreaterEqual(report["normalized_duplicate_groups"], 1)
            self.assertEqual(report["eligible_unique_source_blobs"], 3)
            self.assertEqual(report["commit"], git(root, "rev-parse", "HEAD"))
            self.assertFalse(report["fully_exhaustive_similarity"])
            self.assertEqual(report["disposition"], "review_only_no_auto_delete_or_consolidation")
            for name, receipt in report["artifacts"].items():
                blob = (index / name).read_bytes()
                self.assertEqual(len(blob), receipt["size"])
                self.assertEqual(hashlib.sha256(blob).hexdigest(), receipt["sha256"])

    def test_uncommitted_source_changes_fail_blob_verification(self) -> None:
        temp, root = self.repository()
        with temp:
            original_sha = git(root, "hash-object", "code/a.py")
            (root / "code/a.py").write_text("dirty code\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from pinned Git blob"):
                _verify_file(root, "code/a.py", original_sha, 65536)

    def test_tampered_upstream_index_fails_closed(self) -> None:
        temp, root = self.repository()
        with temp:
            index = root / "index"
            write(root, index)
            with (index / "files.jsonl").open("ab") as stream:
                stream.write(b"{}\n")
            with self.assertRaisesRegex(ValueError, "ledger digest mismatch"):
                analyze(root, index, index)

    def test_similarity_never_executes_repository_source(self) -> None:
        malicious = (
            "from pathlib import Path\n"
            "raise RuntimeError('must not run')\n"
            "def suspicious():\n"
            "    return Path('do-not-create').write_text('unsafe')\n"
        )
        self.assertIsNotNone(structural_digest(malicious, "unsafe.py"))
        self.assertFalse(Path("do-not-create").exists())


if __name__ == "__main__":
    unittest.main()
