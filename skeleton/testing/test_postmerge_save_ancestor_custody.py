"""Post-merge campaign-slot ancestor path custody under symlinks and races.

POSIX only: all publication remains relative to descriptor-anchored parents.
No filesystem write to an attacker-swapped ancestor or forged save is allowed.
"""
from __future__ import annotations

import os
import stat
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
                b'{"tick":1e99999}',
                b'{"tick":-1e99999}',
                b'{"tick":1e-99999}',
                b'{"tick":-1e-99999}',
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


    def test_regular_file_swap_between_precheck_and_open_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slot = root / "slot.json"
            replacement = root / "replacement.json"
            old = root / "original.json"
            slot.write_bytes(b'{"tick": 1}')
            replacement.write_bytes(b'{"tick": 2}')
            original_open = os.open
            swapped = False

            def swap_on_open(file, flags, *args, **kwargs):
                nonlocal swapped
                if file == "slot.json" and "dir_fd" in kwargs and not swapped:
                    slot.rename(old)
                    replacement.rename(slot)
                    swapped = True
                return original_open(file, flags, *args, **kwargs)

            with patch.object(os, "open", side_effect=swap_on_open):
                with self.assertRaisesRegex(SaveSlotError, "changed during open"):
                    read_slot(slot)
            self.assertTrue(swapped)
            self.assertEqual(old.read_bytes(), b'{"tick": 1}')
            self.assertEqual(slot.read_bytes(), b'{"tick": 2}')

    def test_regular_file_swap_after_bounded_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slot = root / "slot.json"
            replacement = root / "replacement.json"
            old = root / "original.json"
            slot.write_bytes(b'{"tick": 1}')
            replacement.write_bytes(b'{"tick": 2}')
            original_stat = os.stat
            calls = 0

            def swap_before_final_stat(file, *args, **kwargs):
                nonlocal calls
                if file == "slot.json" and "dir_fd" in kwargs:
                    calls += 1
                    if calls == 2:
                        slot.rename(old)
                        replacement.rename(slot)
                return original_stat(file, *args, **kwargs)

            with patch.object(os, "stat", side_effect=swap_before_final_stat):
                with self.assertRaisesRegex(SaveSlotError, "changed during read"):
                    read_slot(slot)
            self.assertEqual(calls, 2)
            self.assertEqual(old.read_bytes(), b'{"tick": 1}')
            self.assertEqual(slot.read_bytes(), b'{"tick": 2}')

    def test_same_inode_mutated_during_read_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "slot.json"
            slot.write_bytes(b'{"tick": 1}')
            original_fstat = os.fstat
            modified = False

            def mutate_on_first_regular_fstat(fd):
                nonlocal modified
                observed = original_fstat(fd)
                if stat.S_ISREG(observed.st_mode) and not modified:
                    slot.write_bytes(b'{"tick": 2}')
                    modified = True
                return observed

            with patch.object(os, "fstat", side_effect=mutate_on_first_regular_fstat):
                with self.assertRaisesRegex(SaveSlotError, "changed during read"):
                    read_slot(slot)
            self.assertTrue(modified)

    def test_removed_file_during_read_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "slot.json"
            slot.write_bytes(b'{"tick": 1}')
            original_stat = os.stat
            calls = 0

            def remove_at_validation(file, *args, **kwargs):
                nonlocal calls
                if file == "slot.json" and "dir_fd" in kwargs:
                    calls += 1
                    if calls == 2:
                        slot.unlink()
                return original_stat(file, *args, **kwargs)

            with patch.object(os, "stat", side_effect=remove_at_validation):
                with self.assertRaisesRegex(SaveSlotError, "disappeared during read"):
                    read_slot(slot)
            self.assertFalse(slot.exists())


    def test_exact_zero_exponents_remain_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "slot.json"
            slot.write_bytes(b'{"tick":0e-99999,"offset":-0e-99999}')
            self.assertEqual(read_slot(slot), {"tick": 0.0, "offset": -0.0})

    def test_streamed_encoder_stops_before_oversized_snapshot_is_walked(self):
        from skeleton.game.gameplay import offline_grid_save_slot as module

        class MalformedHugeList(list):
            def __iter__(self):
                yield "a" * 128
                raise AssertionError("unbounded serialization walked further")

        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "slot.json"
            with patch.object(module, "MAX_SAVE_BYTES", 64):
                with self.assertRaisesRegex(SaveSlotError, "byte budget"):
                    write_slot(slot, MalformedHugeList())
            self.assertFalse(slot.exists())
            self.assertEqual(list(Path(tmp).glob(".campaign-*.tmp")), [])

    def test_writer_uses_bounded_streaming_not_monolithic_json_dumps(self):
        from skeleton.game.gameplay import offline_grid_save_slot as module

        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "slot.json"
            with patch.object(module.json, "dumps",
                              side_effect=AssertionError("monolithic JSON encoding")):
                write_slot(slot, {"tick": 4, "flags": ["safe"]})
            self.assertEqual(read_slot(slot), {"tick": 4, "flags": ["safe"]})



if __name__ == "__main__":
    unittest.main()
