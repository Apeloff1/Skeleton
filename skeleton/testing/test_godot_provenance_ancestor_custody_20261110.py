"""Godot provenance regression: current paths, not orphaned file descriptors.

These are offline adversarial source tests. They do not certify actual Godot,
export templates, Windows/WSL2, native devices or release provenance.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from skeleton.godot_export import provenance


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="requires descriptor-anchored POSIX artifact custody",
)


def test_digest_refuses_symlinked_parent_swapped_during_hash(tmp_path):
    root = tmp_path / "source"
    parent = root / "build"
    parent.mkdir(parents=True)
    current = parent / "game.pck"
    content = b"a" * 8192
    current.write_bytes(content)
    other = tmp_path / "outside"
    other.mkdir()
    (other / "game.pck").write_bytes(content)
    orphan = root / "orphaned"
    actual_read = os.read
    swapped = False

    def replace_ancestor_after_read(fd, count):
        nonlocal swapped
        result = actual_read(fd, count)
        if result and not swapped:
            swapped = True
            parent.rename(orphan)
            parent.symlink_to(other, target_is_directory=True)
        return result

    with patch.object(provenance.os, "read", side_effect=replace_ancestor_after_read):
        with pytest.raises(ValueError, match="ancestor path"):
            provenance._digest_beneath(root, "build/game.pck")
    assert swapped
    assert (orphan / "game.pck").read_bytes() == content
    assert (other / "game.pck").read_bytes() == content


def test_digest_refuses_real_directory_replaced_with_identical_contents(tmp_path):
    root = tmp_path / "source"
    parent = root / "build"
    parent.mkdir(parents=True)
    current = parent / "game.bin"
    payload = b"byte-identical-content" * 600
    current.write_bytes(payload)
    other = root / "waiting"
    other.mkdir()
    (other / "game.bin").write_bytes(payload)
    orphan = root / "orphaned"
    actual_read = os.read
    swapped = False

    def replace_parent_after_read(fd, count):
        nonlocal swapped
        result = actual_read(fd, count)
        if result and not swapped:
            swapped = True
            parent.rename(orphan)
            other.rename(parent)
        return result

    with patch.object(provenance.os, "read", side_effect=replace_parent_after_read):
        with pytest.raises(ValueError, match="ancestor path replaced"):
            provenance._digest_beneath(root, "build/game.bin")
    assert swapped
    assert (parent / "game.bin").read_bytes() == payload


def test_digest_refuses_whole_source_root_replaced_during_read(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    payload = b"identical" * 1024
    (root / "game.pck").write_bytes(payload)
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "game.pck").write_bytes(payload)
    detached = tmp_path / "old-source"
    actual_read = os.read
    swapped = False

    def replace_root_after_read(fd, count):
        nonlocal swapped
        result = actual_read(fd, count)
        if result and not swapped:
            swapped = True
            root.rename(detached)
            replacement.rename(root)
        return result

    with patch.object(provenance.os, "read", side_effect=replace_root_after_read):
        with pytest.raises(ValueError, match="ancestor path replaced"):
            provenance._digest_beneath(root, "game.pck")
    assert swapped
    assert (detached / "game.pck").read_bytes() == payload


def test_stable_parent_and_leaf_remain_identically_hashable(tmp_path):
    root = tmp_path / "source"
    output = root / "artifacts" / "linux"
    output.mkdir(parents=True)
    payload = b"real-godot-binary" * 256
    (output / "game.pck").write_bytes(payload)
    observed = provenance._digest_beneath(root, "artifacts/linux/game.pck")
    assert observed == (hashlib.sha256(payload).hexdigest(), len(payload))


def test_source_tree_avoids_full_materialized_rglob_sort(tmp_path):
    root = tmp_path / "project"
    source = root / "scripts"
    source.mkdir(parents=True)
    (source / "c.gd").write_text("extends Node\n", encoding="utf-8")
    (source / "a.gd").write_text("extends Node2D\n", encoding="utf-8")
    (root / "project.godot").write_text("[application]\n", encoding="utf-8")
    expected = provenance.tree_digest(root)
    with patch.object(
        Path, "rglob",
        side_effect=AssertionError("unbounded rglob cannot be used"),
    ):
        assert provenance.tree_digest(root) == expected


def test_source_file_cap_fails_closed_before_large_materialization(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    for index in range(4):
        (root / f"file_{index}.gd").write_text("extends Node\n")
    with patch.object(provenance, "MAX_SOURCE_FILES", 2):
        with pytest.raises(ValueError, match="source file budget"):
            provenance.tree_digest(root)


def test_source_directory_count_has_independent_budget(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    for index in range(6):
        (root / f"dir_{index}").mkdir()
    with patch.object(provenance, "MAX_SOURCE_ENTRIES", 3):
        with pytest.raises(ValueError, match="entry budget"):
            provenance.tree_digest(root)


def test_ignored_build_tree_is_pruned_before_security_scan(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "project.godot").write_text("[application]\n", encoding="utf-8")
    baseline = provenance.tree_digest(root)
    # The build folder is an ignored generated artifact subtree. Neither
    # its size nor its internal links should enter the source tree digest.
    ignored = root / "build"
    ignored.mkdir()
    for index in range(20):
        (ignored / f"generated_{index}.bin").write_bytes(b"x")
    (ignored / "linked.bin").symlink_to(root / "project.godot")
    with patch.object(provenance, "MAX_SOURCE_ENTRIES", 3):
        assert provenance.tree_digest(root) == baseline


def test_special_fifo_is_not_accepted_as_source_file(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    root = tmp_path / "project"
    root.mkdir()
    os.mkfifo(root / "surprise.pipe")
    with pytest.raises(ValueError, match="special"):
        provenance.tree_digest(root)


def test_source_root_changed_after_scan_cannot_qualify(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.gd").write_bytes(b"extends Node\n")
    waiting = tmp_path / "replacement"
    waiting.mkdir()
    (waiting / "main.gd").write_bytes(b"extends Node\n")
    previous = tmp_path / "old-project"
    original = provenance._digest_beneath
    switched = False

    def digest_then_swap(dir_root, relative):
        nonlocal switched
        result = original(dir_root, relative)
        if not switched:
            root.rename(previous)
            waiting.rename(root)
            switched = True
        return result

    with patch.object(provenance, "_digest_beneath", side_effect=digest_then_swap):
        with pytest.raises(ValueError, match="source root changed"):
            provenance.tree_digest(root)
    assert switched


def test_manifest_sha_cannot_be_qualified_from_detached_parent(tmp_path):
    root = tmp_path / "project"
    target_dir = root / "artifacts"
    target_dir.mkdir(parents=True)
    (root / "project.godot").write_text("[application]\n")
    target = target_dir / "native.bin"
    target.write_bytes(b"payload" * 256)
    manifest = provenance.build(root, "4.7", "SHIP", {"Linux": target})
    assert provenance.verify(manifest, root, root) == []
    target_dir.rename(root / "detached")
    new_dir = root / "artifacts"
    new_dir.mkdir()
    (new_dir / "native.bin").write_bytes(b"modified" * 256)
    problems = provenance.verify(manifest, root, root)
    assert any("mismatch" in issue or "changed" in issue for issue in problems)
