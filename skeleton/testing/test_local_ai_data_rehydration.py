"""Physical-byte-only restore rehearsal: independent exact archive and destination hashes.

Synthetic host filesystem fixtures; no Docker daemon, database server or
model. A successful byte copy explicitly MUST NOT imply MongoDB, SQLite,
Chroma, source-epoch, writer-quiescence or application recovery qualification.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

from scripts import local_ai_cold_backup as cold
from scripts import local_ai_data_rehydration as recovery
from scripts import local_ai_volume_copy as worker

ROLES = ("backend_data", "mongo_config", "mongo_data", "skeleton_data")


def _archive(tmp_path: Path, *, payload: bytes = b"SQLite and Mongo synthetic bytes"):
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    bundle = parent / "cold-archive"
    bundle.mkdir(mode=0o700)
    volumes: dict[str, dict] = {}
    for role in ROLES:
        material = source / role
        material.mkdir(mode=0o700)
        (material / "data").mkdir(mode=0o700)
        (material / "data" / "content.bin").write_bytes(payload + role.encode())
        volumes[role] = worker.copy_volume(role, material, bundle)
    cold._write_receipt(bundle, cold._receipt(volumes, "sha256:" + "a" * 64))
    fingerprint = hashlib.sha256((bundle / cold.RECEIPT).read_bytes()).hexdigest()
    return bundle, fingerprint, parent


def _mock_worker_verification(monkeypatch):
    # Production _source independently verifies source via worker.verify_volume,
    # not a Docker daemon. Keep its real validation enabled.
    pass


def test_rehydration_exact_bytes_and_four_roles(tmp_path, monkeypatch):
    archive, fingerprint, parent = _archive(tmp_path)
    dest = parent / "rehydrated"
    report = recovery.rehearse_byte_restore(
        archive, dest, expected_receipt_sha256=fingerprint,
    )
    assert report["status"] == "all_cold_archive_files_rehydrated_not_database_restored"
    assert report["roles"] == list(ROLES)
    assert report["total_files"] == 4
    assert report["total_bytes"] > 0
    assert report["external_volumes_created"] is False
    assert report["docker_daemon_used"] is False
    assert report["database_process_started"] is False
    assert report["mongo_consistency_verified"] is False
    assert report["sqlite_consistency_verified"] is False
    assert report["cross_store_snapshot_atomic"] is False
    assert report["application_restore_qualified"] is False
    assert report["protected_chat_qualified"] is False
    assert report["release_qualified"] is False
    assert {x.name for x in dest.iterdir()} == set(ROLES) | {recovery.RECEIPT}
    assert dest.stat().st_mode & 0o777 == 0o700
    assert (dest / recovery.RECEIPT).stat().st_mode & 0o777 == 0o600
    assert recovery.verify_rehydration(
        archive, dest, expected_receipt_sha256=fingerprint,
    ) == report


def test_rehydration_refuses_existing_destination_without_mutating(tmp_path):
    archive, fingerprint, parent = _archive(tmp_path)
    dest = parent / "rehydrated"
    dest.mkdir(mode=0o700)
    marker = dest / "my-data.txt"
    marker.write_text("preserve")
    with pytest.raises(cold.host.LocalDockerError, match="unused"):
        recovery.rehearse_byte_restore(archive, dest, expected_receipt_sha256=fingerprint)
    assert marker.read_text() == "preserve"


@pytest.mark.parametrize("bad", ["", "0" * 64, "f" * 63, "Z" * 64])
def test_independent_receipt_fingerprint_required_before_any_write(tmp_path, bad):
    archive, _, parent = _archive(tmp_path)
    dest = parent / "new"
    with pytest.raises(recovery.RestoreRehearsalError, match="independent"):
        recovery.rehearse_byte_restore(archive, dest, expected_receipt_sha256=bad)
    assert not dest.exists()


def test_source_tamper_denied_before_private_destination_creation(tmp_path):
    archive, fingerprint, parent = _archive(tmp_path)
    source = archive / "mongo_data" / "data" / "content.bin"
    source.write_bytes(source.read_bytes() + b"modified")
    dest = parent / "rehydrated"
    with pytest.raises((recovery.RestoreRehearsalError, worker.VolumeCopyError)):
        recovery.rehearse_byte_restore(archive, dest, expected_receipt_sha256=fingerprint)
    assert not dest.exists()


def test_source_symlink_denied_before_target_creation(tmp_path):
    archive, fingerprint, parent = _archive(tmp_path)
    source = archive / "backend_data" / "data" / "content.bin"
    source.unlink()
    source.symlink_to(archive / cold.RECEIPT)
    dest = parent / "rehydrated"
    with pytest.raises((recovery.RestoreRehearsalError, worker.VolumeCopyError)):
        recovery.rehearse_byte_restore(archive, dest, expected_receipt_sha256=fingerprint)
    assert not dest.exists()


def test_destination_tamper_fails_independent_verify(tmp_path):
    archive, fingerprint, parent = _archive(tmp_path)
    dest = parent / "rehydrated"
    recovery.rehearse_byte_restore(archive, dest, expected_receipt_sha256=fingerprint)
    row = dest / "mongo_data" / "data" / "content.bin"
    row.write_bytes(row.read_bytes() + b"corrupt")
    with pytest.raises(recovery.RestoreRehearsalError, match="digest"):
        recovery.verify_rehydration(archive, dest,
                                   expected_receipt_sha256=fingerprint)


def test_destination_additional_payload_denied(tmp_path):
    archive, fingerprint, parent = _archive(tmp_path)
    dest = parent / "rehydrated"
    recovery.rehearse_byte_restore(archive, dest, expected_receipt_sha256=fingerprint)
    (dest / "mongo_config" / "extra").write_bytes(b"forbidden")
    with pytest.raises(recovery.RestoreRehearsalError, match="unindexed"):
        recovery.verify_rehydration(archive, dest,
                                   expected_receipt_sha256=fingerprint)


def test_malicious_source_file_cannot_escape_rehearsal(tmp_path):
    archive, fingerprint, parent = _archive(tmp_path)
    dest = parent / "rehydrated"
    # Archive verification must fail if the indexed path is tampered, even
    # when the source file bytes remain identical.
    manifest = archive / "mongo_config" / worker.MANIFEST
    content = manifest.read_bytes()
    assert b"data/content.bin" in content
    manifest.write_bytes(content.replace(b"data/content.bin", b"../escaping.bin"))
    with pytest.raises((recovery.RestoreRehearsalError, worker.VolumeCopyError)):
        recovery.rehearse_byte_restore(archive, dest, expected_receipt_sha256=fingerprint)
    assert not dest.exists()


def test_partial_destination_preserved_without_receipt(tmp_path, monkeypatch):
    archive, fingerprint, parent = _archive(tmp_path)
    target = parent / "rehydrated"
    original = recovery._rehydrate_one
    attempts = 0

    def break_after_one(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise recovery.RestoreRehearsalError("injected physical write interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(recovery, "_rehydrate_one", break_after_one)
    with pytest.raises(recovery.RestoreRehearsalError, match="incomplete"):
        recovery.rehearse_byte_restore(archive, target,
                                      expected_receipt_sha256=fingerprint)
    assert target.exists()
    assert not (target / recovery.RECEIPT).exists()
    assert (target / "backend_data" / "data" / "content.bin").exists()


def test_receipt_escalation_rejected_after_copy(tmp_path):
    archive, fingerprint, parent = _archive(tmp_path)
    target = parent / "rehydrated"
    recovery.rehearse_byte_restore(archive, target,
                                  expected_receipt_sha256=fingerprint)
    receipt = target / recovery.RECEIPT
    import json
    changed = json.loads(receipt.read_text())
    changed["application_restore_qualified"] = True
    receipt.write_text(json.dumps(changed))
    with pytest.raises(recovery.RestoreRehearsalError, match="receipt"):
        recovery.verify_rehydration(archive, target,
                                    expected_receipt_sha256=fingerprint)


def test_private_output_parent_required(tmp_path):
    archive, fingerprint, parent = _archive(tmp_path)
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(cold.host.LocalDockerError):
        recovery.rehearse_byte_restore(archive, public / "dest",
                                      expected_receipt_sha256=fingerprint)
    assert not (public / "dest").exists()
