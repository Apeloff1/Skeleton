"""Descriptor-anchored installed game inode inventory regression suite."""
from __future__ import annotations

import os
from pathlib import Path
import shutil

import pytest

from skeleton.app.installed_tree_custody import (
    InstalledTreeCustodyError, installed_tree_snapshot_digest,
    snapshot_installed_tree,
)
from skeleton.testing.test_app_offline_first_playable_delivery import original_source

pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="POSIX nofollow inventory is required",
)


@pytest.fixture
def copied_game(original_source, tmp_path):
    installed = tmp_path / "installed"
    shutil.copytree(original_source[0], installed)
    return installed


def test_real_original_game_inventory_is_bounded_and_stable(copied_game):
    first = snapshot_installed_tree(copied_game)
    second = snapshot_installed_tree(copied_game)
    assert first == second
    assert first[0][0] == ""
    assert any(name == "release.json" for name, _ in first)
    assert any(name == "godot/scripts/main.gd" for name, _ in first)
    assert len(first) > 6
    assert len(installed_tree_snapshot_digest(first)) == 64
    assert installed_tree_snapshot_digest(first) == installed_tree_snapshot_digest(second)


def test_same_byte_nested_asset_inode_replacement_changes_inventory(
    copied_game, tmp_path,
):
    target = copied_game / "godot" / "scripts" / "main.gd"
    before = snapshot_installed_tree(copied_game)
    replacement = tmp_path / "replacement.gd"
    replacement.write_bytes(target.read_bytes())
    replacement.chmod(target.stat().st_mode & 0o777)
    os.replace(replacement, target)
    after = snapshot_installed_tree(copied_game)
    assert after != before
    assert installed_tree_snapshot_digest(after) != installed_tree_snapshot_digest(before)


def test_symlinked_nested_asset_fails_closed(copied_game, tmp_path):
    target = copied_game / "godot" / "scripts" / "main.gd"
    other = tmp_path / "other.gd"
    other.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(other)
    with pytest.raises((InstalledTreeCustodyError, OSError, ValueError)):
        snapshot_installed_tree(copied_game)


def test_hardlinked_asset_fails_closed(copied_game, tmp_path):
    target = copied_game / "godot" / "scripts" / "main.gd"
    os.link(target, tmp_path / "second-link.gd")
    with pytest.raises(InstalledTreeCustodyError, match="unsafe"):
        snapshot_installed_tree(copied_game)


def test_oversized_asset_fails_before_inventory_is_accepted(copied_game):
    target = copied_game / "godot" / "scripts" / "main.gd"
    with target.open("wb") as stream:
        stream.truncate(2_100_001)
    with pytest.raises(InstalledTreeCustodyError, match="budget"):
        snapshot_installed_tree(copied_game)


def test_too_many_entries_rejected(copied_game):
    directory = copied_game / "extra"
    directory.mkdir()
    for index in range(140):
        (directory / f"item_{index:03d}.txt").write_bytes(b"x")
    with pytest.raises((InstalledTreeCustodyError, ValueError), match="budget"):
        snapshot_installed_tree(copied_game)


def test_special_file_rejected_without_blocking(copied_game):
    fifo = copied_game / "unexpected_fifo"
    os.mkfifo(fifo)
    with pytest.raises(InstalledTreeCustodyError, match="unsafe"):
        snapshot_installed_tree(copied_game)


def test_symlinked_parent_directory_rejected(copied_game, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(copied_game, target_is_directory=True)
    with pytest.raises((InstalledTreeCustodyError, OSError, ValueError)):
        snapshot_installed_tree(alias)


def test_invalid_inventory_digest_input_rejected():
    for invalid in ((), (("a", ("bad",)),), (("a", (True,)),)):
        with pytest.raises(InstalledTreeCustodyError):
            installed_tree_snapshot_digest(invalid)
