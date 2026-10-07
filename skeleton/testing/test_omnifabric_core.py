"""Tests for OmniFabric core — append, chain, outbox-first, hot-tail drain."""
from __future__ import annotations

import pytest

from skeleton.kernel.omnifabric import (
    ChainBroken,
    FabricOutbox,
    OmniFabric,
    OutboxFull,
    FabricEvent,
)
from skeleton.kernel.omnifabric.outbox import MemorySink


def test_append_chains_from_genesis():
    fab = OmniFabric(hot_cap=64)
    ev = fab.append("court", "decide", {"v": 1}, ["a1", "a2"])
    assert ev.seq == 1
    assert ev.prev_hash == "genesis"
    assert ev.hash == ev.compute_hash()
    assert fab.head_hash == ev.hash
    assert fab.verify_chain() is True


def test_append_links_successive_hashes():
    fab = OmniFabric()
    e1 = fab.append("L", "k1", {"n": 1}, ["q"])
    e2 = fab.append("L", "k2", {"n": 2}, ["q"])
    assert e2.prev_hash == e1.hash
    assert e2.seq == 2
    assert fab.current_seq == 2
    assert fab.verify_chain() is True


def test_tail_filters_ledger_newest_first():
    fab = OmniFabric()
    fab.append("A", "x", {}, [])
    fab.append("B", "y", {}, [])
    fab.append("A", "z", {}, [])
    tail = fab.tail("A", 10)
    assert [e.kind for e in tail] == ["z", "x"]


def test_outbox_full_rolls_back_seq():
    sink = MemorySink()
    outbox = FabricOutbox(sink, cap=1)
    fab = OmniFabric(outbox, auto_confirm=False)
    fab.append("L", "a", {}, [])
    assert fab.current_seq == 1
    with pytest.raises(OutboxFull):
        fab.append("L", "b", {}, [])
    assert fab.current_seq == 1
    assert fab.stats()["rollbacks"] == 1
    assert len(fab.snapshot_tail()) == 1


def test_auto_confirm_drains_outbox():
    fab = OmniFabric(auto_confirm=True)
    fab.append("L", "k", {"x": 1}, ["a"])
    assert fab.outbox.pending_count() == 0
    assert fab.outbox.confirmed_total == 1


def test_tampered_payload_breaks_verify():
    fab = OmniFabric()
    fab.append("L", "k", {"ok": True}, [])
    fab._tail[0].payload["ok"] = False  # noqa: SLF001 — intentional tamper
    with pytest.raises(ChainBroken) as ei:
        fab.verify_chain()
    assert "hash does not match" in ei.value.detail


def test_tampered_prev_hash_breaks_verify():
    fab = OmniFabric()
    fab.append("L", "a", {}, [])
    fab.append("L", "b", {}, [])
    fab._tail[1].prev_hash = "deadbeef"  # noqa: SLF001
    # recompute would still fail link check before content if we don't reseal
    with pytest.raises(ChainBroken):
        fab.verify_chain()


def test_hot_tail_drain_keeps_verify_contiguous():
    fab = OmniFabric(hot_cap=8)
    for i in range(20):
        fab.append("L", f"k{i}", {"i": i}, ["q"])
    assert fab.hot_len <= 8
    assert fab.stats()["drains"] >= 1
    # contiguous verify still works on remaining tail
    assert fab.verify_chain() is True
    with pytest.raises(ChainBroken):
        fab.verify_full_from_genesis()


def test_get_by_seq_and_tail_all():
    fab = OmniFabric()
    events = [fab.append("L", "k", {"i": i}, []) for i in range(5)]
    assert fab.get_by_seq(3).id == events[2].id
    assert fab.get_by_seq(99) is None
    assert len(fab.tail_all(3)) == 3
    assert fab.tail_all(3)[0].seq == 5


def test_quorum_preserved():
    fab = OmniFabric()
    ev = fab.append("gov", "vote", {"y": 1}, ["alice", "bob", "carol"])
    assert ev.quorum == ["alice", "bob", "carol"]
    assert fab.tail("gov", 1)[0].quorum == ["alice", "bob", "carol"]


def test_stable_hash_for_same_content():
    a = FabricEvent.create(
        ledger="L", kind="k", payload={"z": 1, "a": 2}, seq=1, quorum=["q"], prev_hash="genesis", ts=1.0, event_id="fixed"
    )
    b = FabricEvent.create(
        ledger="L", kind="k", payload={"a": 2, "z": 1}, seq=1, quorum=["q"], prev_hash="genesis", ts=1.0, event_id="fixed"
    )
    assert a.hash == b.hash


def test_stats_shape():
    fab = OmniFabric()
    fab.append("L", "k", {}, [])
    s = fab.stats()
    for key in ("seq", "head_hash", "hot_len", "appends", "outbox_journaled"):
        assert key in s
