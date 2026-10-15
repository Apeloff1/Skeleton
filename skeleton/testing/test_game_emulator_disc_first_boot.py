"""Original locally owned media descriptors and native disc first-boot custody.

Synthetic local CUE/BIN only. Tests source streaming, disc dependency and
operator rights gates without proprietary BIOS/media or claiming core boots.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_game_emulator_disc_first_boot import (
    SCHEMA, DiscAcceptanceError, _manifest, _media_bundle, _run_case,
    run_matrix,
)
from skeleton.jeeves.game_emulator_catalog import GameContentBundle
from skeleton.testing.test_game_emulator_first_boot_audit import StubNativeHost


def digest(data):
    return hashlib.sha256(data).hexdigest()


class OriginalStreamedDiscAcceptance(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory()
        self.addCleanup(self.private.cleanup)
        folder = Path(self.private.name)
        self.cue = folder / "synthetic-original.cue"
        self.bin = folder / "synthetic-original.bin"
        self.cue.write_bytes(
            b'FILE "synthetic-original.bin" BINARY\n'
            b'  TRACK 01 MODE1/2352\n'
            b'  INDEX 01 00:00:00\n'
        )
        self.bin.write_bytes(b"Original authored synthetic sector" * 100)
        self.case = {
            "core_id": "mednafen_saturn",
            "target_id": "sega_saturn",
            "entrypoint": self.cue.name,
            "files": [
                {"name": self.cue.name, "path": str(self.cue),
                 "sha256": digest(self.cue.read_bytes()),
                 "size_bytes": self.cue.stat().st_size},
                {"name": self.bin.name, "path": str(self.bin),
                 "sha256": digest(self.bin.read_bytes()),
                 "size_bytes": self.bin.stat().st_size},
            ],
        }

    def _manifest_file(self, cases):
        target = Path(self.private.name) / "media-manifest.json"
        target.write_text(json.dumps({"schema_version": SCHEMA, "cases": cases}))
        return target

    def test_real_governed_content_bundle_streams_exact_local_cue_and_bin(self):
        cases = _manifest(self._manifest_file([self.case]))
        bundle, reader, hashes = _media_bundle(cases[0])
        self.assertIsInstance(bundle, GameContentBundle)
        self.assertEqual(set(hashes), {self.cue.name, self.bin.name})
        with tempfile.TemporaryDirectory() as output:
            created = bundle.materialize_private(output, reader=reader)
            self.assertEqual(created.read_bytes(), self.cue.read_bytes())
            self.assertEqual((Path(output) / self.bin.name).read_bytes(),
                             self.bin.read_bytes())

    def test_source_changed_after_admission_refuses_before_native_core(self):
        cases = _manifest(self._manifest_file([self.case]))
        self.bin.write_bytes(self.bin.read_bytes() + b"different content")
        with self.assertRaises(DiscAcceptanceError):
            _media_bundle(cases[0])

    def test_stream_sha_change_under_identical_file_size_is_detected(self):
        cases = _manifest(self._manifest_file([self.case]))
        bundle, reader, hashes = _media_bundle(cases[0])
        self.bin.write_bytes(b"X" + self.bin.read_bytes()[1:])
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaises(ValueError):
                bundle.materialize_private(output, reader=reader)

    def test_missing_playlist_and_wrong_descriptor_name_are_rejected(self):
        first = json.loads(json.dumps(self.case))
        first["entrypoint"] = "missing.cue"
        with self.assertRaises(DiscAcceptanceError):
            _manifest(self._manifest_file([first]))
        second = json.loads(json.dumps(self.case))
        second["files"].pop()
        with self.assertRaises(ValueError):
            _media_bundle(second)

    def test_reject_symlinks_and_duplicate_normalized_paths(self):
        alias = Path(self.private.name) / "original-alias.bin"
        alias.symlink_to(self.bin)
        linked = json.loads(json.dumps(self.case))
        linked["files"][1]["path"] = str(alias)
        with self.assertRaises(DiscAcceptanceError):
            _manifest(self._manifest_file([linked]))
        repeated = json.loads(json.dumps(self.case))
        repeated["files"].append(dict(repeated["files"][1]))
        with self.assertRaises(DiscAcceptanceError):
            _manifest(self._manifest_file([repeated]))

    def test_explicit_legal_rights_required_for_programmatic_discs(self):
        with self.assertRaises(DiscAcceptanceError):
            run_matrix([self.case], rights_acknowledged=False)

    def test_programmatic_disc_audit_cannot_bypass_manifest_file_limit(self):
        illegal = json.loads(json.dumps(self.case))
        illegal["files"] = [
            {
                "name": f"original-media-{i:02d}.bin",
                "path": str(self.bin),
                "sha256": digest(self.bin.read_bytes()),
                "size_bytes": self.bin.stat().st_size,
            }
            for i in range(17)
        ]
        illegal["entrypoint"] = illegal["files"][0]["name"]
        with self.assertRaises(DiscAcceptanceError):
            run_matrix([illegal], rights_acknowledged=True)

    def test_programmatic_disc_audit_requires_exact_absolute_source_paths(self):
        illegal = json.loads(json.dumps(self.case))
        illegal["files"][1]["path"] = "relative-original.bin"
        with self.assertRaises(DiscAcceptanceError):
            run_matrix([illegal], rights_acknowledged=True)

    def test_native_disc_rewind_receipt_requires_real_host_state(self):
        host = StubNativeHost()
        host.core.firmware_digest = "a" * 64
        with patch(
            "scripts.audit_game_emulator_disc_first_boot.create_emulator_environment",
            return_value=host,
        ):
            row = _run_case(self.case, "b" * 64, 5)
        self.assertTrue(row["actual_native_multi_file_disc_boot"])
        self.assertTrue(row["actual_savestate_replay_passed"])
        self.assertEqual(
            row["before_rewind_snapshot_digest"],
            row["after_rewind_snapshot_digest"],
        )
        self.assertFalse(row["independent_disc_hardware_accuracy_certified"])

    def test_native_replay_divergence_does_not_count_as_disc_readiness(self):
        host = StubNativeHost(diverge=True)
        host.core.firmware_digest = "a" * 64
        with patch(
            "scripts.audit_game_emulator_disc_first_boot.create_emulator_environment",
            return_value=host,
        ):
            with self.assertRaises(DiscAcceptanceError):
                _run_case(self.case, "b" * 64, 5)


if __name__ == "__main__":
    unittest.main()
