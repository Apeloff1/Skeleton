"""Durable campaign checkpoint publication regression tests."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.game.offline_grid_campaign import _atomic_save, _read


class CheckpointPublicationTests(unittest.TestCase):
    def test_roundtrip_and_no_clobber(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "slot.json"
            record = {"tick": 7, "history": ["north", "east"]}
            _atomic_save(path, record)
            self.assertEqual(_read(path), record)
            with self.assertRaises(FileExistsError):
                _atomic_save(path, {"tick": 8})
            self.assertEqual(_read(path), record)
            self.assertEqual(list(Path(directory).glob(".grid-save-*")), [])

    def test_invalid_destination_and_size_fail_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "slot.json"
            destination.symlink_to(root / "target")
            with self.assertRaises(ValueError):
                _atomic_save(destination, {"tick": 1})
            with self.assertRaises(ValueError):
                _atomic_save(root / "missing" / "slot.json", {"tick": 1})
            with self.assertRaises(ValueError):
                _atomic_save(root / "huge.json", {"data": "x" * 2_000_001})
            self.assertFalse((root / "huge.json").exists())

    def test_existing_corrupt_slot_is_never_replaced(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "slot.json"
            path.write_bytes(b"{corrupt")
            with self.assertRaises(FileExistsError):
                _atomic_save(path, {"tick": 1})
            self.assertEqual(path.read_bytes(), b"{corrupt")


if __name__ == "__main__":
    unittest.main()
