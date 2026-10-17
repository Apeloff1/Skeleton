"""Native build boundary: real toolchain calls only under explicit local opt-in."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import subprocess

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.studio_build_qualification import (
    NativeBuildQualificationError, _header, adapter_catalog, qualify_native_build,
)


def make_project(root: Path, target: str) -> Path:
    project = root / "source"
    project.mkdir()
    entry = "main.s" if target == "nintendo_famicom" else "main.asm"
    (project / entry).write_text("; independent original source\n")
    (project / "manifest.json").write_text(
        json.dumps({"target": target, "project_id": "original-test"}) + "\n"
    )
    if target == "nintendo_famicom":
        (project / "nes.cfg").write_text("MEMORY {}\n")
    files = {
        name: sha256((project / name).read_bytes()).hexdigest()
        for name in (entry, "manifest.json", *(("nes.cfg",) if target == "nintendo_famicom" else ()))
    }
    body = {
        "schema": "skeleton.game_builder.source_attestation.v1",
        "target": target, "project_id": "original-test",
        "world_digest": "0" * 64,
        "reference_replay_digest": "0" * 64,
        "input_files": files, "source_content_digest": "0" * 64,
        "studio_art_pack_digest": None,
        "rights_independently_verified": False, "binary_compiled": False,
    }
    (project / "source_attestation.json").write_text(json.dumps({
        **body, "attestation_digest": canonical_digest(body),
    }))
    return project


def valid_nes() -> bytes:
    return b"NES\x1a" + bytes([1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]) + bytes(16384 + 8192)


def valid_gb(cgb: bool = False) -> bytes:
    content = bytearray(32768)
    content[0x143] = 0xC0 if cgb else 0
    checksum = 0
    for byte in content[0x134:0x14D]:
        checksum = (checksum - byte - 1) & 255
    content[0x14D] = checksum
    return bytes(content)


class NativeBuildQualificationTests(unittest.TestCase):
    def test_catalog_and_missing_compiler_is_explicit_nonexecution(self):
        self.assertEqual(len(adapter_catalog()["executable_adapters"]), 3)
        with TemporaryDirectory() as temp:
            project = make_project(Path(temp), "nintendo_famicom")
            with patch("skeleton.ai.game_builder.studio_build_qualification.shutil.which",
                       return_value=None):
                result = qualify_native_build(
                    project, "nintendo_famicom", authorized=True
                )
            self.assertFalse(result.toolchain_available)
            self.assertFalse(result.tools_invoked)
            self.assertFalse(result.binary_built)
            self.assertIn("toolchain_missing", result.blocker)
            self.assertEqual(result.as_receipt()["receipt_digest"], result.receipt_digest)

    def test_preflight_does_not_invoke_existing_toolchain(self):
        with TemporaryDirectory() as temp:
            project = make_project(Path(temp), "nintendo_game_boy")
            with patch("skeleton.ai.game_builder.studio_build_qualification.shutil.which",
                       return_value="/opt/trusted/rgbds"), patch(
                "skeleton.ai.game_builder.studio_build_qualification.subprocess.run"
            ) as run:
                result = qualify_native_build(project, "nintendo_game_boy",
                                              authorized=True)
            run.assert_not_called()
            self.assertTrue(result.toolchain_available)
            self.assertFalse(result.binary_built)
            self.assertEqual(result.blocker, "execution_not_authorized")

    def test_each_allowlisted_source_is_compiled_with_explicit_arguments(self):
        cases = (
            ("nintendo_game_boy", "game.gb", valid_gb()),
            ("nintendo_game_boy_color", "game.gbc", valid_gb(True)),
            ("nintendo_famicom", "game.nes", valid_nes()),
        )
        for target, romname, blob in cases:
            with self.subTest(target=target), TemporaryDirectory() as temp:
                root = Path(temp)
                project = make_project(root, target)
                destination = root / "verified.rom"
                calls = []

                def fake_run(args, *, cwd, shell, timeout, stdout, stderr, check, env):
                    self.assertFalse(shell)
                    self.assertTrue(hasattr(stdout, "write"))
                    self.assertEqual(stderr, subprocess.STDOUT)
                    self.assertFalse(check)
                    self.assertIn(timeout, range(1, 121))
                    self.assertTrue(str(args[0]).startswith("/opt/"))
                    calls.append(args)
                    if args[0].endswith("ld65") or args[0].endswith("rgbfix"):
                        (Path(cwd) / romname).write_bytes(blob)
                    return subprocess.CompletedProcess(args, 0, b"ok", b"")

                def fake_which(name):
                    return "/opt/" + name

                with patch("skeleton.ai.game_builder.studio_build_qualification.shutil.which",
                           side_effect=fake_which), patch(
                    "skeleton.ai.game_builder.studio_build_qualification.subprocess.run",
                    side_effect=fake_run
                ):
                    result = qualify_native_build(
                        project, target, authorized=True, execute=True,
                        output=destination,
                    )
                self.assertTrue(result.toolchain_available)
                self.assertTrue(result.tools_invoked)
                self.assertTrue(result.binary_built)
                self.assertTrue(result.rom_header_verified)
                self.assertEqual(result.binary_sha256, sha256(blob).hexdigest())
                self.assertEqual(destination.read_bytes(), blob)
                self.assertEqual(len(calls), 2 if target == "nintendo_famicom" else 3)
                receipt = result.as_receipt()
                self.assertFalse(receipt["emulator_playthrough_verified"])
                self.assertFalse(receipt["physical_hardware_verified"])
                self.assertFalse(receipt["publication_approved"])

    def test_failed_assembler_does_not_publish_rom(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = make_project(root, "nintendo_game_boy")
            destination = root / "game.gb"
            with patch("skeleton.ai.game_builder.studio_build_qualification.shutil.which",
                       return_value="/opt/rgbasm"), patch(
                "skeleton.ai.game_builder.studio_build_qualification.subprocess.run",
                return_value=subprocess.CompletedProcess(["rgbasm"], 2, b"", b"invalid")
            ):
                result = qualify_native_build(
                    project, "nintendo_game_boy", authorized=True,
                    execute=True, output=destination,
                )
            self.assertFalse(result.binary_built)
            self.assertEqual(result.blocker, "toolchain_exit_code:2")
            self.assertFalse(destination.exists())

    def test_corrupt_cartridge_and_wrong_rights_target_are_rejected(self):
        for family, data in (("nes", b"BAD"), ("gb", bytes(32768)),
                             ("gbc", valid_gb(False))):
            with self.subTest(family=family), self.assertRaises(NativeBuildQualificationError):
                _header(family, data)
        with TemporaryDirectory() as temp:
            folder = make_project(Path(temp), "nintendo_game_boy")
            with self.assertRaises(NativeBuildQualificationError):
                qualify_native_build(folder, "nintendo_famicom", authorized=True)
            with self.assertRaises(PermissionError):
                qualify_native_build(folder, "nintendo_game_boy", authorized=False)
            with self.assertRaises(NativeBuildQualificationError):
                qualify_native_build(folder, "nintendo_switch", authorized=True)
            with self.assertRaises(NativeBuildQualificationError):
                qualify_native_build(folder, "nintendo_game_boy",
                                     authorized=True, timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
