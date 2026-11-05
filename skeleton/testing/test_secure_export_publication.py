"""Adversarial no-clobber and rollback tests for the real source publisher."""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

from skeleton.ai.game_builder import secure_export_publication as publication


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
    or not (sys.platform.startswith("linux") or sys.platform == "darwin"),
    reason="requires supported POSIX atomic no-replace rename",
)


def _files():
    return {
        "index.html": b"<html>original playable source</html>",
        "godot/world.json": b'{"schema":"original-world"}',
        "godot/scripts/main.gd": b"extends Control\n",
        "proof/verified_solution.json": b'{"won":true}',
    }


def test_publishes_real_nested_files_and_preserves_exact_bytes(tmp_path):
    target = tmp_path / "game"
    result = publication.publish_generated_tree(_files(), target)
    assert result == target
    for name, payload in _files().items():
        assert (target / name).read_bytes() == payload
    assert not list(tmp_path.glob(".game-export-*"))


def test_existing_empty_destination_is_not_replaced(tmp_path):
    target = tmp_path / "game"
    target.mkdir()
    before = target.stat()
    with pytest.raises(publication.AtomicDirectoryPublicationError):
        publication.publish_generated_tree(_files(), target)
    after = target.stat()
    assert (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
    assert list(target.iterdir()) == []
    assert not list(tmp_path.glob(".game-export-*"))


def test_existing_nonempty_destination_is_not_clobbered(tmp_path):
    target = tmp_path / "game"
    target.mkdir()
    (target / "keep.txt").write_bytes(b"do not overwrite")
    with pytest.raises(publication.AtomicDirectoryPublicationError):
        publication.publish_generated_tree(_files(), target)
    assert (target / "keep.txt").read_bytes() == b"do not overwrite"


def test_concurrent_destination_creation_cannot_be_overwritten(tmp_path, monkeypatch):
    target = tmp_path / "game"
    original = publication._rename_noreplace

    def create_racing_destination(fd, source, destination):
        target.mkdir()
        (target / "owner.txt").write_bytes(b"concurrent owner")
        return original(fd, source, destination)

    monkeypatch.setattr(publication, "_rename_noreplace", create_racing_destination)
    with pytest.raises(publication.AtomicDirectoryPublicationError):
        publication.publish_generated_tree(_files(), target)
    assert (target / "owner.txt").read_bytes() == b"concurrent owner"
    assert not list(tmp_path.glob(".game-export-*"))


def test_failure_before_publication_removes_only_own_staging(tmp_path, monkeypatch):
    target = tmp_path / "game"

    def denied(*_args):
        raise OSError("simulated storage publication failure")

    monkeypatch.setattr(publication, "_rename_noreplace", denied)
    with pytest.raises(publication.AtomicDirectoryPublicationError):
        publication.publish_generated_tree(_files(), target)
    assert not target.exists()
    assert not list(tmp_path.glob(".game-export-*"))


def test_symlinked_parent_rejected_without_writing(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    with pytest.raises(publication.AtomicDirectoryPublicationError):
        publication.publish_generated_tree(_files(), tmp_path / "alias" / "game")
    assert not (real / "game").exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "x//y", "x/./y", "x/../y"])
def test_unsafe_generated_paths_rejected_before_publication(tmp_path, name):
    with pytest.raises(publication.AtomicDirectoryPublicationError):
        publication.publish_generated_tree({name: b"payload"}, tmp_path / "game")
    assert not (tmp_path / "game").exists()
    assert not list(tmp_path.glob(".game-export-*"))


def test_rejects_world_writable_destination_parent(tmp_path):
    parent = tmp_path / "untrusted"
    parent.mkdir(mode=0o777)
    parent.chmod(0o777)
    try:
        with pytest.raises(publication.AtomicDirectoryPublicationError):
            publication.publish_generated_tree(_files(), parent / "game")
        assert not (parent / "game").exists()
    finally:
        parent.chmod(0o700)


def test_source_tree_rejects_oversized_payload_without_writing(tmp_path):
    with pytest.raises(publication.AtomicDirectoryPublicationError, match="budget"):
        publication.publish_generated_tree(
            {"index.html": b"x" * 2_100_001}, tmp_path / "game",
        )
    assert not (tmp_path / "game").exists()


def test_real_original_game_compile_export_and_replay_roundtrip(tmp_path):
    from hashlib import sha256
    from skeleton.ai.game_builder.playable_compiler import compile_original_game
    from skeleton.ai.game_builder.playable_world import GameBuildIntent
    from skeleton.ai.game_builder.dual_runtime_export import (
        render_dual_runtime_package, export_dual_runtime_package,
    )
    from skeleton.ai.game_builder.dual_runtime_verify import verify_exported_package

    intent = GameBuildIntent(
        project_id="atomic-publish-001", title="Original Orchard",
        subtitle="A source-bound offline playable journey", seed=1729,
        levels=1, width=9, height=9, collectibles_per_level=1,
        hazards_per_level=0, starting_health=3,
    )
    compiled = compile_original_game(intent, authorized=True)
    package = render_dual_runtime_package(compiled, authorized=True)
    independent_pin = sha256(package.files["release.json"]).hexdigest()
    output = export_dual_runtime_package(
        package, tmp_path / "playable", authorized=True,
    )
    replay = verify_exported_package(
        output, expected_manifest_sha256=independent_pin, authorized=True,
    )
    assert replay["offline_gameplay_reexecuted"] is True
    assert replay["project_id"] == intent.project_id
    assert replay["godot_executed"] is False
    assert replay["release_certified"] is False
    with pytest.raises(Exception):
        export_dual_runtime_package(package, output, authorized=True)
    assert sha256((output / "release.json").read_bytes()).hexdigest() == independent_pin
