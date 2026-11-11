"""Adversarial APK publication tests without a real SDK or live database."""
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
    monkeypatch.setattr(builder, "_have_full_apk_toolchain", lambda: False)
    return root


def test_fallback_apk_is_published_atomically_with_actual_content_digest(artifact_root):
    result = builder.build_apk({
        "build_id": "tenant-bound-abc",
        "generated_files": {"index.html": "<p>hello</p>"},
    })
    archive = artifact_root / "tenant-bound-abc.apk"
    assert archive.exists()
    assert result["path"] == str(archive)
    assert result["size_bytes"] == archive.stat().st_size
    assert result["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert result["is_installable"] is False
    assert result["is_real_apk"] is False
    with zipfile.ZipFile(archive) as jar:
        assert jar.read("assets/galaxy/index.html") == b"<p>hello</p>"
        assert jar.read("META-INF/CODEDOCK.SF")
    assert not list(artifact_root.glob(".vault-part-*"))


def test_failed_rebuild_does_not_replace_existing_apk(artifact_root):
    builder.build_apk({"build_id": "stable", "generated_files": {"first.txt": "ok"}})
    path = artifact_root / "stable.apk"
    before = path.read_bytes()

    def interrupted():
        yield "new.txt", "new"
        raise RuntimeError("aborted generator")

    with pytest.raises(RuntimeError, match="aborted generator"):
        builder.build_apk({"build_id": "stable", "generated_files_factory": interrupted})
    assert path.read_bytes() == before
    assert not list(artifact_root.glob(".vault-part-*"))


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX openat")
def test_existing_symlink_cannot_redirect_published_apk(artifact_root, tmp_path):
    outside = tmp_path / "secret"
    outside.write_bytes(b"must-not-overwrite")
    (artifact_root / "hostile.apk").symlink_to(outside)
    with pytest.raises((VaultPathError, OSError)):
        builder.build_apk({"build_id": "hostile", "generated_files": {"a": "b"}})
    assert outside.read_bytes() == b"must-not-overwrite"
    assert (artifact_root / "hostile.apk").is_symlink()


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX openat")
def test_existing_hardlink_cannot_be_overwritten(artifact_root, tmp_path):
    outside = tmp_path / "secret"
    outside.write_bytes(b"must-not-overwrite")
    os.link(outside, artifact_root / "hardlink.apk")
    with pytest.raises(VaultPathError):
        builder.build_apk({"build_id": "hardlink", "generated_files": {"a": "b"}})
    assert outside.read_bytes() == b"must-not-overwrite"


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX openat")
def test_symlinked_artifact_root_is_denied(artifact_root, tmp_path, monkeypatch):
    link = tmp_path / "linked-artifacts"
    link.symlink_to(artifact_root, target_is_directory=True)
    monkeypatch.setattr(builder, "ARTIFACTS_ROOT", link)
    with pytest.raises((VaultPathError, OSError)):
        builder.build_apk({"build_id": "bad", "generated_files": {"a": "b"}})
    assert not (artifact_root / "bad.apk").exists()


def test_size_budget_fails_before_publication(artifact_root, monkeypatch):
    monkeypatch.setattr(builder, "_MAX_ZIP_OUTPUT_BYTES", 8)
    with pytest.raises(VaultPathError, match="byte budget"):
        builder.build_apk({"build_id": "oversized", "generated_files": {"a": "content"}})
    assert not (artifact_root / "oversized.apk").exists()


def test_real_toolchain_stage_publishes_without_opening_public_path(artifact_root, monkeypatch):
    monkeypatch.setattr(builder, "_have_full_apk_toolchain", lambda: True)
    stage_paths = []

    def fake_signed_apk(_build, stage):
        stage_paths.append(stage)
        with zipfile.ZipFile(stage, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"MainActivity")
            archive.writestr("classes.dex", b"verified")
        return 2, 10, "verified", True

    monkeypatch.setattr(builder, "_build_real_apk", fake_signed_apk)
    response = builder.build_apk({"build_id": "native-safe"})
    public_path = artifact_root / "native-safe.apk"
    assert len(stage_paths) == 1
    assert stage_paths[0] != public_path
    assert stage_paths[0].parent != public_path.parent
    assert not stage_paths[0].exists()
    assert public_path.is_file()
    assert response["is_real_apk"] is True
    assert response["is_installable"] is True
    assert response["sha256"] == hashlib.sha256(public_path.read_bytes()).hexdigest()


def test_staged_bytes_are_reverified_inside_atomic_writer(artifact_root, monkeypatch):
    monkeypatch.setattr(builder, "_have_full_apk_toolchain", lambda: True)

    def fake_signed_apk(_build, stage):
        with zipfile.ZipFile(stage, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"MainActivity")
            archive.writestr("classes.dex", b"verified")
        return 2, 10, "verified", True

    monkeypatch.setattr(builder, "_build_real_apk", fake_signed_apk)
    original_atomic = builder.atomic_write

    def tamper_before_copy(directory, filename, writer, *, max_bytes):
        def evil_writer(destination):
            # Deliberately simulate a corrupted stage by feeding fewer bytes
            # than the measured size through the already pinned writer.
            class DropOneByte:
                def write(self, payload):
                    return destination.write(payload[:-1] if payload else payload)
            return writer(DropOneByte())
        return original_atomic(directory, filename, evil_writer, max_bytes=max_bytes)

    # The stage hash verification covers bytes read; the downstream atomic
    # writer still bounds output, even when the file sink is faulty.
    # Use a deliberate application writer failure instead of assuming
    # arbitrary alternate sinks preserve original file bytes.
    monkeypatch.setattr(builder, "atomic_write", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk-full")))
    with pytest.raises(OSError, match="disk-full"):
        builder.build_apk({"build_id": "atomic-failure"})
    assert not (artifact_root / "atomic-failure.apk").exists()
