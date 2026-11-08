"""Offline, deterministic custody regressions; no physical Godot run is implied."""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from skeleton.godot_export.artifact_custody import (
    MAX_EXPORT_BYTES, ExportCustodyError, export_and_inspect, inspect_export,
)
from skeleton.godot_export.runner import RunResult


def fake_pe() -> bytes:
    data = bytearray(256)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 128)
    data[128:132] = b"PE\x00\x00"
    return bytes(data)


def fake_elf() -> bytes:
    return b"\x7fELF\x02\x01\x01" + bytes(128)


class SyntheticGodotRunner:
    def __init__(self, data: bytes, code: int = 0):
        self.data, self.code, self.calls = data, code, 0

    def export(self, project, preset, out, timeout=600):
        self.calls += 1
        if self.code == 0:
            Path(out).write_bytes(self.data)
        return RunResult(self.code, "", ("godot",))


class ExportArtifactCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="godot-artifact-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.output = self.root / "game.exe"

    def inspected(self, output=None, root=None, platform="windows"):
        return inspect_export(output or self.output, platform,
                              root=root or self.root, result=RunResult(0, ""))

    def test_real_export_process_boundary_and_cold_restart(self):
        data = fake_pe()
        runner = SyntheticGodotRunner(data)
        result = export_and_inspect(runner, self.project, "Windows Desktop",
                                    self.output, "windows")
        self.assertEqual(runner.calls, 1)
        self.assertEqual(result.size, len(data))
        self.assertEqual(result.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(result.godot_exit_code, 0)
        self.assertEqual(self.inspected().sha256, result.sha256)
        self.assertEqual(self.output.stat().st_nlink, 1)
        self.assertFalse(list(self.root.glob(".godot-export-*")))

    def test_linux_signature_and_digest(self):
        path = self.root / "game.x86_64"
        result = export_and_inspect(SyntheticGodotRunner(fake_elf()),
                                    self.project, "Linux Desktop", path, "linux")
        self.assertEqual(result.sha256, hashlib.sha256(fake_elf()).hexdigest())

    def test_invalid_pe_header_never_emits_evidence(self):
        runner = SyntheticGodotRunner(b"MZ" + bytes(256))
        with self.assertRaises(ExportCustodyError):
            export_and_inspect(runner, self.project, "Windows", self.output, "windows")
        self.assertFalse(self.output.exists())
        self.assertEqual(runner.calls, 1)

    def test_literal_backslash_elf_is_not_an_executable_header(self):
        path = self.root / "bad.x86_64"
        with self.assertRaisesRegex(ExportCustodyError, "invalid-elf-signature"):
            export_and_inspect(SyntheticGodotRunner(b"\\x7fELF" + bytes(128)),
                               self.project, "Linux", path, "linux")

    def test_failed_exit_never_publishes(self):
        with self.assertRaisesRegex(ExportCustodyError, "godot-export-failed"):
            export_and_inspect(SyntheticGodotRunner(fake_pe(), code=127),
                               self.project, "Windows", self.output, "windows")
        self.assertFalse(self.output.exists())

    def test_no_clobber_existing_regular_or_symlink(self):
        self.output.write_bytes(b"valuable-previous-export")
        runner = SyntheticGodotRunner(fake_pe())
        with self.assertRaisesRegex(ExportCustodyError, "output-already-exists"):
            export_and_inspect(runner, self.project, "Windows", self.output, "windows")
        self.assertEqual(runner.calls, 0)
        self.assertEqual(self.output.read_bytes(), b"valuable-previous-export")
        self.output.unlink()
        target = self.root / "target"
        target.write_bytes(b"private")
        try:
            self.output.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ExportCustodyError):
            export_and_inspect(runner, self.project, "Windows", self.output, "windows")
        self.assertEqual(target.read_bytes(), b"private")

    def test_symlink_and_foreign_directory_rejected(self):
        self.output.write_bytes(fake_pe())
        with self.assertRaisesRegex(ExportCustodyError, "artifact-outside-export-root"):
            self.inspected(root=self.project)
        target = self.root / "target"
        target.write_bytes(fake_pe())
        self.output.unlink()
        try:
            self.output.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ExportCustodyError):
            self.inspected()

    def test_hardlink_not_admitted(self):
        self.output.write_bytes(fake_pe())
        alias = self.root / "alias"
        try:
            alias.hardlink_to(self.output)
        except OSError:
            self.skipTest("hardlinks unavailable")
        with self.assertRaisesRegex(ExportCustodyError, "artifact-not-single-regular-file"):
            self.inspected()

    def test_empty_oversized_and_platform_invalid(self):
        self.output.touch()
        with self.assertRaisesRegex(ExportCustodyError, "artifact-size-invalid"):
            self.inspected()
        self.output.unlink()
        with self.output.open("wb") as stream:
            try:
                stream.truncate(MAX_EXPORT_BYTES + 1)
            except OSError:
                self.skipTest("sparse files unavailable")
        with self.assertRaisesRegex(ExportCustodyError, "artifact-size-invalid"):
            self.inspected()
        with self.assertRaisesRegex(ExportCustodyError, "unsupported-platform"):
            self.inspected(platform="console")

    def test_admission_before_native_process(self):
        runner = SyntheticGodotRunner(fake_pe())
        for preset, timeout in (("", 600), (" Windows ", 600), ("Windows", 0),
                                ("Windows", True), ("Windows", 5000)):
            with self.subTest(preset=preset, timeout=timeout):
                with self.assertRaises(ExportCustodyError):
                    export_and_inspect(runner, self.project, preset,
                                       self.output, "windows", timeout=timeout)
        self.assertEqual(runner.calls, 0)

    def test_atomic_publication_failure_leaves_no_output(self):
        runner = SyntheticGodotRunner(fake_pe())
        with mock.patch("skeleton.godot_export.artifact_custody.os.link",
                        side_effect=FileExistsError("simulated concurrent publisher")):
            with self.assertRaisesRegex(ExportCustodyError,
                                        "atomic-publication-unavailable-or-colliding"):
                export_and_inspect(runner, self.project, "Windows",
                                   self.output, "windows")
        self.assertEqual(runner.calls, 1)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".godot-export-*")))

    def test_sidecar_exports_are_not_silently_discarded(self):
        class SidecarRunner(SyntheticGodotRunner):
            def export(self, project, preset, out, timeout=600):
                result = super().export(project, preset, out, timeout=timeout)
                Path(out).with_suffix(".pck").write_bytes(b"separate-unverified-runtime")
                return result

        runner = SidecarRunner(fake_pe())
        with self.assertRaisesRegex(ExportCustodyError,
                                    "export-has-unqualified-sidecars"):
            export_and_inspect(runner, self.project, "Windows",
                               self.output, "windows")
        self.assertEqual(runner.calls, 1)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".godot-export-*")))

    def test_replacement_during_hash_fails_closed(self):
        self.output.write_bytes(fake_pe())
        # The descriptor has already been opened when header verification
        # runs. Replace the path then; the final dir-entry identity check
        # must reject the stale opened inode rather than trusting its bytes.
        from skeleton.godot_export import artifact_custody as custody
        original = custody._validate_image
        moved = self.root / "moved"
        def replace_after_open(stream, platform, size):
            original(stream, platform, size)
            self.output.rename(moved)
            self.output.write_bytes(fake_pe())
        with mock.patch.object(custody, "_validate_image",
                               side_effect=replace_after_open):
            with self.assertRaisesRegex(ExportCustodyError,
                                        "artifact-changed-during-verification"):
                self.inspected()


if __name__ == "__main__":
    unittest.main()
