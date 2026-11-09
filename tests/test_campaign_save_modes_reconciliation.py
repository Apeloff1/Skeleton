"""Reconciliation acceptance for explicit create-only and replace-only campaign saves.

The real CLI is used. No Godot, Windows installer, or release qualification is
claimed by these source-bound tests.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.game.offline_grid_campaign import main
from skeleton.game.gameplay.offline_grid_save_slot import read_slot


def invoke(*args: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = main(list(args))
    return result, stdout.getvalue(), stderr.getvalue()


class CampaignSaveModeTests(unittest.TestCase):
    def test_create_only_does_not_clobber_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = root / "actions.json"
            commands.write_text("[]", encoding="utf-8")
            slot = root / "replay.json"
            code, _, error = invoke("run", "--commands", str(commands),
                                    "--out-save", str(slot))
            self.assertEqual(code, 0, error)
            first = slot.read_bytes()
            code, _, error = invoke("run", "--commands", str(commands),
                                    "--out-save", str(slot))
            self.assertEqual(code, 2)
            self.assertEqual(slot.read_bytes(), first)

    def test_replacement_slot_roundtrip_and_explicit_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = root / "actions.json"
            commands.write_text("[]", encoding="utf-8")
            slot = root / "slot.json"
            code, out, error = invoke("run", "--commands", str(commands),
                                      "--save-slot", str(slot))
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(out)["save"], read_slot(slot))
            first = slot.read_bytes()
            code, out, error = invoke("run", "--commands", str(commands),
                                      "--resume", str(slot), "--save-slot", str(slot))
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(out)["save"], read_slot(slot))
            self.assertEqual(slot.read_bytes(), first)
            self.assertEqual(list(root.glob(".campaign-*.tmp")), [])

    def test_modes_are_disjoint_and_restricted_to_mutating_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = root / "actions.json"
            commands.write_text("[]", encoding="utf-8")
            slot = root / "slot.json"
            code, _, error = invoke("run", "--commands", str(commands),
                                    "--out-save", str(slot), "--save-slot", str(slot))
            self.assertEqual(code, 2)
            self.assertIn("mutually exclusive", error)
            self.assertFalse(slot.exists())
            code, _, error = invoke("inspect", "--save-slot", str(slot))
            self.assertEqual(code, 2)
            self.assertIn("requires play or run", error)

    def test_invalid_save_does_not_publish(self):
        from skeleton.game.gameplay.offline_grid_save_slot import SaveSlotError, write_slot
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "slot.json"
            with self.assertRaises(SaveSlotError):
                write_slot(path, {"bad": float("nan")})
            with self.assertRaises(SaveSlotError):
                write_slot(path, {"bad": object()})
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
