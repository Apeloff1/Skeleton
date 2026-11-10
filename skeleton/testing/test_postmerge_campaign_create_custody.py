"""Create-only offline campaign regression suite using real filesystem/CLI entry points.

This is source-level POSIX acceptance, not first-install or Windows qualification.
"""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.game.offline_grid_campaign import main as campaign_main
from skeleton.game.gameplay.offline_grid_save_slot import (
    SaveSlotError, create_slot, read_slot,
)


SUPPORTS = (
    os.name == "posix"
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "supports_dir_fd")
    and all(fn in os.supports_dir_fd
            for fn in (os.open, os.stat, os.rename, os.unlink))
)


@unittest.skipUnless(SUPPORTS, "requires descriptor-relative POSIX file operations")
class CreateOnlyCampaignCustodyTests(unittest.TestCase):
    def test_atomic_create_slot_has_exactly_one_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slot = root / "atomic.json"
            create_slot(slot, {"tick": 10})
            stat_result = os.stat(slot, follow_symlinks=False)
            self.assertEqual(stat_result.st_nlink, 1)
            self.assertEqual(read_slot(slot), {"tick": 10})
            self.assertEqual(list(root.glob(".campaign-*.tmp")), [])

    def test_publish_failure_never_leaks_temporary_or_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "atomic.json"
            with patch(
                "skeleton.game.gameplay.offline_grid_save_slot._rename_noreplace",
                side_effect=SaveSlotError("native no-replace unavailable"),
            ):
                with self.assertRaisesRegex(SaveSlotError, "native no-replace"):
                    create_slot(target, {"tick": 10})
            self.assertFalse(target.exists())
            self.assertEqual(list(root.glob(".campaign-*.tmp")), [])

    def test_competing_create_wins_without_clobber(self):
        from skeleton.game.gameplay import offline_grid_save_slot as module

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "atomic.json"
            native = module._rename_noreplace

            def competing_writer(dfd, source, dest):
                with os.fdopen(
                    os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600, dir_fd=dfd), "wb",
                ) as stream:
                    stream.write(b'{"tick":99}')
                    stream.flush()
                    os.fsync(stream.fileno())
                return native(dfd, source, dest)

            with patch.object(module, "_rename_noreplace", side_effect=competing_writer):
                with self.assertRaises(FileExistsError):
                    create_slot(target, {"tick": 10})
            self.assertEqual(read_slot(target), {"tick": 99})
            self.assertEqual(list(root.glob(".campaign-*.tmp")), [])

    def test_no_clobber_preserves_previous_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slot = root / "save.json"
            create_slot(slot, {"tick": 9})
            prior = slot.read_bytes()
            with self.assertRaises(FileExistsError):
                create_slot(slot, {"tick": 10})
            self.assertEqual(slot.read_bytes(), prior)
            self.assertEqual(read_slot(slot), {"tick": 9})
            self.assertEqual(list(root.glob(".campaign-*.tmp")), [])

    def test_intermediate_symlink_does_not_escape_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            alias = root / "alias"
            alias.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(SaveSlotError):
                create_slot(alias / "save.json", {"tick": 1})
            self.assertFalse((outside / "save.json").exists())

    def test_replaced_ancestor_is_rejected_without_foreign_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / "safe"
            safe.mkdir()
            outside = root / "outside"
            outside.mkdir()
            old = root / "old-safe"
            path = safe / "save.json"
            actual_open = os.open
            swapped = False

            def swap(file, flags, *args, **kwargs):
                nonlocal swapped
                if file == "safe" and kwargs.get("dir_fd") is not None and not swapped:
                    safe.rename(old)
                    safe.symlink_to(outside, target_is_directory=True)
                    swapped = True
                return actual_open(file, flags, *args, **kwargs)

            with patch.object(os, "open", side_effect=swap):
                with self.assertRaises(SaveSlotError):
                    create_slot(path, {"tick": 2})
            self.assertTrue(swapped)
            self.assertFalse((outside / "save.json").exists())
            self.assertFalse((old / "save.json").exists())

    def test_cli_create_only_fails_closed_on_intermediate_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = root / "commands.json"
            commands.write_text("[]", encoding="utf-8")
            outside = root / "outside"
            outside.mkdir()
            alias = root / "alias"
            alias.symlink_to(outside, target_is_directory=True)
            with contextlib.redirect_stderr(io.StringIO()):
                code = campaign_main([
                    "run", "--commands", str(commands),
                    "--out-save", str(alias / "save.json"),
                ])
            self.assertEqual(code, 2)
            self.assertFalse((outside / "save.json").exists())

    def test_create_only_requires_descriptor_link_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "save.json"
            with patch.object(os, "supports_dir_fd", frozenset()):
                with self.assertRaises(SaveSlotError):
                    create_slot(slot, {"tick": 1})
            self.assertFalse(slot.exists())

    def test_create_only_cli_round_trip_into_strict_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = root / "commands.json"
            commands.write_text("[]", encoding="utf-8")
            save = root / "created.json"
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = campaign_main([
                    "run", "--commands", str(commands),
                    "--out-save", str(save),
                ])
            self.assertEqual(status, 0, stderr.getvalue())
            created = read_slot(save)
            self.assertEqual(created, __import__("json").loads(stdout.getvalue())["save"])
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                status = campaign_main([
                    "run", "--commands", str(commands),
                    "--resume", str(save),
                ])
            self.assertEqual(status, 0, stderr.getvalue())
            self.assertEqual(read_slot(save), created)

    def test_resume_without_replacement_rejects_overflowing_json_exponent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = root / "commands.json"
            commands.write_text("[]", encoding="utf-8")
            resume = root / "save.json"
            resume.write_bytes(b'{"tick":1e99999}')
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                status = campaign_main([
                    "run", "--commands", str(commands),
                    "--resume", str(resume),
                ])
            self.assertEqual(status, 2)
            self.assertIn("non-finite save value", err.getvalue())


    def test_cli_commands_cannot_escape_through_symlink_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            actions = outside / "actions.json"
            actions.write_text("[]", encoding="utf-8")
            alias = root / "alias"
            alias.symlink_to(outside, target_is_directory=True)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                result = campaign_main([
                    "run", "--commands", str(alias / "actions.json"),
                ])
            self.assertEqual(result, 2)
            self.assertFalse((outside / "save.json").exists())

    def test_cli_source_cannot_escape_through_symlink_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = Path(__file__).resolve().parents[2] / (
                "skeleton/game/gameplay/content/lantern_harbor.json"
            )
            outside = root / "outside"
            outside.mkdir()
            source = outside / "source.json"
            source.write_bytes(original.read_bytes())
            alias = root / "alias"
            alias.symlink_to(outside, target_is_directory=True)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                result = campaign_main(["inspect", "--source", str(alias / "source.json")])
            self.assertEqual(result, 2)

    def test_cli_rejects_duplicate_commands_and_nonfinite_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions = root / "actions.json"
            for content in (
                b'[{"kind":"wait","kind":"move"}]',
                b'[{"kind":"wait","target":1e99999}]',
                b'[{"kind":"wait","target":NaN}]',
            ):
                with self.subTest(content=content):
                    actions.write_bytes(content)
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        result = campaign_main(["run", "--commands", str(actions)])
                    self.assertEqual(result, 2)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_racing_fifo_substitution_cannot_hang_read_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save = root / "slot.json"
            save.write_bytes(b'{"tick":1}')
            prior = root / "prior.json"
            actual_open = os.open
            swapped = False

            def swap_open(file, flags, *args, **kwargs):
                nonlocal swapped
                if file == "slot.json" and not swapped:
                    self.assertTrue(flags & os.O_NONBLOCK,
                                    "guarded reader must never block on a FIFO")
                    save.rename(prior)
                    os.mkfifo(save)
                    swapped = True
                return actual_open(file, flags, *args, **kwargs)

            with patch.object(os, "open", side_effect=swap_open):
                with self.assertRaises(SaveSlotError):
                    read_slot(save)
            self.assertTrue(swapped)
            self.assertEqual(prior.read_bytes(), b'{"tick":1}')


if __name__ == "__main__":
    unittest.main()
