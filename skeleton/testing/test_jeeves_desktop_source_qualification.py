"""Offline Jeeves structural source-gate and exact patch-export qualification.

The parser must never run model output as Python or shell. Source-only
fixtures test validated/unverified/held distinctions, original patch digests,
bad syntax, recursive data, duplicate JSON keys, and the actual private
export refusal path. They do NOT certify runtime correctness, model quality,
device performance, package rights or release.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_patch_bundle as patch,
    desktop_patch_export as export,
    desktop_source_qualification as qualify,
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
)

MIB = 1024 * 1024


def entry(path: str, text: str):
    return patch.PatchEntry(
        kind="new", path=path, original_text="",
        replacement_text=text, original_sha256=None,
        replacement_sha256=sha256(text.encode("utf-8")).hexdigest(),
    )


def original_new(*pairs):
    return json.dumps({
        "schema": workspace.SCHEMA,
        "files": [
            {"path": path, "content": content}
            for path, content in pairs
        ],
    }, ensure_ascii=False)


class StructuralParserTests(unittest.TestCase):
    def test_clean_original_python_reports_actual_ast_without_execution(self):
        dangerous_if_executed = (
            "import os\n"
            "def dangerous():\n"
            "    os.remove('/never-delete-this-file')\n"
            "class Useful:\n"
            "    def build(self): return 1\n"
        )
        original = entry("src/worker.py", dangerous_if_executed)
        with (
            mock.patch("os.remove") as removal,
            mock.patch("subprocess.Popen") as native,
        ):
            result = qualify.qualify_source_file(original)
        removal.assert_not_called()
        native.assert_not_called()
        self.assertEqual(result.language, "python")
        self.assertEqual(result.status, "parse-clean")
        self.assertEqual(result.import_count, 1)
        self.assertEqual(result.top_level_definitions, ("dangerous", "Useful"))
        self.assertGreater(result.syntax_nodes, 8)
        self.assertEqual(len(result.parser_fingerprint), 64)
        self.assertFalse(result.to_public()["executed_source_code"])
        self.assertNotIn("never-delete", repr(result.to_public()))

    def test_python_missing_newline_and_unicode_are_legal(self):
        for text in (
            "x = 1", "x = '🌳'\n",
            "from __future__ import annotations\n",
            "@staticmethod\ndef f(): return 1\n",
            "def typed(a: int) -> dict[str,int]:\n    return {'x': a}\n",
        ):
            with self.subTest(text=text), mock.patch("subprocess.run") as shell:
                result = qualify.qualify_source_file(entry("ok.py", text))
                self.assertEqual(result.status, "parse-clean")
                shell.assert_not_called()

    def test_invalid_python_is_not_reported_as_clean(self):
        for text in (
            "def broken(:\n    return 1\n",
            "x = (\n",
            "if True:\nnot_indented = 1\n",
            "raise\n@\n",
        ):
            with self.subTest(text=text):
                result = qualify.qualify_source_file(entry("invalid.py", text))
                self.assertEqual(result.status, "syntax-held")
                self.assertEqual(result.issues[0].code, "python-syntax")
                self.assertFalse(result.to_public()["executed_source_code"])
                self.assertIsNone(result.parser_fingerprint)

    def test_json_strict_duplicate_nan_and_invalid_shape_are_held(self):
        for raw, code in (
            ('{"a":1,"a":2}', "json-duplicate-key"),
            ('{"weight":NaN}', "json-nonfinite"),
            ('{"broken":', "json-syntax"),
            ("[1,2,]", "json-syntax"),
        ):
            with self.subTest(raw=raw):
                report = qualify.qualify_source_file(entry("state.json", raw))
                self.assertEqual(report.status, "syntax-held")
                self.assertEqual(report.issues[0].code, code)
        result = qualify.qualify_source_file(
            entry("state.json", '{"id":"jeeves","active":true,"n":14}')
        )
        self.assertEqual(result.status, "parse-clean")
        self.assertEqual(len(result.parser_fingerprint), 64)

    def test_toml_actual_stdlib_parser_catches_duplicate_keys(self):
        cases = (
            ("[model]\nthreads = 4\n", "parse-clean"),
            ("[model]\nthreads=4\nthreads=5\n", "syntax-held"),
            ("[model\nthreads = 4\n", "syntax-held"),
            ("name = 'local jeeves'\n", "parse-clean"),
        )
        for data, expected in cases:
            with self.subTest(data=data):
                result = qualify.qualify_source_file(entry("settings.toml", data))
                self.assertEqual(result.status, expected)
                self.assertEqual(result.language, "toml")

    def test_unsupported_source_types_explicitly_unverified_not_passed(self):
        for path, content in (
            ("frontend/app.tsx", "export const App = () => null;\n"),
            ("backend/model.rs", "fn main() {}\n"),
            ("README.md", "# Local only\n"),
            ("source.yaml", "port: 8080\n"),
            ("migration.sql", "CREATE TABLE item(id INTEGER);\n"),
            ("script.sh", "echo never-executed\n"),
        ):
            with self.subTest(path=path), mock.patch("os.system") as run:
                result = qualify.qualify_source_file(entry(path, content))
                self.assertEqual(result.status, "unverified")
                self.assertEqual(result.language, "unverified-format")
                self.assertIsNone(result.parser_fingerprint)
                run.assert_not_called()

    def test_parser_diagnostics_do_not_copy_private_source_text(self):
        secret = "    token = 'PRIVATE_SOURCE_CREDENTIAL_DO_NOT_PRINT'\n"
        source = entry("secret_test.py", "def f(:\n" + secret)
        outcome = qualify.qualify_source_file(source)
        self.assertEqual(outcome.status, "syntax-held")
        public = outcome.to_public()
        self.assertNotIn("PRIVATE_SOURCE_CREDENTIAL", repr(public))
        self.assertIn("python-syntax", repr(public))
        self.assertFalse(public["executed_source_code"])

    def test_unapproved_data_types_cannot_create_fake_results(self):
        with self.assertRaises(qualify.StaticSourceHold):
            qualify.qualify_source_file({"path": "new.py"})
        with self.assertRaises(qualify.StaticSourceHold):
            qualify.SyntaxIssue(
                code="release-approved",
                relative_path="worker.py",
                replacement_sha256="a"*64,
                line=1, column=2,
            )
        with self.assertRaises(qualify.StaticSourceHold):
            qualify.FileQualification(
                path="worker.py", replacement_sha256="a"*64,
                language="python", status="parse-clean",
                bytes_checked=42,
                parser_fingerprint=None, syntax_nodes=None,
                top_level_definitions=(), import_count=0,
                issues=(qualify.SyntaxIssue(
                    code="python-syntax", relative_path="worker.py",
                    replacement_sha256="a"*64,
                    line=1, column=1,
                ),),
            )


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Actual source descriptor fixtures require POSIX/WSL2",
)
class CompletePatchQualificationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="jeeves-ast-gate-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "project"
        self.root.mkdir(mode=0o700)
        (self.root / "pkg").mkdir(mode=0o700)
        self.private = Path(tmp.name) / "private"
        self.private.mkdir(mode=0o700)
        def source_fd(value):
            return os.open(value, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for module in (workspace, edits, patch):
            guard = mock.patch.object(
                module, "_open_root", side_effect=source_fd,
            )
            guard.start()
            self.addCleanup(guard.stop)

    def _plan(self, *sources):
        return patch.review_patch_bundle(
            self.root, new_files=original_new(*sources),
        )

    def _export(self, plan):
        return export.export_reviewed_patch(
            plan, self.private / "original-sources.patch",
            expected_manifest_sha256=plan.manifest_sha256,
            expected_patch_sha256=plan.patch_sha256,
            approve_export=True,
        )

    def test_exact_mixed_languages_report_binds_full_patch_digest(self):
        plan = self._plan(
            ("pkg/lib.py", "def run(): return 1\n"),
            ("config.json", '{"name":"local","enabled":true}'),
            ("settings.toml", "name = 'offline'\n"),
            ("app.ts", "export const value = 1;\n"),
        )
        report = qualify.qualify_patch_sources(plan)
        public = report.to_public()
        self.assertEqual(public["source_manifest_sha256"], plan.manifest_sha256)
        self.assertEqual(public["source_patch_sha256"], plan.patch_sha256)
        self.assertEqual(public["file_count"], 4)
        self.assertEqual(public["parse_clean_count"], 3)
        self.assertEqual(public["unverified_count"], 1)
        self.assertEqual(public["syntax_held_count"], 0)
        self.assertTrue(report.permits_inert_export)
        self.assertFalse(public["all_languages_parsed"])
        self.assertEqual(report.status, "mixed-unverified")
        self.assertFalse(public["source_code_executed"])
        self.assertFalse(public["model_executed_from_patch"])
        self.assertFalse(public["release_certified"])

    def test_actual_private_export_blocks_bad_generated_python_before_any_write(self):
        plan = self._plan(
            ("service.py", "def x(:\n    return 1\n"),
            ("README.md", "# a real project\n"),
        )
        report = qualify.qualify_patch_sources(plan)
        self.assertFalse(report.permits_inert_export)
        self.assertEqual(report.status, "syntax-held")
        with self.assertRaises(export.PatchExportHold):
            self._export(plan)
        self.assertFalse((self.private / "original-sources.patch").exists())

    def test_actual_private_export_blocks_duplicate_json_and_invalid_toml(self):
        for name, text in (
            ("bad.json", '{"id":1,"id":2}'),
            ("bad.toml", "name = 'x'\nname = 'y'\n"),
        ):
            with self.subTest(name=name):
                plan = self._plan((name, text))
                with self.assertRaises(export.PatchExportHold):
                    self._export(plan)
                self.assertFalse((self.private / "original-sources.patch").exists())

    def test_python_valid_and_unknown_ts_mixed_receipt_explicitly_unverified(self):
        plan = self._plan(
            ("thing.py", "def build(): return 'ready'\n"),
            ("thing.ts", "export const x = 2;\n"),
        )
        result = self._export(plan)
        self.assertEqual(result["static_source_status"], "mixed-unverified")
        self.assertEqual(result["parse_clean_count"], 1)
        self.assertEqual(result["unverified_source_count"], 1)
        self.assertFalse(result["source_code_executed"])
        self.assertEqual(
            sha256((self.private / "original-sources.patch").read_bytes()).hexdigest(),
            plan.patch_sha256,
        )
        self.assertFalse((self.root / "thing.py").exists())
        self.assertFalse((self.root / "thing.ts").exists())

    def test_all_supported_source_files_have_actual_parse_clean_status(self):
        plan = self._plan(
            ("logic.py", "def value(): return 1\n"),
            ("data.json", '{"nested":{"ok":true}}'),
            ("settings.toml", "[app]\nname='local'\n"),
        )
        report = qualify.require_parseable_patch(plan)
        self.assertEqual(report.status, "parse-clean")
        self.assertTrue(report.to_public()["all_languages_parsed"])
        result = self._export(plan)
        self.assertEqual(result["static_source_status"], "parse-clean")
        self.assertEqual(result["unverified_source_count"], 0)
        self.assertEqual(result["parse_clean_count"], 3)

    def test_parser_rejection_never_mutates_original_existing_file(self):
        original = self.root / "existing.py"
        original.write_text("value = 1\n", encoding="utf-8")
        plan = patch.review_patch_bundle(
            self.root, existing_edits=json.dumps({
                "schema": edits.SCHEMA,
                "files": [{
                    "path": "existing.py",
                    "expected_sha256": sha256(b"value = 1\n").hexdigest(),
                    "replacement": "if True:\nmissing_indent=1\n",
                }],
            }),
        )
        report = qualify.qualify_patch_sources(plan)
        self.assertEqual(report.status, "syntax-held")
        with self.assertRaises(export.PatchExportHold):
            self._export(plan)
        self.assertEqual(original.read_text(), "value = 1\n")
        self.assertFalse((self.private / "original-sources.patch").exists())


if __name__ == "__main__":
    unittest.main()
