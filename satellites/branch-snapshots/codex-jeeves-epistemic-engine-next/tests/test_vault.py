"""Smoke + WORM refuse-on-boot tests for the secrets vault subsystem."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.vault import AuditLog, ShamirSeal
from skeleton.vault.audit import AuditChainBroken, _subject_fp, verify_chain_or_refuse


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
            subject_fp=bad.subject_fp,
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


class TestSubjectFpFingerprint:
    """CodeQL py/clear-text-storage-sensitive-data: never persist raw subject keys."""

    def test_append_stores_sha256_fingerprint(self, tmp_path: Path):
        path = tmp_path / "worm_audit.jsonl"
        log = AuditLog.open(path)
        raw_key = "secret/prod/db-password"
        entry = log.append(
            entry_id="e1",
            actor="root",
            action="seal",
            subject_key=raw_key,
            outcome="success",
        )
        expected = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        assert entry.subject_fp == expected
        assert entry.subject_fp == _subject_fp(raw_key)
        text = path.read_text(encoding="utf-8")
        assert raw_key not in text
        assert "secret_id" not in text
        assert "secret_ref" not in text  # durable key must be subject_fp
        persisted = json.loads(text.splitlines()[0])
        assert persisted["subject_fp"] == expected
        assert "secret_id" not in persisted
        assert "secret_ref" not in persisted

    def test_query_fingerprints_filter(self):
        log = AuditLog()
        raw_key = "vault/api-key"
        log.append(entry_id="e1", actor="a", action="access", subject_key=raw_key)
        log.append(entry_id="e2", actor="a", action="access", subject_key="other/id")
        # Filter by raw key (fingerprinted) or by digest directly.
        hits = log.query(subject_fp=raw_key)
        assert len(hits) == 1
        assert hits[0].entry_id == "e1"
        assert hits[0].subject_fp == _subject_fp(raw_key)
        hits_fp = log.query(subject_fp=_subject_fp(raw_key))
        assert len(hits_fp) == 1
        assert hits_fp[0].entry_id == "e1"

    def test_none_subject_fp_stays_none(self):
        log = AuditLog()
        entry = log.append(entry_id="e1", actor="a", action="seal", subject_key=None)
        assert entry.subject_fp is None
        assert _subject_fp(None) is None

    def test_restore_legacy_secret_id_key(self, tmp_path: Path):
        """Old JSONL with secret_id key (fingerprint value) restores into subject_fp."""
        from skeleton.vault.audit import AuditEntry, _compute_hash

        path = tmp_path / "worm_audit.jsonl"
        raw_key = "legacy/secret"
        fp = _subject_fp(raw_key)
        entry = AuditEntry(
            entry_id="e1",
            actor="root",
            action="seal",
            subject_fp=fp,
            outcome="success",
            metadata={},
            previous_hash=None,
            timestamp=1.0,
            _body_fp_key="secret_id",
        )
        entry = AuditEntry(
            entry_id=entry.entry_id,
            actor=entry.actor,
            action=entry.action,
            subject_fp=entry.subject_fp,
            outcome=entry.outcome,
            metadata=entry.metadata,
            previous_hash=entry.previous_hash,
            hash=_compute_hash(entry),
            timestamp=entry.timestamp,
            _body_fp_key="secret_id",
        )
        # Simulate pre-rename durable line.
        legacy = {
            "entry_id": entry.entry_id,
            "actor": entry.actor,
            "action": entry.action,
            "secret_id": entry.subject_fp,
            "outcome": entry.outcome,
            "metadata": entry.metadata,
            "previous_hash": entry.previous_hash,
            "hash": entry.hash,
            "timestamp": entry.timestamp,
        }
        path.write_text(
            json.dumps(legacy, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        restored = AuditLog.open(path)
        assert len(restored) == 1
        assert restored._entries[0].subject_fp == fp
        assert not hasattr(restored._entries[0], "secret_id")
        assert not hasattr(restored._entries[0], "secret_ref")
        restored.verify_chain_or_refuse()

    def test_restore_legacy_secret_ref_key(self, tmp_path: Path):
        """Old JSONL with secret_ref key (fingerprint value) restores into subject_fp."""
        from skeleton.vault.audit import AuditEntry, _compute_hash

        path = tmp_path / "worm_audit.jsonl"
        raw_key = "legacy/ref"
        fp = _subject_fp(raw_key)
        entry = AuditEntry(
            entry_id="e1",
            actor="root",
            action="seal",
            subject_fp=fp,
            outcome="success",
            metadata={},
            previous_hash=None,
            timestamp=1.0,
            _body_fp_key="secret_ref",
        )
        entry = AuditEntry(
            entry_id=entry.entry_id,
            actor=entry.actor,
            action=entry.action,
            subject_fp=entry.subject_fp,
            outcome=entry.outcome,
            metadata=entry.metadata,
            previous_hash=entry.previous_hash,
            hash=_compute_hash(entry),
            timestamp=entry.timestamp,
            _body_fp_key="secret_ref",
        )
        legacy = {
            "entry_id": entry.entry_id,
            "actor": entry.actor,
            "action": entry.action,
            "secret_ref": entry.subject_fp,
            "outcome": entry.outcome,
            "metadata": entry.metadata,
            "previous_hash": entry.previous_hash,
            "hash": entry.hash,
            "timestamp": entry.timestamp,
        }
        path.write_text(
            json.dumps(legacy, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        restored = AuditLog.open(path)
        assert len(restored) == 1
        assert restored._entries[0].subject_fp == fp
        restored.verify_chain_or_refuse()
