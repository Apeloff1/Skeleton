"""Safe source-digest and workspace-manifest construction tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from skeleton.shells.ai.source_digest import (
    SourceDigestError,
    SourceDigestPolicy,
    SourceDigestProvider,
)


def test_source_digest_hashes_file(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")
    provider = SourceDigestProvider(SourceDigestPolicy(root))
    digest = provider.digest("a.txt")
    assert len(digest) == 64
    assert digest == provider.digest("a.txt")


def test_source_digest_changes_with_content(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    path = root / "a.txt"
    path.write_text("one", encoding="utf-8")
    provider = SourceDigestProvider(SourceDigestPolicy(root))
    first = provider.digest("a.txt")
    path.write_text("two", encoding="utf-8")
    second = provider.digest("a.txt")
    assert first != second


def test_source_digest_rejects_absolute_resource(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "x"
    outside.write_text("x", encoding="utf-8")
    provider = SourceDigestProvider(SourceDigestPolicy(root))
    with pytest.raises(SourceDigestError, match="relative"):
        provider.digest(str(outside))


def test_source_digest_rejects_parent_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "x"
    outside.write_text("x", encoding="utf-8")
    provider = SourceDigestProvider(SourceDigestPolicy(root))
    with pytest.raises(SourceDigestError):
        provider.digest("../x")


def test_source_digest_rejects_missing_file(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    provider = SourceDigestProvider(SourceDigestPolicy(root))
    with pytest.raises(SourceDigestError, match="does not exist"):
        provider.digest("missing")


def test_source_digest_rejects_directory(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "sub").mkdir()
    provider = SourceDigestProvider(SourceDigestPolicy(root))
    with pytest.raises(SourceDigestError, match="regular file"):
        provider.digest("sub")


def test_source_digest_rejects_large_file(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.bin").write_bytes(b"x" * 11)
    provider = SourceDigestProvider(
        SourceDigestPolicy(root, max_file_bytes=10)
    )
    with pytest.raises(SourceDigestError, match="byte limit"):
        provider.digest("a.bin")


def test_source_digest_entry_has_size_and_mode(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    path = root / "a.txt"
    path.write_text("hello", encoding="utf-8")
    provider = SourceDigestProvider(SourceDigestPolicy(root))
    entry = provider.entry("a.txt")
    assert entry.path == "a.txt"
    assert entry.size_bytes == 5
    assert entry.mode is not None
    assert len(entry.digest) == 64


def test_source_manifest_deduplicates_requested_paths(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")
    provider = SourceDigestProvider(SourceDigestPolicy(root))
    manifest = provider.manifest("m", ("a.txt", "a.txt"))
    assert len(manifest.entries) == 1


def test_source_manifest_entry_limit(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a").write_text("a", encoding="utf-8")
    (root / "b").write_text("b", encoding="utf-8")
    provider = SourceDigestProvider(
        SourceDigestPolicy(root, max_manifest_entries=1)
    )
    with pytest.raises(SourceDigestError, match="entry limit"):
        provider.manifest("m", ("a", "b"))


def test_source_manifest_total_byte_limit(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a").write_bytes(b"123")
    (root / "b").write_bytes(b"456")
    provider = SourceDigestProvider(
        SourceDigestPolicy(
            root,
            max_file_bytes=10,
            max_manifest_bytes=5,
        )
    )
    with pytest.raises(SourceDigestError, match="manifest byte"):
        provider.manifest("m", ("a", "b"))


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_source_digest_rejects_symlink_by_default(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = root / "target"
    target.write_text("hello", encoding="utf-8")
    os.symlink(target, root / "link")
    provider = SourceDigestProvider(SourceDigestPolicy(root))
    with pytest.raises(SourceDigestError, match="symlink"):
        provider.digest("link")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_source_digest_allowed_symlink_must_stay_inside_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = root / "target"
    target.write_text("hello", encoding="utf-8")
    os.symlink(target, root / "link")
    provider = SourceDigestProvider(
        SourceDigestPolicy(root, allow_symlinks=True)
    )
    assert provider.digest("link") == provider.digest("target")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_source_digest_allowed_symlink_cannot_escape_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("secret", encoding="utf-8")
    os.symlink(outside, root / "link")
    provider = SourceDigestProvider(
        SourceDigestPolicy(root, allow_symlinks=True)
    )
    with pytest.raises(SourceDigestError, match="escapes"):
        provider.digest("link")


def test_source_policy_root_must_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        SourceDigestPolicy(tmp_path / "missing")


def test_source_policy_root_must_be_directory(tmp_path):
    path = tmp_path / "file"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="directory"):
        SourceDigestPolicy(path)
