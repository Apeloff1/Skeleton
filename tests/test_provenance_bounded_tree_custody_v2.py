"""Godot source provenance: bounded traversal and exact directory custody."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from skeleton.godot_export import provenance as p


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="requires native POSIX no-follow directory descriptors",
)


def project(tmp_path: Path) -> Path:
    root = tmp_path / "game-project"
    root.mkdir()
    (root / "project.godot").write_text("[application]\n", encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "scene.gd").write_text("extends Node\n", encoding="utf-8")
    return root


def test_tree_hash_is_global_lexical_order_independent_of_creation(tmp_path: Path):
    root = project(tmp_path)
    nested = root / "scripts" / "b"
    nested.mkdir()
    (nested / "z.gd").write_text("Z", encoding="utf-8")
    (nested / "a.gd").write_text("A", encoding="utf-8")
    manual = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manual.update(rel.encode() + b"\0" + digest.encode() + b"\n")
    assert p.tree_digest(root) == manual.hexdigest()
    assert p.tree_digest(root) == p.tree_digest(root)


def test_ignored_build_and_cache_are_not_part_of_source_authority(tmp_path: Path):
    root = project(tmp_path)
    baseline = p.tree_digest(root)
    for subdir in ("build", ".godot", ".import", "export", ".git"):
        directory = root / subdir
        directory.mkdir()
        (directory / "artifact.bin").write_bytes(b"ignored")
    assert p.tree_digest(root) == baseline
    (root / "scripts" / "scene.gd").write_text("extends Node\n# changed", encoding="utf-8")
    assert p.tree_digest(root) != baseline


def test_source_file_count_is_bounded_before_big_inventory(tmp_path: Path, monkeypatch):
    root = project(tmp_path)
    (root / "scripts" / "more.gd").write_text("third", encoding="utf-8")
    monkeypatch.setattr(p, "MAX_SOURCE_FILES", 2)
    with pytest.raises(ValueError, match="file budget"):
        p.tree_digest(root)


def test_empty_directory_inventory_is_bounded(tmp_path: Path, monkeypatch):
    root = project(tmp_path)
    for i in range(5):
        (root / f"empty-{i}").mkdir()
    monkeypatch.setattr(p, "MAX_SOURCE_DIRS", 3)
    with pytest.raises(ValueError, match="directory budget"):
        p.tree_digest(root)


def test_source_bytes_are_budgeted(tmp_path: Path, monkeypatch):
    root = project(tmp_path)
    monkeypatch.setattr(p, "MAX_SOURCE_BYTES", 12)
    with pytest.raises(ValueError, match="size budget"):
        p.tree_digest(root)


def test_source_root_missing_and_symlinked_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="root"):
        p.tree_digest(tmp_path / "nonexistent")
    root = project(tmp_path)
    linked = tmp_path / "linked"
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="root"):
        p.tree_digest(linked)


def test_source_intermediate_symlink_refused(tmp_path: Path):
    root = project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "other.gd").write_bytes(b"private")
    (root / "external").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe"):
        p.tree_digest(root)


def test_digest_rejects_parent_replacement_after_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    root = project(tmp_path)
    source = root / "scripts" / "scene.gd"
    original_read = os.read
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "scene.gd").write_bytes(b"foreign")
    old = root / "scripts-old"
    changed = False

    def move_parent_while_reading(fd, count):
        nonlocal changed
        payload = original_read(fd, count)
        if payload and not changed:
            changed = True
            (root / "scripts").rename(old)
            (root / "scripts").symlink_to(outside, target_is_directory=True)
        return payload

    monkeypatch.setattr(p.os, "read", move_parent_while_reading)
    with pytest.raises(ValueError, match="directory changed"):
        p._digest_beneath(root, "scripts/scene.gd")
    assert changed
    assert source.is_file()  # through the swapped path; no source trust granted
    assert (outside / "scene.gd").read_bytes() == b"foreign"


def test_digest_rejects_replacement_directory_even_with_same_file_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    root = project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    source = root / "scripts" / "scene.gd"
    (outside / "scene.gd").write_bytes(source.read_bytes())
    old = root / "scripts-old"
    original_read = os.read
    changed = False

    def reparent(fd, count):
        nonlocal changed
        chunk = original_read(fd, count)
        if chunk and not changed:
            changed = True
            (root / "scripts").rename(old)
            outside.rename(root / "scripts")
        return chunk

    monkeypatch.setattr(p.os, "read", reparent)
    with pytest.raises(ValueError, match="directory replaced"):
        p._digest_beneath(root, "scripts/scene.gd")
    assert changed


def test_manifest_verifier_remains_fail_closed_after_path_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    root = project(tmp_path)
    target = root / "scripts" / "scene.gd"
    source = p.build(root, "4.7", "SHIP", {"Asset": target})
    original_read = os.read
    mutated = False

    def mutate(fd, count):
        nonlocal mutated
        value = original_read(fd, count)
        if value and not mutated:
            mutated = True
            target.write_text("extends Node\n# modified", encoding="utf-8")
        return value

    monkeypatch.setattr(p.os, "read", mutate)
    errors = p.verify(source, root, root)
    assert errors
    assert any("unreadable" in item or "changed" in item for item in errors)


def test_tree_hash_nontrivial_project_has_bounded_sorted_output(tmp_path: Path):
    root = project(tmp_path)
    for directory in range(7):
        target = root / f"d{directory}"
        target.mkdir()
        for file_number in range(5):
            (target / f"file-{file_number}.gd").write_text(
                f"extends Node\n# {directory}.{file_number}\n",
                encoding="utf-8",
            )
    first = p.tree_digest(root)
    second = p.tree_digest(root)
    assert first == second
    assert len(first) == 64


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
