"""Post-merge campaign-slot ancestor path custody under symlinks and races.

POSIX only: all publication remains relative to descriptor-anchored parents.
No filesystem write to an attacker-swapped ancestor or forged save is allowed.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.game.gameplay.offline_grid_save_slot import (
    SaveSlotError, read_slot, write_slot,
)


SUPPORTS_GUARDED_DIR_FD = (
    os.name == "posix"
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "supports_dir_fd")
    and all(fn in os.supports_dir_fd
            for fn in (os.open, os.stat, os.rename, os.unlink))
)


@unittest.skipUnless(SUPPORTS_GUARDED_DIR_FD, "requires no-follow descriptor paths")
class SaveSlotAncestorCustodyTests(unittest.TestCase):
    def test_symlinked_intermediate_parent_fails_closed_for_read_and_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            (outside / "nested").mkdir()
            alias = root / "alias"
            alias.symlink_to(outside, target_is_directory=True)
            slot = alias / "nested" / "slot.json"
            with self.assertRaises(SaveSlotError):
                write_slot(slot, {"tick": 1})
            with self.assertRaises(SaveSlotError):
                read_slot(slot)
            self.assertFalse((outside / "nested" / "slot.json").exists())

    def test_swapped_ancestor_cannot_redirect_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / "safe"
            safe.mkdir()
            (safe / "nested").mkdir()
            outside = root / "outside"
            (outside / "nested").mkdir(parents=True)
            old = root / "old-safe"
            target = safe / "nested" / "slot.json"
            actual_open = os.open
            swapped = False

            def swap_on_open(file, flags, *args, **kwargs):
                nonlocal swapped
                if file == "safe" and kwargs.get("dir_fd") is not None and not swapped:
                    safe.rename(old)
                    safe.symlink_to(outside, target_is_directory=True)
                    swapped = True
                return actual_open(file, flags, *args, **kwargs)

            with patch.object(os, "open", side_effect=swap_on_open):
                with self.assertRaises(SaveSlotError):
                    write_slot(target, {"tick": 2})
            self.assertTrue(swapped, "directory traversal must open components separately")
            self.assertFalse((outside / "nested" / "slot.json").exists())
            self.assertFalse((old / "nested" / "slot.json").exists())

    def test_ordinary_parent_round_trip_and_failed_update_are_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "safe" / "nested"
            root.mkdir(parents=True)
            slot = root / "slot.json"
            write_slot(slot, {"tick": 1})
            old = slot.read_bytes()
            with self.assertRaises(SaveSlotError):
                write_slot(slot, {"tick": float("nan")})
            self.assertEqual(slot.read_bytes(), old)
            write_slot(slot, {"tick": 2})
            self.assertEqual(read_slot(slot), {"tick": 2})
            self.assertEqual(list(root.glob(".campaign-*.tmp")), [])

    def test_dot_dot_ancestors_do_not_bypass_component_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "sub" / ".." / "slot.json"
            (root / "sub").mkdir()
            with self.assertRaises(SaveSlotError):
                write_slot(path, {"tick": 1})
            self.assertFalse((root / "slot.json").exists())


    def test_strict_reader_rejects_duplicate_keys_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slot = root / "slot.json"
            invalid = (
                b'{"tick":1,"tick":2}',
                b'{"tick":NaN}',
                b'{"tick":Infinity}',
                b'{"tick":-Infinity}',
                b'{"tick":1} trailing',
                b'{"tick": "\xff"}',
                b'{"tick":',
            )
            for payload in invalid:
                with self.subTest(payload=payload):
                    slot.write_bytes(payload)
                    with self.assertRaises(SaveSlotError):
                        read_slot(slot)

    def test_serialization_never_publishes_ambiguous_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "slot.json"
            write_slot(slot, {"tick": 5})
            previous = slot.read_bytes()
            invalid = (
                {"tick": float("nan")},
                {"tick": float("inf")},
                {1: "integer-key", "1": "text-key"},
            )
            for snapshot in invalid:
                with self.subTest(snapshot=snapshot):
                    with self.assertRaises(SaveSlotError):
                        write_slot(slot, snapshot)
                    self.assertEqual(slot.read_bytes(), previous)
            self.assertEqual(read_slot(slot), {"tick": 5})
            self.assertEqual(list(Path(tmp).glob(".campaign-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
