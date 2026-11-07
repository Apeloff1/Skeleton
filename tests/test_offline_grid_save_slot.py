"""Real filesystem durability and hostile slot tests (no simulated engine claim)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from skeleton.game.gameplay.offline_grid_save_slot import (
    MAX_SAVE_BYTES, SaveSlotError, read_slot, write_slot,
)


class SaveSlotTests(unittest.TestCase):
    def test_restart_round_trip_and_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "save.json"
            write_slot(slot, {"tick": 3, "inventory": ["lantern"]})
            self.assertEqual(read_slot(slot)["tick"], 3)
            write_slot(slot, {"tick": 9, "inventory": []})
            self.assertEqual(read_slot(slot), {"tick": 9, "inventory": []})
            self.assertEqual(slot.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(tmp).glob(".campaign-*")), [])

    def test_reject_symlink_slot_without_touching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "private"
            target.write_text("protected", encoding="utf-8")
            (root / "save.json").symlink_to(target)
            with self.assertRaises(SaveSlotError):
                write_slot(root / "save.json", {"tick": 1})
            with self.assertRaises(SaveSlotError):
                read_slot(root / "save.json")
            self.assertEqual(target.read_text(encoding="utf-8"), "protected")

    def test_reject_hardlink_and_oversized_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slot = root / "save.json"
            slot.write_text("{}", encoding="utf-8")
            os.link(slot, root / "linked")
            with self.assertRaises(SaveSlotError):
                write_slot(slot, {})
            slot.unlink()
            with self.assertRaises(SaveSlotError):
                write_slot(slot, {"huge": "x" * MAX_SAVE_BYTES})
            self.assertFalse(slot.exists())

    def test_corrupt_slot_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "save.json"
            slot.write_text("{corrupt", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                read_slot(slot)

    def test_real_cli_play_quit_and_run_save_slot(self):
        """Exercise the real CLI entrypoint, not a simulated save writer."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slot = root / "slot.json"
            process = subprocess.run(
                [sys.executable, "-m", "scripts.game.offline_grid_campaign",
                 "play", "--save-slot", str(slot)],
                input="quit\n", text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertTrue(slot.is_file())
            saved = read_slot(slot)
            self.assertIsInstance(saved, dict)
            self.assertEqual(json.loads(process.stdout.splitlines()[-1])["save"], saved)
            commands = root / "commands.json"
            commands.write_text("[]", encoding="utf-8")
            second = subprocess.run(
                [sys.executable, "-m", "scripts.game.offline_grid_campaign",
                 "run", "--commands", str(commands), "--resume", str(slot),
                 "--save-slot", str(slot)],
                text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(second.stdout)["save"], read_slot(slot))

    def test_parent_symlink_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "real").mkdir()
            (root / "alias").symlink_to(root / "real", target_is_directory=True)
            with self.assertRaises(SaveSlotError):
                write_slot(root / "alias" / "save.json", {"tick": 1})


if __name__ == "__main__":
    unittest.main()
