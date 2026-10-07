"""Regression coverage for vault audit durability and restore boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.vault import AuditLog
from skeleton.vault.audit import AuditChainBroken


def test_persist_happens_before_in_memory_chain_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "worm_audit.jsonl"
    log = AuditLog.open(path)
    observed = {}

    def persist(entry) -> None:
        observed["entry"] = entry
        observed["length"] = len(log)
        observed["head"] = log._last_hash

    monkeypatch.setattr(log, "_persist", persist)

    entry = log.append(entry_id="e1", actor="root", action="seal")

    assert observed == {"entry": entry, "length": 0, "head": None}
    assert len(log) == 1
    assert log._last_hash == entry.hash


def test_persist_failure_keeps_memory_unchanged_and_poisoned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "worm_audit.jsonl"
    log = AuditLog.open(path)

    def fail_persist(_entry) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(log, "_persist", fail_persist)

    with pytest.raises(OSError, match="disk full"):
        log.append(entry_id="e1", actor="root", action="seal")

    assert len(log) == 0
    assert log._last_hash is None

    with pytest.raises(AuditChainBroken, match="reopen the ledger"):
        log.append(entry_id="e2", actor="root", action="seal")


def test_restore_false_existing_ledger_refuses_append(tmp_path: Path) -> None:
    path = tmp_path / "worm_audit.jsonl"
    initial = AuditLog.open(path)
    initial.append(entry_id="e1", actor="root", action="seal")

    unverified = AuditLog(path=path, restore=False)
    with pytest.raises(AuditChainBroken, match="restore was disabled"):
        unverified.append(entry_id="e2", actor="root", action="unseal")

    reopened = AuditLog.open(path)
    second = reopened.append(entry_id="e2", actor="root", action="unseal")

    assert second.previous_hash == reopened._entries[0].hash
    reopened.verify_chain_or_refuse()


def test_invalid_utf8_refuses_open_with_audit_error(tmp_path: Path) -> None:
    path = tmp_path / "worm_audit.jsonl"
    path.write_bytes(b"\xff\n")

    with pytest.raises(AuditChainBroken, match="unreadable"):
        AuditLog.open(path)


def test_append_snapshots_nested_metadata(tmp_path: Path) -> None:
    path = tmp_path / "worm_audit.jsonl"
    metadata = {"nested": {"values": [1, 2]}}

    log = AuditLog.open(path)
    entry = log.append(
        entry_id="e1",
        actor="root",
        action="access",
        metadata=metadata,
    )

    metadata["nested"]["values"].append(3)

    assert entry.metadata == {"nested": {"values": [1, 2]}}
    assert log.tamper_check() == (True, -1)

    restored = AuditLog.open(path)
    assert restored._entries[0].metadata == {"nested": {"values": [1, 2]}}
    restored.verify_chain_or_refuse()
