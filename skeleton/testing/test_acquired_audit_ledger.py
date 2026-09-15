from __future__ import annotations

import json

import pytest

from skeleton.acquired.audit_ledger import (
    AuditChainError,
    GENESIS_HASH,
    TamperEvidentAuditLog,
)
from skeleton.kernel.events import EventBus


def test_append_restore_and_verify_chain(tmp_path):
    path = tmp_path / "worm.log"
    ledger = TamperEvidentAuditLog(path)

    first = ledger.append(
        "request",
        seal="req-1",
        principal="jeeves",
        route="/api/cognition",
        detail="admitted",
        timestamp=1000.0,
    )
    second = ledger.append(
        "decision",
        seal="req-1",
        principal="jeeves",
        route="/api/cognition",
        detail="completed",
        timestamp=1001.0,
    )

    assert first.seq == 1
    assert first.prev_hash == GENESIS_HASH
    assert second.seq == 2
    assert second.prev_hash == first.hash
    assert second.hash != first.hash

    restored = TamperEvidentAuditLog(path)
    report = restored.verify()
    assert report == {
        "valid": True,
        "entries": 2,
        "head": second.hash,
        "sequence": 2,
    }
    assert restored.latest == second


def test_tampering_is_detected_fail_closed(tmp_path):
    path = tmp_path / "worm.log"
    ledger = TamperEvidentAuditLog(path)
    ledger.append("request", detail="original", timestamp=1000.0)
    ledger.append("decision", detail="ok", timestamp=1001.0)

    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["detail"] = "tampered"
    lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(AuditChainError, match="content hash mismatch"):
        TamperEvidentAuditLog(path)


def test_sequence_gaps_are_rejected(tmp_path):
    path = tmp_path / "worm.log"
    ledger = TamperEvidentAuditLog(path)
    entry = ledger.append("request", timestamp=1000.0)

    data = entry.to_dict()
    data["seq"] = 3
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")

    with pytest.raises(AuditChainError, match="sequence mismatch"):
        TamperEvidentAuditLog(path)


def test_bounds_are_enforced_before_write(tmp_path):
    path = tmp_path / "worm.log"
    ledger = TamperEvidentAuditLog(path, max_field_chars=8, max_line_bytes=512)

    with pytest.raises(ValueError, match="detail exceeds"):
        ledger.append("event", detail="x" * 9)
    assert not path.exists()


def test_append_emits_only_after_durable_write(tmp_path):
    bus = EventBus()
    events = []
    bus.subscribe("acquired.audit.*", events.append)
    path = tmp_path / "worm.log"
    ledger = TamperEvidentAuditLog(path, bus=bus)

    entry = ledger.append("request", route="/api/swarm", timestamp=1000.0)

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["hash"] == entry.hash
    assert events[-1].topic == "acquired.audit.appended"
    assert events[-1].payload["hash"] == entry.hash


def test_boolean_resource_bounds_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        TamperEvidentAuditLog(tmp_path / "worm.log", max_field_chars=True)
    with pytest.raises(ValueError):
        TamperEvidentAuditLog(tmp_path / "worm.log", max_line_bytes=False)
