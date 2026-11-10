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
            for fn in (os.open, os.stat, os.rename, os.unlink, os.link))
)


@unittest.skipUnless(SUPPORTS, "requires descriptor-relative POSIX file operations")
class CreateOnlyCampaignCustodyTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
