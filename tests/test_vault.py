"""Smoke + WORM refuse-on-boot tests for the secrets vault subsystem."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.vault import AuditLog, ShamirSeal
from skeleton.vault.audit import AuditChainBroken, verify_chain_or_refuse


class TestVault:
    def test_audit_log_constructs(self):
        assert AuditLog() is not None

    def test_shamir_constructs(self):
        assert ShamirSeal() is not None


class TestWormRefuseOnBoot:
    """Sibling of Zaibatsu.Gate WormAuditLog — broken chain refuses start."""

    def _append_two(self, log: AuditLog) -> None:
        log.append(entry_id="e1", actor="root", action="seal", outcome="success")
        log.append(entry_id="e2", actor="root", action="unseal", outcome="success")

    def test_healthy_chain_ok(self, tmp_path: Path):
        path = tmp_path / "worm_audit.jsonl"
        log = AuditLog.open(path)
        self._append_two(log)
        verify_chain_or_refuse(log)
        log.verify_chain_or_refuse()
        # reopen restores durable chain and still passes
        restored = AuditLog.open(path)
        assert len(restored) == 2
        restored.verify_chain_or_refuse()
        assert restored.report()["chain_intact"] is True

    def test_broken_chain_refuses_on_open(self, tmp_path: Path):
        path = tmp_path / "worm_audit.jsonl"
        log = AuditLog.open(path)
        self._append_two(log)
        # Tamper durable ledger: flip a byte in the first record's hash field.
        lines = path.read_text(encoding="utf-8").splitlines()
        raw = json.loads(lines[0])
        raw["hash"] = "0" * 64
        lines[0] = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(AuditChainBroken) as ei:
            AuditLog.open(path)
        assert "refusing to start" in str(ei.value)
        assert ei.value.code == "VLT.AUDIT_CHAIN_BROKEN"

    def test_broken_prev_link_refuses(self, tmp_path: Path):
        path = tmp_path / "worm_audit.jsonl"
        log = AuditLog.open(path)
        self._append_two(log)
        lines = path.read_text(encoding="utf-8").splitlines()
        raw = json.loads(lines[1])
        raw["previous_hash"] = "deadbeef" * 8
        # keep stored hash so recompute/link both fail
        lines[1] = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(AuditChainBroken):
            AuditLog.open(path)

    def test_unreadable_line_refuses(self, tmp_path: Path):
        path = tmp_path / "worm_audit.jsonl"
        path.write_text("{not-json\n", encoding="utf-8")
        with pytest.raises(AuditChainBroken) as ei:
            AuditLog.open(path)
        assert "unreadable" in str(ei.value)

    def test_in_memory_tamper_refuses_via_callable(self):
        log = AuditLog()  # no path
        log.append(entry_id="e1", actor="a", action="access", outcome="success")
        # Mutate internal chain without going through append.
        bad = log._entries[0]
        from skeleton.vault.audit import AuditEntry

        log._entries[0] = AuditEntry(
            entry_id=bad.entry_id,
            actor=bad.actor,
            action=bad.action,
            secret_id=bad.secret_id,
            outcome=bad.outcome,
            metadata=bad.metadata,
            previous_hash=bad.previous_hash,
            hash="ff" * 32,
            timestamp=bad.timestamp,
        )
        with pytest.raises(AuditChainBroken):
            verify_chain_or_refuse(log)

    def test_empty_missing_file_ok(self, tmp_path: Path):
        path = tmp_path / "missing.jsonl"
        log = AuditLog.open(path)
        log.verify_chain_or_refuse()
        assert len(log) == 0
