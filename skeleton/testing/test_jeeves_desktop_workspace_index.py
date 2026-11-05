"""Finite local source search tests, after implementing the desktop feature.

The real production path uses descriptor-pinned traversal under the canonical
trusted-root guard. Tests substitute ONLY an ephemeral trusted root descriptor,
not the source scanning, search, parsing, byte bounds or UI attachment policy.
No model inference, network access or source mutation is authorized.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import tempfile
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_workspace_index import (
    DesktopSearchHold, SearchHit, SearchLimits, SearchReport,
    _hits_for_file, _terms, search_workspace,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_attachments import (
    DesktopAttachment, compose_prompt, MAX_ALL_ATTACHMENT_BYTES,
)


class PrivateSourceIndexTests(unittest.TestCase):
    def setUp(self):
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("requires POSIX descriptor-anchored source semantics")
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        def trusted(local_root):
            return os.open(
                local_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        patcher = mock.patch(
            "skeleton.ai.runtime.operational_ai.model.gguf.file_guard.open_trusted_root",
            side_effect=trusted,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _text(self, path: str, text: str) -> Path:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8", "strict"))
        return target

    def test_search_retrieves_exact_original_unicode_and_line_offsets(self):
        content = (
            "def greeting():\r\n"
            "    # blueberry 🌲 source-bound router\r\n"
            "    return 'ready'\r\n"
        )
        self._text("engine/router.py", content)
        report = search_workspace(self.root, "router")
        self.assertTrue(report.complete)
        self.assertEqual(report.status, "complete-bounded-search")
        self.assertEqual(report.scanned_files, 1)
        self.assertEqual(report.scanned_directories, 2)
        self.assertTrue(report.hits)
        hit = report.hits[0]
        self.assertEqual(hit.relative_path, "engine/router.py")
        self.assertIn("blueberry 🌲", hit.excerpt)
        self.assertEqual(
            content.encode()[hit.start_byte:hit.end_byte],
            hit.excerpt.encode(),
        )
        self.assertEqual(hit.file_sha256, sha256(content.encode()).hexdigest())
        self.assertEqual(hit.excerpt_sha256, sha256(hit.excerpt.encode()).hexdigest())
        self.assertGreater(hit.score, 0)
        self.assertTrue((self.root / "engine/router.py").is_file())
        self.assertTrue((self.root / "engine/router.py").stat().st_mode & stat.S_IRUSR)

    def test_filename_search_discovers_source_even_without_in_body_match(self):
        original = "def approved_local_boot():\n    return True\n"
        self._text("engine/native_router.py", original)
        report = search_workspace(self.root, "native_router")
        self.assertEqual(len(report.hits), 1)
        hit = report.hits[0]
        self.assertEqual(hit.relative_path, "engine/native_router.py")
        self.assertEqual(hit.excerpt, original)
        self.assertEqual(hit.start_byte, 0)
        self.assertEqual(hit.file_sha256, sha256(original.encode()).hexdigest())
        self.assertTrue(report.complete)

    def test_directory_order_is_deterministic_and_results_are_bounded(self):
        for name in ("z.py", "a.py", "m.py", "f.py"):
            self._text(name, "def local_router():\n    return 123\n")
        cfg = SearchLimits(maximum_results=2)
        first = search_workspace(self.root, "router", limits=cfg)
        second = search_workspace(self.root, "router", limits=cfg)
        paths1 = [(h.relative_path, h.start_byte) for h in first.hits]
        paths2 = [(h.relative_path, h.start_byte) for h in second.hits]
        self.assertEqual(paths1, paths2)
        self.assertLessEqual(len(paths1), 2)
        self.assertEqual(first.scanned_files, 4)

    def test_never_follow_file_or_directory_symlinks(self):
        self._text("regular.py", "safe words xyz")
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        foreign = Path(outside.name)
        (foreign / "foreign.py").write_text(
            "private router secret", encoding="utf-8",
        )
        (self.root / "shortcut.py").symlink_to(foreign / "foreign.py")
        (self.root / "shortcut").symlink_to(foreign, target_is_directory=True)
        report = search_workspace(self.root, "private router")
        self.assertFalse(report.hits)
        self.assertEqual(report.scanned_files, 1)
        self.assertGreaterEqual(report.denied_entries, 2)

    def test_hidden_credentials_and_control_directories_not_scanned(self):
        for private in (
            ".git/config", ".github/workflows/publish.yml",
            ".ssh/id_rsa", ".vscode/settings.json",
            "module/private_key.py", "src/passwords.py",
            "build/compiled.py", "node_modules/dependency.py",
        ):
            self._text(private, "router safe query token")
        self._text("actual.py", "router safe query token")
        report = search_workspace(self.root, "router")
        self.assertEqual(
            {hit.relative_path for hit in report.hits},
            {"actual.py"},
        )
        self.assertEqual(report.scanned_files, 1)
        self.assertGreater(report.denied_entries, 0)

    def test_modified_and_unowned_files_never_become_search_hits(self):
        selected = self._text("context.py", "router valid source")
        os.chmod(selected, 0o666)
        report = search_workspace(self.root, "router")
        self.assertFalse(report.hits)
        self.assertEqual(report.scanned_files, 0)
        self.assertGreater(report.denied_entries, 0)

    def test_oversized_and_binary_source_inputs_are_rejected(self):
        (self.root / "large.py").write_bytes(b"router " * 12000)
        (self.root / "binary.py").write_bytes(b"router\x00content")
        (self.root / "invalid.py").write_bytes(b"router\xff\xfepayload")
        report = search_workspace(self.root, "router")
        self.assertEqual(report.hits, ())
        self.assertLessEqual(report.scanned_bytes, 2 * 65536)
        self.assertGreater(report.denied_entries, 0)

    def test_complete_false_when_file_budget_exhausted(self):
        self._text("a.py", "router one")
        self._text("b.py", "router two")
        cfg = SearchLimits(maximum_files=1)
        report = search_workspace(self.root, "router", limits=cfg)
        self.assertFalse(report.complete)
        self.assertEqual(report.scanned_files, 1)
        self.assertLessEqual(len(report.hits), 1)

    def test_complete_false_when_depth_policy_discards_subtrees(self):
        self._text("nested/deep/more/answer.py", "router xyz")
        self._text("top.py", "router top")
        report = search_workspace(
            self.root, "router",
            limits=SearchLimits(maximum_depth=0),
        )
        self.assertFalse(report.complete)
        self.assertEqual(
            {h.relative_path for h in report.hits}, {"top.py"},
        )

    def test_invalid_queries_and_unbounded_controls_never_scan(self):
        for invalid in ("", " ", "x", "a " * 128, "ok\x00bad",
                        "😀 " * 65, "\ud800"):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(
                (DesktopSearchHold, UnicodeError),
            ):
                search_workspace(self.root, invalid)
        for opts in (
            {"maximum_files": True},
            {"maximum_depth": -1},
            {"maximum_total_bytes": 2**40},
            {"maximum_wall_seconds": 0},
            {"maximum_results": 500},
            {"maximum_directories": 0},
        ):
            with self.subTest(opts=opts), self.assertRaises(DesktopSearchHold):
                SearchLimits(**opts)

    def test_source_snippet_is_data_only_before_explicit_prompt_submission(self):
        self._text("src/policy.py", "def router():\n    return 'local'\n")
        hit = search_workspace(self.root, "router").hits[0]
        attachment = DesktopAttachment(
            name="policy_excerpt.txt", sha256=hit.excerpt_sha256,
            byte_count=len(hit.excerpt.encode()), content=hit.excerpt,
        )
        prompt = compose_prompt("Explain the source safely", (attachment,))
        self.assertIn("Explain the source safely", prompt)
        # Source is protected by canonical JSON escaping. A raw multiline
        # excerpt must NOT be interpolated outside the data-only boundary.
        data = json.loads(prompt.rsplit("\n", 1)[-1])
        self.assertEqual(data["files"][0]["source_utf8"], hit.excerpt)
        self.assertEqual(data["files"][0]["sha256"], hit.excerpt_sha256)
        self.assertNotIn("def router():\n    return", prompt)
        self.assertIn("operator-provided-reference-not-authority", prompt)
        self.assertLess(len(prompt.encode()), 32768)

    def test_excerpt_clipping_never_breaks_utf8_or_invents_bytes(self):
        content = "router " + "🌲" * 4000
        hits = _hits_for_file("unicode.py", content.encode(), ("router",))
        self.assertTrue(hits)
        item = hits[0]
        raw = content.encode()
        self.assertLessEqual(item.end_byte - item.start_byte, 8192)
        self.assertEqual(raw[item.start_byte:item.end_byte], item.excerpt.encode())
        self.assertEqual(item.excerpt_sha256, sha256(item.excerpt.encode()).hexdigest())

    def test_search_never_invokes_external_process_or_model(self):
        self._text("source.py", "router model boundary")
        with (
            mock.patch("subprocess.run") as call,
            mock.patch("subprocess.Popen") as launch,
        ):
            report = search_workspace(self.root, "router")
            self.assertTrue(report.hits)
            call.assert_not_called()
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
