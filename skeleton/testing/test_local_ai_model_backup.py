"""Physical byte-custody tests for operator-owned local Jeeves model backups.

These are not GGUF inference, credential-provider, live Docker, or recovery tests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.local_ai_model_backup import (
    MANIFEST, RECEIPT, ModelBackupError, backup_model, inventory, verify_backup,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _source(tmp_path: Path, *, libraries: bool = False) -> Path:
    root = tmp_path / "local-ai"
    (root / "models").mkdir(parents=True)
    (root / "runtime").mkdir()
    model_bytes = b"GGUF" + bytes(range(256)) * 3
    executable_bytes = b"ELF local test executable fake, never run"
    (root / "models" / "model.gguf").write_bytes(model_bytes)
    (root / "runtime" / "llama-cli").write_bytes(executable_bytes)
    payload = {
        "schema_version": "skeleton.local_model.deployment.v1",
        "runtime_kind": "llama.cpp-cli",
        "model_id": "jeeves",
        "model_path": "/app/local-ai/models/model.gguf",
        "model_sha256": _sha(model_bytes),
        "executable_path": "/app/local-ai/runtime/llama-cli",
        "executable_sha256": _sha(executable_bytes),
        "config": {"context_size": 4096, "gpu_layers": 0},
    }
    if libraries:
        name = "libggml.so"
        artifact = b"library bytes for offline custody tests"
        (root / "runtime" / name).write_bytes(artifact)
        payload["runtime_libraries"] = {name: _sha(artifact)}
    (root / MANIFEST).write_text(json.dumps(payload, sort_keys=True) + "\n")
    return root


@pytest.mark.parametrize("libraries,count", [(False, 3), (True, 4)])
def test_backups_copy_complete_pinned_model_bytes(
    tmp_path: Path, libraries: bool, count: int,
) -> None:
    root = _source(tmp_path, libraries=libraries)
    original = [(x["path"], x["sha256"]) for x in inventory(root)]
    destination = tmp_path / "immutable-backup"
    record = backup_model(root, destination)
    verified = verify_backup(destination)
    assert verified["verified"] is True
    assert verified["file_count"] == count
    assert record["application_state_included"] is False
    assert record["inference_executed"] is False
    assert record["device_qualified"] is False
    assert [(x["path"], x["sha256"]) for x in record["files"]] == original
    assert (destination / RECEIPT).is_file()
    assert (destination / "models" / "model.gguf").read_bytes() == (
        root / "models" / "model.gguf"
    ).read_bytes()


def test_backup_immutability_preserves_live_source(tmp_path: Path) -> None:
    root = _source(tmp_path)
    before = [(x["path"], x["sha256"]) for x in inventory(root)]
    backup_model(root, tmp_path / "backup")
    after = [(x["path"], x["sha256"]) for x in inventory(root)]
    assert before == after
    with pytest.raises(ModelBackupError, match="existing"):
        backup_model(root, tmp_path / "backup")


def test_unpinned_runtime_shared_library_denies_backup(tmp_path: Path) -> None:
    root = _source(tmp_path)
    (root / "runtime" / "libunlisted.so").write_bytes(b"unreviewed library")
    with pytest.raises(ModelBackupError, match="not fully pinned"):
        inventory(root)


def test_modified_model_fails_before_creating_backup_folder(tmp_path: Path) -> None:
    root = _source(tmp_path)
    (root / "models" / "model.gguf").write_bytes(b"changed weights")
    with pytest.raises(ModelBackupError, match="differs"):
        backup_model(root, tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()


@pytest.mark.parametrize("key", ["model_path", "executable_path"])
@pytest.mark.parametrize("escape", [
    "/etc/passwd", "/app/local-ai/../escape",
    "/app/local-ai//models/model.gguf",
    "/app/local-ai/models/./model.gguf",
])
def test_unsafe_pinned_paths_never_escape_mount(
    tmp_path: Path, key: str, escape: str,
) -> None:
    root = _source(tmp_path)
    manifest = root / MANIFEST
    data = json.loads(manifest.read_text())
    data[key] = escape
    manifest.write_text(json.dumps(data))
    with pytest.raises(ModelBackupError):
        inventory(root)


def test_nested_symlink_denied_even_if_target_is_inside_mount(tmp_path: Path) -> None:
    root = _source(tmp_path)
    model = root / "models" / "model.gguf"
    model.rename(root / "models" / "original.gguf")
    model.symlink_to("original.gguf")
    with pytest.raises(ModelBackupError):
        backup_model(root, tmp_path / "uncreated")
    assert not (tmp_path / "uncreated").exists()


def test_hardlinked_model_denied(tmp_path: Path) -> None:
    root = _source(tmp_path)
    (root / "models" / "original.gguf").hardlink_to(root / "models" / "model.gguf")
    with pytest.raises(ModelBackupError, match="private regular file"):
        inventory(root)


def test_receipt_and_copied_bytes_are_verified_independently(tmp_path: Path) -> None:
    root = _source(tmp_path)
    destination = tmp_path / "model-custody"
    backup_model(root, destination)
    saved = (destination / "models" / "model.gguf")
    saved.chmod(0o600)
    saved.write_bytes(saved.read_bytes() + b"tampering")
    with pytest.raises(ModelBackupError, match="byte identity"):
        verify_backup(destination)


def test_rewritten_receipt_does_not_authorize_existing_copy(tmp_path: Path) -> None:
    root = _source(tmp_path)
    destination = tmp_path / "copy"
    backup_model(root, destination)
    receipt = destination / RECEIPT
    receipt.chmod(0o600)
    payload = json.loads(receipt.read_text())
    payload["status"] = "application_fully_restored"
    receipt.write_text(json.dumps(payload))
    with pytest.raises(ModelBackupError, match="receipt identity"):
        verify_backup(destination)


def test_partial_copy_without_receipt_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "partial"
    target.mkdir()
    (target / "models").mkdir()
    (target / "models" / "model.gguf").write_bytes(b"not a backup")
    with pytest.raises((ModelBackupError, OSError)):
        verify_backup(target)


def test_backup_refuses_subdirectory_inside_live_model_mount(tmp_path: Path) -> None:
    root = _source(tmp_path)
    with pytest.raises(ModelBackupError, match="outside"):
        backup_model(root, root / "backup")
    assert not (root / "backup").exists()


def test_extra_files_in_archive_do_not_validate(tmp_path: Path) -> None:
    root = _source(tmp_path)
    target = tmp_path / "snapshot"
    backup_model(root, target)
    (target / "extra.json").write_text("not pinned")
    with pytest.raises(ModelBackupError, match="undeclared"):
        verify_backup(target)


def test_manifest_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    root = _source(tmp_path)
    value = (root / MANIFEST).read_text()
    (root / MANIFEST).write_text(value.replace('"model_id": "jeeves"', '"model_id": "jeeves", "model_id": "another"'))
    with pytest.raises(ModelBackupError, match="duplicate"):
        inventory(root)


def test_no_model_backup_can_masquerade_as_application_recovery(tmp_path: Path) -> None:
    root = _source(tmp_path)
    record = backup_model(root, tmp_path / "backup")
    assert record["status"] == "model_artifacts_copied_not_application_recovered"
    assert record["archive_kind"] == "offline_model_only"
    assert verify_backup(tmp_path / "backup")["application_state_included"] is False


def test_forged_receipt_cannot_rebind_original_manifest_to_wrong_weights(tmp_path: Path) -> None:
    root = _source(tmp_path)
    target = tmp_path / "reconcile"
    backup_model(root, target)
    model_manifest = target / MANIFEST
    model_manifest.chmod(0o600)
    data = json.loads(model_manifest.read_text())
    data["model_sha256"] = "a" * 64
    model_manifest.write_text(json.dumps(data, sort_keys=True) + "\n")
    receipt_path = target / RECEIPT
    receipt_path.chmod(0o600)
    record = json.loads(receipt_path.read_text())
    for entry in record["files"]:
        if entry["path"] == MANIFEST:
            entry["sha256"] = _sha(model_manifest.read_bytes())
            record["total_bytes"] += model_manifest.stat().st_size - entry["bytes"]
            entry["bytes"] = model_manifest.stat().st_size
    record.pop("receipt_sha256")
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    record["receipt_sha256"] = _sha(canonical.encode())
    receipt_path.write_text(json.dumps(record, sort_keys=True))
    with pytest.raises(ModelBackupError, match="manifest digest"):
        verify_backup(target)


def test_extra_empty_directory_cannot_hide_in_model_backup(tmp_path: Path) -> None:
    root = _source(tmp_path)
    target = tmp_path / "copy"
    backup_model(root, target)
    (target / "not-declared").mkdir()
    with pytest.raises(ModelBackupError, match="undeclared"):
        verify_backup(target)
