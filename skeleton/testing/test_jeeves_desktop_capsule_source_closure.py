"""Selected original + reviewed source dependency closure regression proofs.

All source data is inert synthetic UTF-8. AST analysis is pure: no Python
import, project traversal, native GGUF, Git, subprocess or filesystem write.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_capsule_source_closure as audit,
)

A = "a" * 64
B = "b" * 64


def source(path, code, kind="selected-original"):
    data = code.encode("utf-8", "strict")
    return audit.ClosureSource(path, kind, data, sha256(data).hexdigest())


def inspect(*entries):
    return audit.analyze_capsule_source_closure(
        tuple(entries), source_manifest_sha256=A, source_patch_sha256=B,
    )


class OriginalAndReviewedCapsuleGraphTests(unittest.TestCase):
    def test_original_dependency_edges_are_exact_sha_bound(self):
        app = source("src/app.py", "from .dependency import value\nvalue += 1\n", "edit")
        helper = source("src/dependency.py", "value = 42\n")
        graph = inspect(app, helper)
        self.assertEqual(graph.python_count, 2)
        self.assertEqual(graph.status, "linked-selected-python")
        self.assertEqual(graph.linked_original_count, 1)
        self.assertEqual(graph.linked_change_count, 0)
        self.assertEqual(graph.unverified_count, 0)
        edge = graph.import_links[0]
        self.assertEqual(edge.target_path, helper.path)
        self.assertEqual(edge.target_sha256, helper.sha256)
        self.assertEqual(edge.source_sha256, app.sha256)
        self.assertEqual(edge.status, "linked-selected-original")
        self.assertTrue(graph.permits_inert_capsule)
        self.assertFalse(graph.to_public()["all_original_project_imports_known"])
        self.assertFalse(graph.to_public()["runtime_imports_executed"])

    def test_new_reviewed_source_import_has_separate_provenance(self):
        app = source("src/app.py", "import src.newhelper\n", "edit")
        new = source("src/newhelper.py", "value = 5\n", "new")
        graph = inspect(app, new)
        self.assertEqual(graph.linked_original_count, 0)
        self.assertEqual(graph.linked_change_count, 1)
        self.assertEqual(graph.import_links[0].target_path, new.path)
        self.assertEqual(graph.import_links[0].target_kind, "new")

    def test_existing_edit_and_selected_original_link_both_directions(self):
        changed = source("pkg/core.py", "from .config import ready\n", "edit")
        original = source("pkg/config.py", "from .core import status\nready = True\n")
        graph = inspect(changed, original)
        self.assertEqual(graph.linked_original_count, 1)
        self.assertEqual(graph.linked_change_count, 1)
        self.assertEqual(graph.cycles, (("pkg/config.py", "pkg/core.py"),))
        self.assertEqual(graph.status, "linked-selected-python")
        self.assertFalse(graph.to_public()["release_certified"])

    def test_unselected_original_and_external_imports_never_count_as_resolved(self):
        code = "import os\nimport third_party\nfrom pkg.missing import operation\n"
        graph = inspect(source("pkg/app.py", code, "new"))
        self.assertEqual(graph.unverified_count, 3)
        self.assertEqual(graph.status, "partially-unverified-python")
        self.assertEqual(graph.linked_original_count, 0)
        self.assertEqual(graph.linked_change_count, 0)
        self.assertTrue(graph.permits_inert_capsule)
        self.assertFalse(graph.to_public()["stdlib_or_external_dependencies_verified"])

    def test_parent_package_import_can_resolve_selected_init(self):
        files = (
            source("pkg/__init__.py", "CONFIG = 12\n"),
            source("pkg/run.py", "from . import CONFIG\n", "new"),
        )
        report = inspect(*files)
        self.assertEqual(report.linked_original_count, 1)
        self.assertEqual(report.import_links[0].target_path, "pkg/__init__.py")

    def test_nested_package_absolute_module_reference(self):
        report = inspect(
            source("a/b/c.py", "import a.b.lib\n", "new"),
            source("a/b/lib.py", "value = 2\n"),
        )
        self.assertEqual(report.linked_original_count, 1)

    def test_missing_parent_level_is_terminal_hold_for_all_selected_source(self):
        with self.assertRaises(audit.CapsuleClosureHold):
            inspect(source("src/a.py", "from ...outside import thing\n", "edit"))

    def test_invalid_relative_origin_in_original_dependency_is_held_too(self):
        with self.assertRaises(audit.CapsuleClosureHold):
            inspect(
                source("src/new.py", "result = 1\n", "new"),
                source("src/original.py", "from ...unknown import secret\n"),
            )

    def test_selected_original_python_syntax_must_be_real_parseable_ast(self):
        with self.assertRaises(audit.CapsuleClosureHold):
            inspect(
                source("src/new.py", "return_value = 1\n", "new"),
                source("src/existing.py", "def broken(:\n"),
            )

    def test_reviewed_new_source_python_syntax_is_not_executed_to_check(self):
        with (
            mock.patch("subprocess.run") as execution,
            mock.patch("os.system") as system,
        ):
            with self.assertRaises(audit.CapsuleClosureHold):
                inspect(source("src/new.py", "not actually valid python[\n", "new"))
            execution.assert_not_called()
            system.assert_not_called()

    def test_invalid_python_utf8_bytes_do_not_become_a_valid_module(self):
        raw = b"\xff\xfe"
        bad = audit.ClosureSource(
            "src/foreign.py", "selected-original", raw, sha256(raw).hexdigest(),
        )
        with self.assertRaises(audit.CapsuleClosureHold):
            inspect(bad)

    def test_no_python_sources_is_explicitly_not_runtime_qualified(self):
        graph = inspect(source("docs/README.md", "# Original support document\n"))
        self.assertEqual(graph.status, "no-selected-python")
        self.assertEqual(graph.python_count, 0)
        self.assertEqual(graph.ast_nodes, 0)
        self.assertEqual(graph.unverified_count, 0)
        self.assertFalse(graph.to_public()["all_original_project_imports_known"])

    def test_module_identity_does_not_accept_two_runtime_implementations(self):
        with self.assertRaises(audit.CapsuleClosureHold):
            inspect(
                source("pkg/main.py", "x = 1\n"),
                source("pkg/main/__init__.py", "x = 2\n"),
            )

    def test_implementation_can_coexist_with_type_stub(self):
        report = inspect(
            source("pkg/a.pyi", "def run() -> int: ...\n"),
            source("pkg/a.py", "def run():\n    return 1\n"),
            source("pkg/main.py", "import pkg.a\n", "edit"),
        )
        self.assertEqual(report.linked_original_count, 1)
        self.assertEqual(report.import_links[0].target_path, "pkg/a.py")

    def test_reordering_input_cannot_change_closure_hash(self):
        files = (
            source("pkg/z.py", "import pkg.a\n", "new"),
            source("pkg/a.py", "value = 1\n"),
        )
        self.assertEqual(
            inspect(*files).graph_sha256, inspect(*reversed(files)).graph_sha256,
        )

    def test_payload_change_alters_closure_sha_even_without_import_change(self):
        original = source("pkg/a.py", "value = 1\n")
        new = source("pkg/a.py", "value = 2\n")
        self.assertNotEqual(inspect(original).graph_sha256, inspect(new).graph_sha256)

    def test_manifest_or_patch_sha_rebinds_closure_identity(self):
        files = (source("pkg/a.py", "result = 1\n"),)
        first = inspect(*files)
        other_manifest = audit.analyze_capsule_source_closure(
            files, source_manifest_sha256="c"*64, source_patch_sha256=B,
        )
        other_patch = audit.analyze_capsule_source_closure(
            files, source_manifest_sha256=A, source_patch_sha256="d"*64,
        )
        self.assertNotEqual(first.graph_sha256, other_manifest.graph_sha256)
        self.assertNotEqual(first.graph_sha256, other_patch.graph_sha256)

    def test_mutating_original_ast_report_digest_is_rejected(self):
        report = inspect(source("pkg/main.py", "import some_unknown\n"))
        with self.assertRaises(audit.CapsuleClosureHold):
            replace(report, graph_sha256="0"*64)
        with self.assertRaises(audit.CapsuleClosureHold):
            replace(report, status="linked-selected-python")

    def test_duplicate_and_case_conflicting_paths_are_both_held(self):
        for paths in (
            ("src/a.py", "src/a.py"),
            ("src/a.py", "src/A.py"),
        ):
            with self.subTest(paths=paths):
                with self.assertRaises(audit.CapsuleClosureHold):
                    inspect(*(source(p, "value = 1\n") for p in paths))

    def test_untrusted_source_kind_and_path_rejected(self):
        with self.assertRaises(audit.CapsuleClosureHold):
            source("src/a.py", "value = 1\n", "exec")
        with self.assertRaises(audit.CapsuleClosureHold):
            source("src/../bad.py", "value = 1\n")
        with self.assertRaises(audit.CapsuleClosureHold):
            audit.analyze_capsule_source_closure(
                tuple(), source_manifest_sha256=A, source_patch_sha256=B,
            )

    def test_source_sha_mutation_and_byte_count_refused(self):
        item = source("pkg/a.py", "value = 1\n")
        with self.assertRaises(audit.CapsuleClosureHold):
            replace(item, sha256="0"*64)
        with self.assertRaises(audit.CapsuleClosureHold):
            inspect(audit.ClosureSource("pkg/a.py", "new", b"", sha256(b"").hexdigest()))

    def test_total_selected_source_bytes_must_be_bounded(self):
        text = "value = 1234\n" * 4000
        files = tuple(
            source(f"pkg/module{i}.py", text, "new")
            for i in range(50)
        )
        with self.assertRaises(audit.CapsuleClosureHold):
            inspect(*files)

    def test_more_than_seventy_two_files_are_refused(self):
        files = tuple(
            source(f"pkg/m{i}.py", "value = 1\n")
            for i in range(73)
        )
        with self.assertRaises(audit.CapsuleClosureHold):
            inspect(*files)

    def test_more_than_two_hundred_fifty_six_imports_in_one_file_hold(self):
        text = "".join(f"import unresolved_{i}\n" for i in range(257))
        with self.assertRaises(audit.CapsuleClosureHold):
            inspect(source("src/app.py", text, "new"))

    def test_hundreds_of_imports_across_bounded_files_are_finite(self):
        rows = tuple(
            source(f"pkg/m{i}.py", "import mystery\n" * 100, "new")
            for i in range(10)
        )
        result = inspect(*rows)
        self.assertEqual(result.unverified_count, 1000)
        self.assertEqual(result.status, "partially-unverified-python")
        self.assertLess(result.ast_nodes, audit.MAX_TOTAL_NODES)

    def test_non_python_text_is_never_exec_or_imported(self):
        content = "# README\nprint('private document')\n"
        report = inspect(
            source("README.md", content),
            source("pkg/a.py", "ready = True\n", "edit"),
        )
        self.assertEqual(report.python_count, 1)
        self.assertFalse(report.to_public()["runtime_imports_executed"])
        self.assertFalse(report.to_public()["source_code_executed"])


if __name__ == "__main__":
    unittest.main()
