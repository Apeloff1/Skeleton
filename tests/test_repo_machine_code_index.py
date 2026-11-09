from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repo_machine_code_index",
    ROOT / "skeleton" / "repo_machine" / "code_index.py",
)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


class CrossLanguageCodeIndexTests(unittest.TestCase):
    def test_python_parser_records_are_high_confidence(self) -> None:
        symbols, refs = M.extract_records(
            "pkg/example.py",
            "import json\nclass A: pass\ndef f(): return 1\n",
        )
        self.assertEqual({s.name for s in symbols}, {"A", "f"})
        self.assertTrue(all(s.confidence == "parser" for s in symbols))
        self.assertIn("json", {r.target for r in refs})

    def test_typescript_go_rust_and_cpp_are_indexed(self) -> None:
        fixtures = {
            "ui.ts": "export interface User {}\nexport function load() {}\nimport x from 'pkg';\n",
            "main.go": 'import "fmt"\nfunc Run() {}\ntype State struct {}\n',
            "lib.rs": "pub struct Engine {}\npub fn run() {}\nuse crate::core;\n",
            "main.cpp": '#include "thing.hpp"\nclass Engine {};\nint run() { return 0; }\n',
        }
        for path, content in fixtures.items():
            with self.subTest(path=path):
                symbols, refs = M.extract_records(path, content)
                self.assertTrue(symbols)
                self.assertTrue(all(s.confidence == "heuristic" for s in symbols))
                self.assertTrue(refs)

    def test_malformed_python_fails_closed(self) -> None:
        with self.assertRaises(M.CodeIndexError):
            M.extract_records("pkg/broken.py", "def broken(:\n")

    def test_noncanonical_path_fails_closed(self) -> None:
        with self.assertRaises(M.CodeIndexError):
            M.extract_records("../escape.py", "x = 1\n")
        with self.assertRaises(M.CodeIndexError):
            M.extract_records("pkg\\escape.py", "x = 1\n")

    def test_duplicate_inventory_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(M.CodeIndexError, "duplicate source path"):
            M.build_language_inventory(
                (("pkg/a.py", "x = 1\n"), ("pkg/a.py", "y = 2\n"))
            )

    def test_oversized_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(M.CodeIndexError, "exceeds"):
            M.extract_records("pkg/huge.py", "x" * 5_000_001)

    def test_unknown_suffix_is_explicitly_unindexed(self) -> None:
        self.assertIsNone(M.language_for_path("notes.txt"))
        self.assertEqual(M.extract_records("notes.txt", "class fake"), ((), ()))


if __name__ == "__main__":
    unittest.main()
