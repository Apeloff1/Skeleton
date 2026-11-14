"""No toolchain required: secure ZIP publication and adversarial members."""
from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

import pytest

from core.vault_secure_fs import VaultPathError
from services import binary_builder as builder


@pytest.fixture
def artifact_root(monkeypatch, tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    monkeypatch.setattr(builder, "ARTIFACTS_ROOT", root)
    monkeypatch.setattr(builder, "require_execution_allowed", lambda _: True)
    return root


def test_zip_is_atomic_and_digest_covers_actual_downloadable_bytes(artifact_root):
    result = builder.build_zip({
        "build_id": "safe",
        "title": "Approved",
        "generated_files": {"scripts/main.js": "console.log(1)"},
    })
    archive = artifact_root / "safe.zip"
    assert archive.exists()
    assert result["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert result["size_bytes"] == archive.stat().st_size
    assert result["file_count"] == 1
    with zipfile.ZipFile(archive) as contents:
        assert contents.namelist() == ["manifest.json", "scripts/main.js"]
        assert contents.read("scripts/main.js") == b"console.log(1)"


@pytest.mark.parametrize("path", [
    "", ".", "..", "../credentials", "x/../credentials",
    "/etc/passwd", "C:\\secret.txt", "x//y", "x/./y",
    "manifest.json", "x\x00evil", "x" * 257, "x/",
])
def test_archive_member_path_rejects_ambiguous_and_reserved_names(artifact_root, path):
    with pytest.raises(ValueError):
        builder.build_zip({
            "build_id": "reject",
            "generated_files": {path: "data"},
        })
    assert not (artifact_root / "reject.zip").exists()


def test_backslashes_canonicalize_only_safe_relative_paths(artifact_root):
    assert builder._sanitize_path("x\\scripts\\main.js") == "x/scripts/main.js"


def test_archive_rejects_unbounded_file_and_aggregate_sizes(monkeypatch, artifact_root):
    monkeypatch.setattr(builder, "_MAX_PACKAGE_FILE_BYTES", 8)
    with pytest.raises(ValueError, match="byte budget"):
        builder.build_zip({
            "build_id": "large",
            "generated_files": {"big.txt": "y" * 9},
        })
    assert not (artifact_root / "large.zip").exists()

    monkeypatch.setattr(builder, "_MAX_PACKAGE_FILE_BYTES", 128)
    monkeypatch.setattr(builder, "_MAX_PACKAGE_RAW_BYTES", 12)
    with pytest.raises(ValueError, match="payload byte budget"):
        builder.build_zip({
            "build_id": "total",
            "generated_files": {"a.txt": "x" * 9, "b.txt": "y" * 9},
        })
    assert not (artifact_root / "total.zip").exists()


def test_generator_cannot_stream_unlimited_repeated_entries(monkeypatch, artifact_root):
    monkeypatch.setattr(builder, "_MAX_PACKAGE_FILES", 3)
    def infinite():
        while True:
            yield "same.txt", "x"
    # The stricter canonical-name contract rejects the second repeated name.
    with pytest.raises(ValueError, match="duplicate"):
        builder.build_zip({
            "build_id": "infinite",
            "generated_files_factory": infinite,
        })
    assert not (artifact_root / "infinite.zip").exists()


def test_failed_generator_never_truncates_previous_archive(artifact_root):
    builder.build_zip({"build_id": "stable", "generated_files": {"old.txt": "before"}})
    archive = artifact_root / "stable.zip"
    prior = archive.read_bytes()

    def interrupted():
        yield "new.txt", "after"
        raise RuntimeError("generator interrupted")

    with pytest.raises(RuntimeError, match="interrupted"):
        builder.build_zip({
            "build_id": "stable",
            "generated_files_factory": interrupted,
        })
    assert archive.read_bytes() == prior
    assert not list(artifact_root.glob(".vault-part-*"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_symlinked_archive_destination_does_not_overwrite_external_data(artifact_root, tmp_path):
    external = tmp_path / "outside"
    external.write_bytes(b"private-source")
    (artifact_root / "evil.zip").symlink_to(external)
    with pytest.raises(VaultPathError):
        builder.build_zip({
            "build_id": "evil", "generated_files": {"ok.txt": "safe"},
        })
    assert external.read_bytes() == b"private-source"
    assert (artifact_root / "evil.zip").is_symlink()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_archive_root_symlink_is_rejected(artifact_root, tmp_path, monkeypatch):
    link = tmp_path / "alias"
    link.symlink_to(artifact_root, target_is_directory=True)
    monkeypatch.setattr(builder, "ARTIFACTS_ROOT", link)
    with pytest.raises((VaultPathError, OSError)):
        builder.build_zip({"build_id": "bad", "generated_files": {"ok.txt": "safe"}})


def test_distinct_generator_cannot_exceed_scan_budget(monkeypatch, artifact_root):
    monkeypatch.setattr(builder, "_MAX_PACKAGE_FILES", 3)
    def infinite_distinct():
        n = 0
        while True:
            yield f"asset-{n}.txt", "x"
            n += 1
    with pytest.raises(ValueError, match="count"):
        builder.build_zip({
            "build_id": "distinct",
            "generated_files_factory": infinite_distinct,
        })
    assert not (artifact_root / "distinct.zip").exists()
