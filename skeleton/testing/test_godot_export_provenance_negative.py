"""Adversarial manifest custody and source hash tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from skeleton.godot_export import provenance

DIGEST = "a" * 64


def test_reject_absolute_escape_and_platform_aliases():
    for path in ("../outside", "a/../b", "/etc/passwd", "C:/windows/system32",
                 "a\\b", "./file", "a//b"):
        with pytest.raises(ValueError):
            provenance.Artifact("Linux", path, DIGEST, 3)


def test_reject_manifest_duplicate_keys_nonfinite_and_type_confusion():
    valid = {"schema": provenance.SCHEMA, "project": "p", "tree": DIGEST,
             "engine": "godot", "verdict": "NO-SHIP", "artifacts": []}
    with pytest.raises(ValueError, match="duplicate"):
        provenance.Manifest.loads(json.dumps(valid)[:-1] + ',"verdict":"SHIP"}')
    with pytest.raises(ValueError):
        provenance.Manifest.loads(json.dumps(valid)[:-1] + ',"extra": NaN}')
    with pytest.raises(ValueError):
        provenance.Artifact("Linux", "ok.bin", DIGEST, True)
    with pytest.raises(ValueError):
        provenance.Artifact("Linux", "ok.bin", "not-a-sha", 1)


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow digest backend")
def test_manifest_cannot_follow_artifact_symlink_or_hardlink(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "project.godot").write_text("[application]\n")
    output = root / "output"
    output.mkdir()
    target = output / "game.bin"
    target.write_bytes(b"binary")
    m = provenance.build(root, "godot", "SHIP", {"Linux": target})
    assert provenance.verify(m, root, root) == []
    target.unlink()
    target.symlink_to(root / "project.godot")
    assert any("unsafe" in p for p in provenance.verify(m, root))
    target.unlink()
    os.link(root / "project.godot", target)
    assert any("unsafe" in p for p in provenance.verify(m, root))


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow digest backend")
def test_no_follow_on_parent_and_source_tree(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    (root / "leak").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="linked"):
        provenance.tree_digest(root)
    with pytest.raises(OSError):
        provenance._digest_beneath(root, "leak/secret.txt")

@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow export directory custody")
def test_export_target_cannot_overwrite_or_follow_directory_symlinks(tmp_path):
    from skeleton.godot_export.export_cert import _export_target
    root = tmp_path / "out"
    target = _export_target(root, "build/linux/game.x86_64")
    assert target == root / "build/linux/game.x86_64"
    target.write_bytes(b"old")
    with pytest.raises(FileExistsError):
        _export_target(root, "build/linux/game.x86_64")
    target.unlink()
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    (root / "build" / "linked").symlink_to(redirected, target_is_directory=True)
    with pytest.raises(OSError):
        _export_target(root, "build/linked/other.x86_64")
    with pytest.raises(ValueError):
        _export_target(root, "../escape")
    with pytest.raises(ValueError):
        _export_target(root, "/etc/shadow")
