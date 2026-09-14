from dataclasses import replace
from datetime import UTC, datetime
import json

import pytest

from core.worm_audit import AuditEntry, AuditIntegrityError, GENESIS_HASH, WormAuditLog, compute_hash, verify_entries


def test_append_is_chained_and_restores(tmp_path):
    ledger = WormAuditLog(tmp_path)
    first = ledger.append(kind="request", seal="alpha", principal="user-1", route="/api/build", detail="admitted",
                          ts=datetime(2026, 9, 14, 0, 0, tzinfo=UTC))
    second = ledger.append(kind="decision", seal="beta", principal="user-1", route="/api/build", detail="completed",
                           ts=datetime(2026, 9, 14, 0, 1, tzinfo=UTC))
    assert first.seq == 1 and first.prev_hash == GENESIS_HASH and first.hash == compute_hash(first)
    assert second.seq == 2 and second.prev_hash == first.hash and ledger.verify() == second
    restored = WormAuditLog(tmp_path)
    assert restored.sequence == 2 and restored.latest == second


def test_two_instances_interleave_without_forking_ancestry(tmp_path):
    left = WormAuditLog(tmp_path)
    right = WormAuditLog(tmp_path)
    one = left.append(kind="one", seal="s", principal="p", route="/x", detail="1")
    two = right.append(kind="two", seal="s", principal="p", route="/x", detail="2")
    three = left.append(kind="three", seal="s", principal="p", route="/x", detail="3")
    assert (one.seq, two.seq, three.seq) == (1, 2, 3)
    assert two.prev_hash == one.hash
    assert three.prev_hash == two.hash
    assert left.sequence == right.sequence == 3
    assert left.latest == right.latest == three
    assert left.entries() == (one, two, three)


def test_audit_health_exposes_verified_process_safe_chain(tmp_path):
    ledger = WormAuditLog(tmp_path)
    ledger.append(kind="event", seal="s", principal="p", route="/x", detail="ok")
    health = ledger.health()
    assert health["verified"] is True
    assert health["cross_process_locking"] is True
    assert health["sequence"] == 1
    assert health["head"] == ledger.latest.hash
    assert health["lock_backend"] in {"fcntl", "msvcrt"}


def test_history_projection_is_verified_and_tail_limited(tmp_path):
    ledger = WormAuditLog(tmp_path)
    entries = [ledger.append(kind="event", seal="s", principal="p", route="/x", detail=str(index)) for index in range(4)]
    assert ledger.entries() == tuple(entries)
    assert ledger.entries(limit=2) == tuple(entries[-2:])
    assert ledger.entries(limit=0) == ()
    with pytest.raises(ValueError, match="limit"): ledger.entries(limit=-1)


def test_naive_timestamp_is_rejected(tmp_path):
    ledger = WormAuditLog(tmp_path)
    with pytest.raises(ValueError, match="timezone-aware"):
        ledger.append(kind="request", seal="s", principal="p", route="/x", detail="bad-time", ts=datetime(2026, 9, 14, 0, 0))
    assert ledger.sequence == 0


def test_tampered_detail_fails_closed_on_restore(tmp_path):
    ledger = WormAuditLog(tmp_path)
    ledger.append(kind="decision", seal="seal", principal="operator", route="/gate", detail="allow")
    record = json.loads(ledger.path.read_text(encoding="utf-8")); record["detail"] = "deny"
    ledger.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(AuditIntegrityError, match="audit hash broken at seq 1"): WormAuditLog(tmp_path)


def test_history_projection_fails_closed_if_disk_is_tampered_after_open(tmp_path):
    ledger = WormAuditLog(tmp_path)
    ledger.append(kind="decision", seal="seal", principal="p", route="/x", detail="ok")
    record = json.loads(ledger.path.read_text(encoding="utf-8")); record["principal"] = "attacker"
    ledger.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(AuditIntegrityError, match="audit hash broken"): ledger.entries()


def test_broken_predecessor_fails_closed(tmp_path):
    ledger = WormAuditLog(tmp_path)
    first = ledger.append(kind="request", seal="one", principal="p", route="/x", detail="one")
    second = AuditEntry(seq=2, ts=datetime.now(UTC).isoformat(), kind="request", seal="two", principal="p", route="/x",
                        detail="two", prev_hash="not-the-first-hash")
    second = replace(second, hash=compute_hash(second))
    with pytest.raises(AuditIntegrityError, match="audit predecessor broken at seq 2"): verify_entries([first, second])


def test_sequence_gap_fails_closed(tmp_path):
    ledger = WormAuditLog(tmp_path)
    first = ledger.append(kind="request", seal="one", principal="p", route="/x", detail="one")
    skipped = AuditEntry(seq=3, ts=datetime.now(UTC).isoformat(), kind="request", seal="three", principal="p", route="/x",
                         detail="three", prev_hash=first.hash)
    skipped = replace(skipped, hash=compute_hash(skipped))
    with pytest.raises(AuditIntegrityError, match="expected 2"): verify_entries([first, skipped])


def test_unreadable_json_fails_closed(tmp_path):
    (tmp_path / "worm.log").write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(AuditIntegrityError, match="unreadable at line 1"): WormAuditLog(tmp_path)


def test_blank_lines_are_ignored(tmp_path):
    ledger = WormAuditLog(tmp_path)
    entry = ledger.append(kind="request", seal="one", principal="p", route="/x", detail="one")
    ledger.path.write_text("\n" + ledger.path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert WormAuditLog(tmp_path).latest == entry
