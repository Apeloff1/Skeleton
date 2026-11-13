"""Offline Python AST source graph and cross-file import qualification.

Only already-reviewed source replacement text is parsed; no imported Python
module is ever loaded, compiled, run, queried over a network or resolved
through the operating system. All project files are temporary fixtures.
"""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_patch_bundle as bundle,
    desktop_source_graph as graph,
    desktop_source_qualification as qualification,
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
)


def proposal(*files):
    return json.dumps({
        "schema": workspace.SCHEMA,
        "files": [{"path": p, "content": s} for p, s in files],
    }, ensure_ascii=False)


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Real original-source descriptor tests use POSIX/WSL2",
)
class ReviewedPythonGraphTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="jeeves-python-source-graph-")
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / "project"
        self.root.mkdir(mode=0o700)
        (self.root / "src").mkdir(mode=0o700)
        (self.root / "src/pkg").mkdir(mode=0o700)
        def root_fd(value):
            return os.open(value, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for module in (workspace, edits, bundle):
            pat = mock.patch.object(
                module, "_open_root", side_effect=root_fd,
            )
            pat.start()
            self.addCleanup(pat.stop)

    def plan(self, *sources):
        return bundle.review_patch_bundle(
            self.root, new_files=proposal(*sources),
        )

    def test_reviewed_modules_have_actual_sha_bound_python_import_edges(self):
        b = self.plan(
            ("src/a.py", "import src.b\nfrom .b import value\n"),
            ("src/b.py", "value = 42\n"),
            ("src/__init__.py", "from .a import main\n"),
        )
        with mock.patch("subprocess.run") as execution:
            result = graph.analyze_python_source_graph(b)
        execution.assert_not_called()
        self.assertEqual(result.status, "observed-internal-imports")
        self.assertEqual(result.linked_import_count, 3)
        self.assertEqual(result.unverified_import_count, 0)
        self.assertEqual(result.invalid_relative_count, 0)
        self.assertTrue(result.permits_inert_export)
        self.assertEqual(result.manifest_sha256, b.manifest_sha256)
        self.assertEqual(result.patch_sha256, b.patch_sha256)
        self.assertEqual(result.to_public()["graph_sha256"], result.graph_sha256)
        self.assertFalse(result.to_public()["whole_original_project_scanned"])
        self.assertFalse(result.to_public()["source_code_executed"])
        self.assertFalse(result.to_public()["all_dependencies_resolved"])
        self.assertFalse(result.to_public()["python_compiler_executed"])
        self.assertFalse(result.to_public()["release_certified"])
        self.assertFalse((self.root / "src/a.py").exists())

    def test_stdlib_and_external_imports_are_unverified_not_false_resolution(self):
        b = self.plan(
            ("src/a.py", "import os\nfrom external import engine\n"),
        )
        result = graph.analyze_python_source_graph(b)
        self.assertEqual(result.status, "partially-unverified-imports")
        self.assertEqual(result.unverified_import_count, 2)
        self.assertEqual(result.linked_import_count, 0)
        self.assertTrue(result.permits_inert_export)
        self.assertFalse(result.to_public()["all_dependencies_resolved"])
        self.assertIsInstance(qualification.require_parseable_patch(b),
                              qualification.SourceQualification)

    def test_invalid_relative_import_beyond_parent_held_before_private_export(self):
        b = self.plan(
            ("src/a.py", "from ...parent import value\nvalue = 1\n"),
        )
        static = qualification.qualify_patch_sources(b)
        self.assertEqual(static.status, "parse-clean")
        result = graph.analyze_python_source_graph(b)
        self.assertEqual(result.status, "invalid-relative-held")
        self.assertEqual(result.invalid_relative_count, 1)
        self.assertFalse(result.permits_inert_export)
        with self.assertRaises(qualification.StaticSourceHold):
            qualification.require_parseable_patch(b)
        self.assertFalse((self.root / "src/a.py").exists())

    def test_same_source_package_relative_import_one_level_is_legal(self):
        b = self.plan(
            ("src/pkg/entry.py", "from .local import run\n"),
            ("src/pkg/local.py", "def run():\n    return 1\n"),
        )
        r = graph.analyze_python_source_graph(b)
        self.assertEqual(r.invalid_relative_count, 0)
        self.assertEqual(r.linked_import_count, 1)
        self.assertEqual(r.status, "observed-internal-imports")

    def test_two_level_relative_reference_within_nested_package_is_supported(self):
        b = self.plan(
            ("src/pkg/entry.py", "from .. import bridge\n"),
            ("src/bridge.py", "bridge = 42\n"),
        )
        r = graph.analyze_python_source_graph(b)
        self.assertEqual(r.invalid_relative_count, 0)
        self.assertEqual(r.linked_import_count, 1)

    def test_two_level_parent_from_top_level_package_is_invalid(self):
        b = self.plan(
            ("src/entry.py", "from .. import bridge\n"),
        )
        r = graph.analyze_python_source_graph(b)
        self.assertEqual(r.invalid_relative_count, 1)
        self.assertEqual(r.status, "invalid-relative-held")

    def test_statically_observed_mutual_module_cycle_is_reported(self):
        b = self.plan(
            ("src/a.py", "from src import b\n"),
            ("src/b.py", "from src import a\n"),
        )
        r = graph.analyze_python_source_graph(b)
        self.assertEqual(r.linked_import_count, 2)
        self.assertEqual(len(r.cycles), 1)
        self.assertEqual(r.cycles[0], ("src/a.py", "src/b.py"))
        self.assertEqual(r.to_public()["observed_cycle_count"], 1)
        # A static cycle is an informational finding, not proof a
        # runtime import necessarily fails or should execute.
        self.assertTrue(r.permits_inert_export)
        self.assertFalse(r.to_public()["python_imports_executed"])

    def test_legitimate_python_implementation_and_pyi_stub_are_both_scanned(self):
        b = self.plan(
            ("src/model.py", "class Model: pass\n"),
            ("src/model.pyi", "class Model: ...\n"),
            ("src/user.py", "import src.model\n"),
        )
        r = graph.analyze_python_source_graph(b)
        self.assertEqual(len(r.python_files), 3)
        self.assertEqual(r.linked_import_count, 1)
        target = next(x.target_path for f in r.python_files
                      for x in f.import_links if x.target_path is not None)
        self.assertEqual(target, "src/model.py")
        self.assertTrue(r.permits_inert_export)

    def test_ambiguous_python_plain_module_and_package_claim_is_denied(self):
        b = self.plan(
            ("src/pkg.py", "value = 1\n"),
            ("src/pkg/__init__.py", "value = 2\n"),
        )
        with self.assertRaises(graph.SourceGraphHold):
            graph.analyze_python_source_graph(b)

    def test_root_init_module_does_not_accidentally_fail_static_source(self):
        b = self.plan(("__init__.py", "version = 'local'\n"))
        r = graph.analyze_python_source_graph(b)
        self.assertTrue(r.permits_inert_export)
        self.assertEqual(r.status, "observed-internal-imports")

    def test_typescript_only_still_explicitly_unverified_in_python_graph(self):
        b = self.plan(("src/app.ts", "export const x = 1;\n"))
        r = graph.analyze_python_source_graph(b)
        self.assertEqual(r.status, "no-python-source")
        self.assertEqual(len(r.python_files), 0)
        self.assertEqual(r.linked_import_count, 0)
        self.assertFalse(r.to_public()["all_dependencies_resolved"])
        self.assertTrue(r.permits_inert_export)

    def test_syntax_invalid_python_cannot_claim_complete_graph(self):
        b = self.plan(("src/invalid.py", "def x(:\n"))
        r = graph.analyze_python_source_graph(b)
        self.assertEqual(r.python_files[0].status, "syntax-held")
        self.assertEqual(r.status, "unsupported-python-source-held")
        self.assertFalse(r.permits_inert_export)

    def test_source_diagnostics_never_disclose_import_names_in_public_receipt(self):
        b = self.plan((
            "src/private.py",
            "import do_not_disclose_private_package_name\n",
        ))
        r = graph.analyze_python_source_graph(b)
        public = r.to_public()
        self.assertNotIn("do_not_disclose_private_package_name", repr(public))
        self.assertEqual(r.unverified_import_count, 1)
        self.assertIn("requested_name_sha256", repr(public))
        self.assertFalse(public["source_code_executed"])

    def test_graph_provenance_changes_for_different_generated_source(self):
        a = self.plan(("src/a.py", "import sys\n"))
        b = self.plan(("src/a.py", "import os\n"))
        x = graph.analyze_python_source_graph(a)
        y = graph.analyze_python_source_graph(b)
        self.assertNotEqual(x.patch_sha256, y.patch_sha256)
        self.assertNotEqual(x.graph_sha256, y.graph_sha256)
        with self.assertRaises(graph.SourceGraphHold):
            replace(x, graph_sha256="0"*64)

    def test_native_side_effect_text_is_never_run_during_graph_scan(self):
        b = self.plan((
            "src/source.py",
            "import os\n"
            "if True:\n"
            "    os.system('DO_NOT_EXECUTE_SOURCE')\n",
        ))
        with (
            mock.patch("os.system") as system,
            mock.patch("subprocess.Popen") as spawn,
            mock.patch("subprocess.run") as run,
        ):
            result = graph.analyze_python_source_graph(b)
        self.assertTrue(result.permits_inert_export)
        system.assert_not_called()
        spawn.assert_not_called()
        run.assert_not_called()
        self.assertFalse(result.to_public()["python_imports_executed"])


if __name__ == "__main__":
    unittest.main()
