"""Safe physical byte-copy qualification for restoring an operator-pinned local model.

These tests never start Docker, download weights, execute GGUF or rewrite the
live model mount. Application/DB recovery and protected chat are held.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.local_ai_model_backup import (
    MANIFEST, ModelBackupError, backup_model, inventory, verify_backup,
)
from scripts.local_ai_model_restore import (
    RECEIPT, restore_model_backup, verify_restore,
)


def _prepared(tmp_path: Path, *, libs: bool = False):
    active = tmp_path / "active-model"
    model = active / "models"
    runtime = active / "runtime"
    model.mkdir(parents=True)
    runtime.mkdir()
    weights = b"GGUF" + bytes(range(128)) * 16
    exe = b"ELF TEST ONLY; never invoke"
    (model / "jeeves.gguf").write_bytes(weights)
    (runtime / "llama-cli").write_bytes(exe)
    digest = lambda x: hashlib.sha256(x).hexdigest()
    pins = {
        "schema_version": "skeleton.local_model.deployment.v1",
        "runtime_kind": "llama.cpp-cli",
        "model_id": "jeeves",
        "model_path": "/app/local-ai/models/jeeves.gguf",
        "model_sha256": digest(weights),
        "executable_path": "/app/local-ai/runtime/llama-cli",
        "executable_sha256": digest(exe),
        "config": {"context_size": 4096, "gpu_layers": 0},
    }
    if libs:
        lib = b"native library test data; never dynamically loaded"
        (runtime / "libggml.so").write_bytes(lib)
        pins["runtime_libraries"] = {"libggml.so": digest(lib)}
    (active / MANIFEST).write_text(json.dumps(pins, sort_keys=True) + "\n")
    backup = tmp_path / "backup"
    backup_model(active, backup)
    return active, backup


@pytest.mark.parametrize("libs,count", [(False, 3), (True, 4)])
def test_restore_into_new_private_mount_preserves_every_pinned_byte(
    tmp_path: Path, libs: bool, count: int,
):
    active, backup = _prepared(tmp_path, libs=libs)
    before = inventory(active)
    archived = verify_backup(backup)
    new = tmp_path / "restored"
    result = restore_model_backup(backup, new)
    assert result["verified"] is True
    assert result["file_count"] == count
    assert result["source_backup_receipt_sha256"] == archived["receipt_sha256"]
    assert result["application_state_restored"] is False
    assert result["chat_guard_qualified"] is False
    assert result["device_qualified"] is False
    assert result["inference_executed"] is False
    assert inventory(active) == inventory(new) == before
    assert (new / RECEIPT).is_file()
    assert (new / "runtime" / "llama-cli").stat().st_mode & 0o100
    assert verify_restore(new) == result


def test_existing_target_never_overwritten_even_when_empty(tmp_path: Path):
    _, backup = _prepared(tmp_path)
    existing = tmp_path / "live-target"
    existing.mkdir()
    (existing / "evidence.txt").write_text("operator-owned data")
    with pytest.raises(ModelBackupError, match="new"):
        restore_model_backup(backup, existing)
    assert (existing / "evidence.txt").read_text() == "operator-owned data"


def test_target_cannot_overlap_archive_or_enter_through_symlink(tmp_path: Path):
    _, backup = _prepared(tmp_path)
    with pytest.raises(ModelBackupError, match="overlap"):
        restore_model_backup(backup, backup / "nested")
    parent_link = tmp_path / "fake-parent"
    parent_link.symlink_to(backup, target_is_directory=True)
    with pytest.raises(ModelBackupError):
        restore_model_backup(backup, parent_link / "another")


def test_invalid_backup_fails_before_creating_any_target(tmp_path: Path):
    _, backup = _prepared(tmp_path)
    # Backup artifacts are intentionally sealed read-only (0400). Make only
    # this isolated fixture writable before simulating post-backup tampering;
    # never weaken production backup permissions or verification.
    archived_model = backup / "models" / "jeeves.gguf"
    archived_model.chmod(0o600)
    archived_model.write_bytes(b"forged weights")
    candidate = tmp_path / "never-created"
    with pytest.raises(ModelBackupError):
        restore_model_backup(backup, candidate)
    assert not candidate.exists()


def test_partial_or_tampered_restored_source_is_not_accepted(tmp_path: Path):
    _, backup = _prepared(tmp_path)
    restored = tmp_path / "restored"
    restore_model_backup(backup, restored)
    binary = restored / "runtime" / "llama-cli"
    binary.write_bytes(b"corrupt")
    with pytest.raises(ModelBackupError):
        verify_restore(restored)


def test_unknown_or_symlinked_artifacts_cannot_hide_in_completed_restore(tmp_path: Path):
    _, backup = _prepared(tmp_path)
    restored = tmp_path / "restored"
    restore_model_backup(backup, restored)
    (restored / "extras").mkdir()
    (restored / "extras" / "unknown.txt").write_text("unreviewed")
    with pytest.raises(ModelBackupError, match="undeclared"):
        verify_restore(restored)
    (restored / "extras" / "unknown.txt").unlink()
    (restored / "extras").rmdir()
    (restored / "hidden").symlink_to(restored / "models", target_is_directory=True)
    with pytest.raises(ModelBackupError, match="undeclared"):
        verify_restore(restored)


def test_rewritten_receipt_does_not_confer_application_recovery(tmp_path: Path):
    _, backup = _prepared(tmp_path)
    restored = tmp_path / "restored"
    restore_model_backup(backup, restored)
    receipt = restored / RECEIPT
    doc = json.loads(receipt.read_text())
    doc["application_state_restored"] = True
    receipt.write_text(json.dumps(doc))
    with pytest.raises(ModelBackupError, match="receipt authority"):
        verify_restore(restored)


def test_restore_does_not_touch_source_mount_or_backup(tmp_path: Path):
    active, backup = _prepared(tmp_path)
    initial_active = inventory(active)
    initial_backup = verify_backup(backup)
    restore_model_backup(backup, tmp_path / "restored")
    assert inventory(active) == initial_active
    assert verify_backup(backup) == initial_backup
