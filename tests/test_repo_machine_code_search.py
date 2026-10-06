from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.code_search import (
    CodeSearchError,
    CodeSearchIndex,
    load_code_search_index,
    save_code_search_index,
)


CONFIG = """
[repository]
schema_version = 1
name = "fixture"
default_owner = "supervisor"
max_files = 100
max_file_bytes = 100000
max_context_bytes = 30000

[policy]
require_tests_for_code = false
require_readme_for_top_level_code = false
detect_dependency_cycles = true
detect_oversized_modules = false
oversized_python_lines = 1000
oversized_javascript_lines = 1000
oversized_generic_lines = 1000

[[zone]]
name = "alpha"
prefixes = ["alpha/"]
owner = "alpha-team"
criticality = "high"

[[zone]]
name = "tests"
prefixes = ["tests/"]
owner = "quality"
criticality = "high"

[ignore]
prefixes = [".git/", ".machine/", "__pycache__/"]
suffixes = [".pyc"]
"""


class CodeSearchIndexTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / ".machine").mkdir()
        (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
        (root / "alpha").mkdir()
        (root / "tests").mkdir()
        (root / "alpha" / "service.py").write_text(
            "class RenderEngine:\\n"
            "    def render_scene(self, scene):\\n"
            "        return normalize_scene(scene)\\n\\n"
            "def normalize_scene(scene):\\n"
            "    return scene\\n",
            encoding="utf-8",
        )
        (root / "alpha" / "consumer.py").write_text(
            "from alpha.service import RenderEngine\\n\\n"
            "def run():\\n"
            "    engine = RenderEngine()\\n"
            "    return engine.render_scene({})\\n",
            encoding="utf-8",
        )
        (root / "tests" / "test_service.py").write_text(
            "from alpha.service import RenderEngine\\n\\n"
            "def test_render():\\n"
            "    assert RenderEngine().render_scene({}) == {}\\n",
            encoding="utf-8",
        )
        return temp, root

    def test_definition_outranks_references(self) -> None:
        temp, root = self.fixture()
        with temp:
            model = RepositoryModelBuilder(root).build()
            index = CodeSearchIndex.build(root, model)
            hits = index.search("RenderEngine")
            self.assertGreaterEqual(len(hits), 3)
            self.assertEqual(hits[0].path, "alpha/service.py")
            self.assertEqual(hits[0].match_kind, "definition")
            self.assertEqual(hits[0].line, 1)
            self.assertIn("renderengine", hits[0].matched_terms)

    def test_function_definition_has_line_level_evidence(self) -> None:
        temp, root = self.fixture()
        with temp:
            model = RepositoryModelBuilder(root).build()
            index = CodeSearchIndex.build(root, model)
            hits = index.search("render_scene")
            self.assertEqual(hits[0].path, "alpha/service.py")
            self.assertEqual(hits[0].line, 2)
            self.assertEqual(hits[0].match_kind, "definition")
            self.assertGreaterEqual(hits[0].occurrence_count, 1)

    def test_path_and_filter_search_are_deterministic(self) -> None:
        temp, root = self.fixture()
        with temp:
            model = RepositoryModelBuilder(root).build()
            index = CodeSearchIndex.build(root, model)
            first = index.search("service", zones=["alpha"])
            second = index.search("service", zones=["alpha"])
            self.assertEqual(first, second)
            self.assertTrue(first)
            self.assertEqual(first[0].path, "alpha/service.py")
            self.assertTrue(all(hit.zone == "alpha" for hit in first))

    def test_save_load_round_trip_and_fingerprint_binding(self) -> None:
        temp, root = self.fixture()
        with temp:
            model = RepositoryModelBuilder(root).build()
            index = CodeSearchIndex.build(root, model)
            target = root / ".machine" / "code-search-index.json"
            save_code_search_index(index, target)
            loaded = load_code_search_index(
                target,
                expected_fingerprint=model.fingerprint,
            )
            self.assertEqual(loaded.summary(), index.summary())
            self.assertEqual(
                loaded.search("RenderEngine"),
                index.search("RenderEngine"),
            )
            with self.assertRaisesRegex(CodeSearchError, "fingerprint"):
                load_code_search_index(target, expected_fingerprint="0" * 64)

    def test_checksum_corruption_fails_closed(self) -> None:
        temp, root = self.fixture()
        with temp:
            model = RepositoryModelBuilder(root).build()
            index = CodeSearchIndex.build(root, model)
            target = root / ".machine" / "code-search-index.json"
            save_code_search_index(index, target)
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["state"]["repository"] = "tampered"
            target.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(CodeSearchError, "checksum"):
                load_code_search_index(target)

    def test_source_drift_fails_closed(self) -> None:
        temp, root = self.fixture()
        with temp:
            model = RepositoryModelBuilder(root).build()
            (root / "alpha" / "service.py").write_text(
                "class Changed:\\n    pass\\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CodeSearchError, "changed since repository model"):
                CodeSearchIndex.build(root, model)

    def test_oversized_source_is_explicitly_skipped(self) -> None:
        temp, root = self.fixture()
        with temp:
            model = RepositoryModelBuilder(root).build()
            index = CodeSearchIndex.build(root, model, max_source_bytes=20)
            skipped = dict(index.skipped)
            self.assertIn("alpha/service.py", skipped)
            self.assertIn("byte bound", skipped["alpha/service.py"])
            self.assertNotIn("alpha/service.py", {item.path for item in index.documents})


if __name__ == "__main__":
    unittest.main()
