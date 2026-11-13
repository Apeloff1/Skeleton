"""Adversarial artifact path, atomic-publication and download-custody tests."""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

from services import binary_builder as binary


@pytest.mark.parametrize("bad", [
    "", ".", "..", "../secret", "assets/../secret",
    "/etc/passwd", "C:\\windows\\system.ini", "\\\\server\\share",
    "assets//hero.png", "assets/./hero.png", "AUX", "CON.txt",
    "assets/NUL", "assets/trailing.", "assets/trailing ", "assets/field:stream",
    "assets/a\x00b", "manifest.json", "nested/" * 17 + "x",
])
def test_artifact_source_paths_are_canonical(bad):
    with pytest.raises(ValueError):
        binary._sanitize_path(bad)


def test_asset_source_windows_separators_are_canonicalized_without_traversal():
    assert binary._sanitize_path("art\\hero.png") == "art/hero.png"
    assert binary._sanitize_path("art/hero.png") == "art/hero.png"


@pytest.mark.parametrize("content", [None, {"nested": "data"}, object()])
def test_packager_refuses_unexpected_content_objects(content):
    with pytest.raises(ValueError):
        binary._bounded_asset_bytes(content)


def test_per_asset_byte_budget_is_enforced_before_encoding(monkeypatch):
    monkeypatch.setattr(binary, "_MAX_ASSET_BYTES", 64)
    with pytest.raises(ValueError, match="byte budget"):
        binary._bounded_asset_bytes("A" * 65)
    assert binary._bounded_asset_bytes("ok") == b"ok"


@pytest.fixture
def publish_root(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(binary, "ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(binary, "_ensure_artifacts_root", lambda: tmp_path)
    monkeypatch.setattr(binary, "require_execution_allowed", lambda *_: True)
    return tmp_path


def test_zip_publishes_complete_archive_and_records_bytes(publish_root):
    build = {
        "build_id": "secure",
        "title": "Original game",
        "files": {"assets/readme.txt": "hello world"},
    }
    result = binary.build_zip(build)
    path = publish_root / "secure.zip"
    assert result["size_bytes"] == path.stat().st_size
    assert result["file_count"] == 1
    with zipfile.ZipFile(path) as archive:
        assert json.loads(archive.read("manifest.json"))["build_id"] == "secure"
        assert archive.read("assets/readme.txt") == b"hello world"
    assert not list(publish_root.glob(".vault-part-*"))


def test_invalid_asset_does_not_replace_previous_publish(publish_root):
    published = publish_root / "stable.zip"
    published.write_bytes(b"verified-previous")
    with pytest.raises(ValueError):
        binary.build_zip({"build_id": "stable", "files": {"../escape": b"x"}})
    assert published.read_bytes() == b"verified-previous"
    assert not list(publish_root.glob(".vault-part-*"))


def test_archive_total_budget_failure_preserves_old_artifact(publish_root, monkeypatch):
    monkeypatch.setattr(binary, "_MAX_SOURCE_BYTES", 10)
    published = publish_root / "stable.zip"
    published.write_bytes(b"old")
    with pytest.raises(ValueError, match="total"):
        binary.build_zip({"build_id": "stable", "files": {"large.txt": "X" * 11}})
    assert published.read_bytes() == b"old"
    assert not list(publish_root.glob(".vault-part-*"))


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX publication")
def test_symlink_published_leaf_is_never_followed(publish_root, tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.write_bytes(b"secret")
    (publish_root / "safe.zip").symlink_to(outside)
    with pytest.raises(ValueError):
        binary.build_zip({"build_id": "safe", "files": {"readme.txt": "hello"}})
    assert outside.read_bytes() == b"secret"


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX publication")
def test_pinned_reader_keeps_previous_inode_during_atomic_republish(publish_root):
    previous = publish_root / "next.zip"
    previous.write_bytes(b"previous-artifact")
    opened = binary.open_artifact_for_download("next", "zip")
    assert opened is not None
    try:
        result = binary.build_zip({"build_id": "next", "files": {"note.txt": "new"}})
        assert result["size_bytes"] > 0
        assert previous.read_bytes().startswith(b"PK")
        assert opened.read() == b"previous-artifact"
    finally:
        opened.close()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX publication")
def test_apk_publishes_only_after_staging_completed(publish_root, monkeypatch):
    published = publish_root / "safe.apk"
    published.write_bytes(b"old-apk")

    def stage(build, output):
        assert output.parent != publish_root
        output.write_bytes(b"new-complete-apk")
        return {"kind": "apk", "path": str(output), "size_bytes": output.stat().st_size}

    monkeypatch.setattr(binary, "_build_apk_staged", stage)
    result = binary.build_apk({"build_id": "safe"})
    assert result["path"] == str(published)
    assert result["size_bytes"] == len(b"new-complete-apk")
    assert published.read_bytes() == b"new-complete-apk"


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX publication")
def test_failed_apk_stage_preserves_previous_publish(publish_root, monkeypatch):
    published = publish_root / "safe.apk"
    published.write_bytes(b"old-complete-apk")

    def fail(build, output):
        output.write_bytes(b"partial")
        raise RuntimeError("toolchain failed halfway")

    monkeypatch.setattr(binary, "_build_apk_staged", fail)
    with pytest.raises(RuntimeError, match="toolchain failed"):
        binary.build_apk({"build_id": "safe"})
    assert published.read_bytes() == b"old-complete-apk"
