"""Focused unit tests for forge materialise outbox durability."""

from __future__ import annotations

import pytest

from skeleton.forge.outbox import (
    MaterialiseOutbox,
    MemorySink,
    OutboxFull,
    bind_materialise_outbox,
)
from skeleton.forge.universal import Forge
from skeleton.kernel.events import EventBus


def test_journal_and_reconcile_confirms_into_sink():
    sink = MemorySink()
    outbox = MaterialiseOutbox(sink, cap=8)
    seq = outbox.append_materialisation(
        blueprint_id="bp-1",
        components=2,
        wires=1,
        era="extraction_now",
        target="json",
        name="demo",
    )
    assert seq == 1
    assert outbox.pending_count() == 1
    assert outbox.reconcile() == 1
    assert outbox.pending_count() == 0
    assert outbox.confirmed_total == 1
    assert sink.documents[0]["blueprint_id"] == "bp-1"
    assert sink.documents[0]["kind"] == "forge.blueprint.materialised"


def test_outbox_full_backpressures_never_drops():
    sink = MemorySink()
    outbox = MaterialiseOutbox(sink, cap=1)
    outbox.journal({"blueprint_id": "a"})
    with pytest.raises(OutboxFull):
        outbox.journal({"blueprint_id": "b"})
    assert outbox.pending_count() == 1
    assert outbox.journaled_total == 1


def test_failed_sink_keeps_intent_for_replay():
    calls = {"n": 0}

    def flaky(doc):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("sink down")

    outbox = MaterialiseOutbox(flaky, cap=4)
    outbox.append_materialisation(
        blueprint_id="bp-retry",
        components=0,
        wires=0,
        era="extraction_now",
        target="json",
    )
    assert outbox.reconcile() == 0
    assert outbox.pending_count() == 1
    assert outbox.pending()[0].attempts == 1
    assert outbox.reconcile() == 1
    assert outbox.pending_count() == 0


def test_forge_injects_outbox_on_successful_materialise():
    sink = MemorySink()
    outbox = MaterialiseOutbox(sink)
    forge = Forge(outbox=outbox)
    bp = forge.new_blueprint("wired")
    forge.instantiate(bp, "source", "src")
    forge.instantiate(bp, "sink", "dst")
    bp.connect(("src", "out"), ("dst", "in"))
    result = forge.materialise(bp, target="json")
    assert result["blueprint_id"] == bp.blueprint_id
    assert outbox.pending_count() == 1
    outbox.reconcile()
    assert sink.documents[-1]["blueprint_id"] == bp.blueprint_id
    assert sink.documents[-1]["target"] == "json"
    assert sink.documents[-1]["name"] == "wired"


def test_forge_without_outbox_unchanged():
    forge = Forge()
    assert forge._outbox is None
    bp = forge.new_blueprint("plain")
    forge.instantiate(bp, "source", "src")
    forge.instantiate(bp, "sink", "dst")
    bp.connect(("src", "out"), ("dst", "in"))
    result = forge.materialise(bp, target="json")
    assert "blueprint_id" in result


def test_bind_materialise_outbox_listen_helper():
    bus = EventBus()
    sink = MemorySink()
    outbox = MaterialiseOutbox(sink)
    unsub = bind_materialise_outbox(bus, outbox)
    bus.emit(
        "forge.blueprint.materialised",
        {"blueprint_id": "bp-bus", "components": 3, "wires": 2, "era": "e", "target": "json"},
    )
    assert outbox.pending_count() == 1
    outbox.reconcile()
    assert sink.documents[0]["blueprint_id"] == "bp-bus"
    assert sink.documents[0]["extra"]["source"] == "bus"
    unsub()
    bus.emit(
        "forge.blueprint.materialised",
        {"blueprint_id": "bp-after", "components": 0, "wires": 0, "era": "e", "target": "json"},
    )
    assert outbox.pending_count() == 0


def test_stats_shape():
    outbox = MaterialiseOutbox(cap=16)
    outbox.journal({"blueprint_id": "x"})
    stats = outbox.stats()
    assert stats["cap"] == 16
    assert stats["pending"] == 1
    assert stats["journaled_total"] == 1
    assert stats["confirmed_total"] == 0
