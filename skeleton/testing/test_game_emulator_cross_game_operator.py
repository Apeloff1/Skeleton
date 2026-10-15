"""Operator comparison of private original ROM files through actual DMG CPU."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_rom_cross_game_comparison import SCHEMA, _manifest, run_manifest
from skeleton.jeeves.game_emulator_cross_game_lab import (
    CrossGameComparisonError, verify_cross_game_comparison_receipt,
)
from skeleton.testing.test_game_emulator_cross_game_lab import original_loop


class OperatorSourceGameComparisons(unittest.TestCase):
    def setUp(self):
        self.owned = tempfile.TemporaryDirectory()
        self.addCleanup(self.owned.cleanup)
        self.folder = Path(self.owned.name)
        self.games = []
        for index in range(2):
            filename = self.folder / f"source-original-{index}.gb"
            data = original_loop(index + 1)
            filename.write_bytes(data)
            self.games.append({
                "source_kind": "original_dmg", "core_id": None,
                "target_id": "game_boy", "filename": filename.name,
                "rom_path": str(filename),
                "rom_sha256": hashlib.sha256(data).hexdigest(),
            })

    def _cases(self, cases=None):
        path = self.folder / "source-comparison-manifest.json"
        path.write_text(json.dumps({
            "schema_version": SCHEMA,
            "games": self.games if cases is None else cases,
        }))
        return _manifest(path)

    def test_explicit_source_Rom_files_produce_actual_replay_checked_comparison(self):
        result = run_manifest(
            self._cases(), rights_acknowledged=True,
            programs=(("idle",), ("a",)),
        )
        self.assertEqual(result["selected_games"], 2)
        self.assertEqual(result["actual_replayed_game_programs"], 8)
        self.assertEqual(result["actual_source_action_steps"], 8)
        self.assertTrue(verify_cross_game_comparison_receipt(result)["accepted"])
        self.assertEqual(result["ai_training_gradient_updates"], 0)

    def test_private_operator_rights_and_exact_ROM_SHA_required(self):
        with self.assertRaises(CrossGameComparisonError):
            run_manifest(self._cases(), rights_acknowledged=False)
        incorrect = json.loads(json.dumps(self.games))
        incorrect[1]["rom_sha256"] = "0" * 64
        with self.assertRaises(CrossGameComparisonError):
            run_manifest(self._cases(incorrect), rights_acknowledged=True)

    def test_exact_source_duplicate_case_and_symlink_root_denied(self):
        with self.assertRaises(CrossGameComparisonError):
            self._cases(self.games + [dict(self.games[0])])
        link = self.folder / "source-symlink.gb"
        link.symlink_to(self.folder / self.games[0]["filename"])
        cases = json.loads(json.dumps(self.games))
        cases[0]["rom_path"] = str(link)
        with self.assertRaises(CrossGameComparisonError):
            self._cases(cases)

    def test_programmatic_operator_CLI_cannot_bypass_manifest_path_and_duplicate_limits(self):
        repeated = self.games + [dict(self.games[0])]
        with self.assertRaises(CrossGameComparisonError):
            run_manifest(repeated, rights_acknowledged=True)
        changed = json.loads(json.dumps(self.games))
        changed[0]["rom_path"] = "unsafe-relative-original.gb"
        with self.assertRaises(CrossGameComparisonError):
            run_manifest(changed, rights_acknowledged=True)
        changed = json.loads(json.dumps(self.games))
        changed[0]["run_untrusted_command"] = "python any_script.py"
        with self.assertRaises(CrossGameComparisonError):
            run_manifest(changed, rights_acknowledged=True)

    def test_manifests_cannot_include_hidden_build_options(self):
        payload = json.loads(json.dumps(self.games))
        payload[0]["execute_shell_command"] = "echo never"
        with self.assertRaises(CrossGameComparisonError):
            self._cases(payload)

    def test_program_error_and_unapproved_target_fail_closed(self):
        wrong = json.loads(json.dumps(self.games))
        wrong[0]["target_id"] = "playstation_5"
        with self.assertRaises(CrossGameComparisonError):
            self._cases(wrong)
        with self.assertRaises(CrossGameComparisonError):
            run_manifest(
                self._cases(), rights_acknowledged=True,
                programs=(("idle",), ("not_a_game_button",)),
            )


if __name__ == "__main__":
    unittest.main()
