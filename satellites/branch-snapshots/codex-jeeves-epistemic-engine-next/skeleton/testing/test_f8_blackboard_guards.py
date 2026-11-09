"""F-8: memory-poisoning guards for the blackboard (isolated, no FastAPI)."""

from __future__ import annotations

import pytest

from skeleton.kernel.events import EventBus
from skeleton.swarm.blackboard import Blackboard, BlackboardEntry, is_poisonous


def test_low_confidence_quarantined_not_in_read():
    bb = Blackboard(min_confidence=0.2)
    entry = bb.post("intel.x", {"v": 1}, producer="scout", confidence=0.1)
    assert entry.quarantined is True
    assert bb.read() == []
    assert bb.read(include_quarantined=True) == [entry]
    assert bb.stats()["quarantined"] == 1
    assert bb.stats()["live"] == 0


def test_require_provenance_quarantines_empty():
    bb = Blackboard(require_provenance=True)
    bad = bb.post("t", {"a": 1}, producer="a", confidence=0.9, provenance="")
    good = bb.post(
        "t", {"a": 2}, producer="b", confidence=0.9, provenance="session-1"
    )
    assert bad.quarantined is True
    assert good.quarantined is False
    live = bb.read()
    assert len(live) == 1
    assert live[0].entry_id == good.entry_id
    assert live[0].provenance == "session-1"


def test_blocked_producer_quarantined():
    events: list[str] = []
    bus = EventBus()
    bus.subscribe("blackboard.quarantined", lambda e: events.append(e.topic))
    bb2 = Blackboard(bus=bus, blocked_producers={"evil"})
    entry = bb2.post("t", {"x": 1}, producer="evil", confidence=0.9)
    assert entry.quarantined is True
    assert bb2.read() == []
    assert "blackboard.quarantined" in events


def test_release_restores_to_read():
    bb = Blackboard(min_confidence=0.5)
    entry = bb.post("t", {}, producer="a", confidence=0.1)
    assert entry.quarantined and bb.read() == []
    released = bb.release(entry.entry_id)
    assert released.quarantined is False
    assert bb.read() == [entry]
    assert bb.stats()["quarantined"] == 0


def test_operator_quarantine_hides_from_read():
    bb = Blackboard()
    entry = bb.post("t", {"ok": True}, producer="a", confidence=0.9)
    assert bb.read() == [entry]
    bb.quarantine(entry.entry_id)
    assert entry.quarantined is True
    assert bb.read() == []
    assert bb.read(include_quarantined=True)[0].entry_id == entry.entry_id


def test_oversized_payload_rejected():
    bb = Blackboard(max_payload_bytes=32)
    with pytest.raises(ValueError, match="max_payload_bytes"):
        bb.post("t", {"blob": "x" * 100}, producer="a", confidence=0.9)
    assert bb.posts == 0
    assert bb.read() == []


def test_is_poisonous_helper():
    low = BlackboardEntry(
        entry_id="1", topic="t", payload={}, producer="a",
        confidence=0.05, posted_at=0.0, ttl_s=10.0,
    )
    assert is_poisonous(low, min_confidence=0.2) is True
    ok = BlackboardEntry(
        entry_id="2", topic="t", payload={}, producer="a",
        confidence=0.9, posted_at=0.0, ttl_s=10.0, provenance="src",
    )
    assert is_poisonous(ok, min_confidence=0.2) is False
    assert is_poisonous(ok, require_provenance=True) is False
    no_prov = BlackboardEntry(
        entry_id="3", topic="t", payload={}, producer="a",
        confidence=0.9, posted_at=0.0, ttl_s=10.0, provenance="",
    )
    assert is_poisonous(no_prov, require_provenance=True) is True
    blocked = BlackboardEntry(
        entry_id="4", topic="t", payload={}, producer="evil",
        confidence=0.9, posted_at=0.0, ttl_s=10.0,
    )
    assert is_poisonous(blocked, blocked_producers={"evil"}) is True


def test_to_dict_includes_provenance_and_quarantined():
    bb = Blackboard(min_confidence=0.2)
    entry = bb.post(
        "t", {"k": 1}, producer="a", confidence=0.1, provenance="attested"
    )
    d = entry.to_dict()
    assert d["provenance"] == "attested"
    assert d["quarantined"] is True


def test_default_guards_do_not_break_wave4_confidence():
    """Default min_confidence=0.2; typical posts remain live."""
    bb = Blackboard()
    bb.post("intel.prices", {"gold": 100}, producer="scout", confidence=0.4)
    bb.post("intel.prices", {"gold": 101}, producer="oracle", confidence=0.9)
    entries = bb.read("intel.prices")
    assert len(entries) == 2
    assert entries[0].producer == "oracle"
