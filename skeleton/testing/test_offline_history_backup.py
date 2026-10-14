"""Portable offline transcript recovery: bounded, atomic, model-pinned and non-authoritative."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import os

import pytest

from skeleton.app.offline_history import (
    BACKUP_SCHEMA,
    MAX_BACKUP_BYTES,
    OfflineHistoryError,
    backup_history,
    restore_history,
)
from skeleton.app.local_ai import OfflineAIError, OfflineAISession
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer


MODEL = "a" * 64
TURNS = (("user", "hello"), ("assistant", "offline answer"))


def test_manual_backup_survives_restart_and_preserves_exact_turns(tmp_path: Path) -> None:
    path = tmp_path / "chat.json"
    checksum = backup_history(path, MODEL, TURNS)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["payload"]["schema_version"] == BACKUP_SCHEMA
    assert data["sha256"] == checksum
    assert restore_history(path, MODEL) == TURNS
    assert not path.is_symlink()
    if os.name == "posix":
        assert (path.stat().st_mode & 0o077) == 0


def test_wrong_model_never_reuses_stored_context(tmp_path: Path) -> None:
    path = tmp_path / "chat.json"
    backup_history(path, MODEL, TURNS)
    with pytest.raises(OfflineHistoryError, match="another model"):
        restore_history(path, "b" * 64)


def test_corrupt_and_duplicate_key_backups_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "chat.json"
    backup_history(path, MODEL, TURNS)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["payload"]["history"][1][1] = "tampered"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(OfflineHistoryError, match="checksum mismatch"):
        restore_history(path, MODEL)
    path.write_text('{"sha256":"a","sha256":"b","payload":{}}', encoding="utf-8")
    with pytest.raises(OfflineHistoryError, match="duplicate JSON"):
        restore_history(path, MODEL)


@pytest.mark.parametrize("invalid", [
    (("user", "orphan"),),
    (("assistant", "wrong role"), ("user", "wrong role")),
    (("user", ""), ("assistant", "answer")),
    (("user", "x" * 4097), ("assistant", "answer")),
    (("user", "x\x00"), ("assistant", "answer")),
    (("user", "hello"), ("assistant", "a" * 65537)),
])
def test_incomplete_or_malformed_history_never_persists(
    tmp_path: Path, invalid
) -> None:
    path = tmp_path / "chat.json"
    with pytest.raises(OfflineHistoryError):
        backup_history(path, MODEL, invalid)
    assert not path.exists()


def test_backup_failure_never_destroys_existing_data(tmp_path: Path) -> None:
    path = tmp_path / "chat.json"
    backup_history(path, MODEL, TURNS)
    before = path.read_bytes()
    with pytest.raises(OfflineHistoryError):
        backup_history(path, MODEL, (("user", "unfinished"),))
    assert path.read_bytes() == before


def test_oversized_and_symlink_backups_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "huge.json"
    path.write_bytes(b"x" * (MAX_BACKUP_BYTES + 1))
    with pytest.raises(OfflineHistoryError, match="maximum file size|bounded"):
        restore_history(path, MODEL)
    target = tmp_path / "target.json"
    backup_history(target, MODEL, TURNS)
    symlink = tmp_path / "link.json"
    try:
        symlink.symlink_to(target)
    except OSError:
        pytest.skip("host disallows symlinks")
    with pytest.raises(OfflineHistoryError, match="symlink"):
        restore_history(symlink, MODEL)
    with pytest.raises(OfflineHistoryError, match="symlink"):
        backup_history(symlink, MODEL, TURNS)


def _native_session() -> OfflineAISession:
    model = TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
        dim=8, ctx=64, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )
    return OfflineAISession(NativeRuntimeLocalModel(NativeLLMRuntime(model)))


@pytest.mark.asyncio
async def test_native_session_restarts_from_explicit_backup(tmp_path: Path) -> None:
    first = _native_session()
    await first.ask("hello", max_output_tokens=2)
    path = tmp_path / "native.json"
    first.save_history_backup(path)
    restored = _native_session()
    assert restored.restore_history_backup(path) == 1
    assert restored.history == first.history
    with pytest.raises(OfflineAIError, match="new conversation"):
        restored.restore_history_backup(path)
    await restored.ask("hello", max_output_tokens=2)
    assert len(restored.history) == 4
    assert len(first.history) == 2


@pytest.mark.asyncio
async def test_native_session_cannot_restore_wrong_checkpoint(tmp_path: Path) -> None:
    first = _native_session()
    await first.ask("hello", max_output_tokens=2)
    path = tmp_path / "native.json"
    first.save_history_backup(path)
    different = OfflineAISession(NativeRuntimeLocalModel(NativeLLMRuntime(
        TinyTransformer(
            vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
            dim=8, ctx=64, seed=52, n_heads=2, n_layers=2, d_ff=16,
        )
    )))
    with pytest.raises(OfflineHistoryError, match="another model"):
        different.restore_history_backup(path)
    assert different.history == ()
