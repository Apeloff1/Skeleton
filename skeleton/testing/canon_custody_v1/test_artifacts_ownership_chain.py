"""Acceptance, lineage, replay and isolation regression for artifacts_ownership_chain."""
import pytest
from skeleton.forge.canon_custody_v1.artifacts_ownership_chain import (
    CanonRecord, CanonLedger, MAX_RECORDS, MAX_GAP,
    append, timeline, snapshot, replay
)


def event(identity="a", entity="npc-1", action="establish", value="known",
          predecessor="", evidence="world-proof-1", world="primary", tick=1, revision=0):
    return {"id":identity, "entity":entity, "action":action,
            "value":value, "predecessor":predecessor, "evidence":evidence,
            "world":world, "tick":tick, "expected_revision":revision}


def initial():
    return append(CanonLedger(), event())[0]


def test_metadata_is_domain_specific():
    report = snapshot(CanonLedger())
    assert report["policy"] == "artifacts_ownership_chain"
    assert report["record_capacity"] == MAX_RECORDS
    assert report["record_count"] == 0


def test_establishment_accepted():
    ledger, decision = append(CanonLedger(), event())
    assert decision.accepted
    assert ledger.revision == 1
    assert ledger.entries[0].identity == "a"


def test_append_amendment_follows_parent():
    ledger = initial()
    updated, decision = append(
        ledger, event("b", action="amend", value="changed",
                      predecessor="a", tick=2, revision=1)
    )
    assert decision.accepted
    assert len(timeline(updated, "npc-1")) == 2
    assert updated.entries[-1].predecessor == "a"


def test_reconciliation_is_append_only():
    ledger = initial()
    updated, decision = append(
        ledger, event("b", action="reconcile", predecessor="a",
                      tick=2, revision=1)
    )
    assert decision.accepted
    assert len(ledger.entries) == 1
    assert len(updated.entries) == 2


def test_duplicate_event_rejected():
    ledger = initial()
    same, decision = append(ledger, event("a", tick=2, revision=1))
    assert same is ledger
    assert decision.reason == "duplicate-event"


def test_cross_world_event_rejected():
    ledger = initial()
    same, decision = append(
        ledger, event("b", action="amend", predecessor="a",
                      world="parallel", tick=2, revision=1)
    )
    assert same is ledger
    assert decision.reason == "cross-world-canon"


def test_stale_revision_rejected():
    ledger = initial()
    same, decision = append(
        ledger, event("b", action="amend", predecessor="a",
                      tick=2, revision=0)
    )
    assert same is ledger
    assert decision.reason == "stale-revision"


def test_nonmonotonic_tick_rejected():
    ledger = initial()
    same, decision = append(
        ledger, event("b", action="amend", predecessor="a",
                      tick=1, revision=1)
    )
    assert same is ledger
    assert decision.reason == "nonmonotonic-tick"


def test_unjustified_clock_gap_rejected():
    ledger = initial()
    same, decision = append(
        ledger, event("b", action="amend", predecessor="a",
                      tick=2 + MAX_GAP, revision=1)
    )
    assert same is ledger
    assert decision.reason == "unjustified-clock-gap"


def test_missing_parent_rejected():
    ledger = initial()
    same, decision = append(
        ledger, event("b", action="amend", predecessor="unknown",
                      tick=2, revision=1)
    )
    assert same is ledger
    assert decision.reason == "missing-predecessor"


def test_entity_lineage_cannot_cross():
    ledger = initial()
    same, decision = append(
        ledger, event("b", entity="npc-2", action="amend",
                      predecessor="a", tick=2, revision=1)
    )
    assert same is ledger
    assert decision.reason == "entity-lineage-mismatch"


def test_duplicate_establishment_rejected():
    ledger = initial()
    same, decision = append(
        ledger, event("b", tick=2, revision=1)
    )
    assert same is ledger
    assert decision.reason == "entity-already-established"


def test_missing_proof_rejected():
    old = CanonLedger()
    same, decision = append(old, event(evidence=""))
    assert same is old
    assert decision.reason == "evidence-required"


def test_amendment_requires_causal_parent():
    ledger = initial()
    same, decision = append(
        ledger, event("b", action="amend", tick=2, revision=1)
    )
    assert same is ledger
    assert decision.reason == "amendment-missing-predecessor"


def test_establishment_cannot_claim_parent():
    ledger = initial()
    same, decision = append(
        ledger, event("b", entity="npc-2", predecessor="a", tick=2, revision=1)
    )
    assert same is ledger
    assert decision.reason == "establishment-has-predecessor"


@pytest.mark.parametrize("invalid", [None, True, -1, 1.5, "1"])
def test_invalid_revision_fails_closed(invalid):
    with pytest.raises(ValueError):
        append(CanonLedger(), event(revision=invalid))


@pytest.mark.parametrize("invalid", [None, True, -1, 1.5])
def test_invalid_tick_fails_closed(invalid):
    with pytest.raises(ValueError):
        append(CanonLedger(), event(tick=invalid))


def test_unknown_command_fields_rejected():
    with pytest.raises(ValueError):
        append(CanonLedger(), {**event(), "force": True})


def test_invalid_ledger_state_rejected():
    with pytest.raises(ValueError):
        CanonLedger(revision=1)
    with pytest.raises(ValueError):
        CanonLedger(world="")
    with pytest.raises(ValueError):
        CanonLedger(tick=True)
    with pytest.raises(ValueError):
        CanonLedger(entries=(object(),))


def test_replay_is_byte_deterministic():
    commands = [
        event(),
        event("b", action="amend", predecessor="a", tick=2, revision=1),
    ]
    assert replay(commands) == replay(commands)
    assert all(decision.accepted for decision in replay(commands)[1])


def test_timeline_filter_is_readonly():
    ledger = initial()
    assert len(timeline(ledger, "npc-1")) == 1
    assert timeline(ledger, "npc-2") == ()
    assert ledger.revision == 1


def test_batch_capacity_rejected():
    with pytest.raises(ValueError):
        replay([event()] * (MAX_RECORDS + 1))
