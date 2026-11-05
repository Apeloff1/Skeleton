"""Regression contracts for carpentry_shelter_frame production."""
from __future__ import annotations
import pytest
from skeleton.forge.production_pipelines_v1.carpentry_shelter_frame import (
    ProductionState, STAGES, MATERIAL_COST, ENERGY_PER_STAGE,
    YIELD_PER_BATCH, BATCH_LIMIT, MAX_EVENTS, transition, snapshot, replay,
)

def cmd(identity="e1", action="start", batch=1, version=0, tick=1, evidence=""):
    return {
        "id": identity, "action": action, "batch": batch,
        "expected_version": version, "tick": tick, "evidence": evidence,
    }

def execution():
    return [
        cmd("start", "start", 1, 0, 1),
        cmd("prep", "advance", 1, 1, 2, "trusted-stage-prep"),
        cmd("build", "advance", 1, 2, 3, "trusted-stage-build"),
        cmd("quality", "advance", 1, 3, 4, "trusted-stage-quality"),
        cmd("finish", "finish", 1, 4, 5, "trusted-quality-acceptance"),
    ]

def test_initial_snapshot():
    result = snapshot(ProductionState())
    assert result["recipe_id"] == "carpentry_shelter_frame"
    assert result["status"] == "idle"
    assert result["stage_count"] == 3

def test_start_consumes_materials():
    before = ProductionState()
    after, receipt = transition(before, cmd())
    assert receipt.accepted
    assert after.status == "working"
    assert after.materials == before.materials - MATERIAL_COST
    assert after.spent_materials == MATERIAL_COST

def test_full_lot_yields_only_after_quality_acceptance():
    state, receipts = replay(execution())
    assert state.status == "completed"
    assert state.stage == len(STAGES)
    assert state.products == YIELD_PER_BATCH
    assert len(receipts) == 5
    assert all(receipt.accepted for receipt in receipts)

def test_no_product_during_work_in_progress():
    state, _ = replay(execution()[:4])
    assert state.status == "working"
    assert state.products == 0
    assert state.stage == len(STAGES)

def test_missing_stage_evidence_rejected():
    state, _ = transition(ProductionState(), cmd())
    unchanged, receipt = transition(state, cmd("a", "advance", 1, 1, 2))
    assert unchanged is state
    assert receipt.reason == "stage-evidence-missing"

def test_finish_before_stages_rejected():
    state, _ = transition(ProductionState(), cmd())
    unchanged, receipt = transition(
        state, cmd("finish", "finish", 1, 1, 2, "evidence")
    )
    assert unchanged is state
    assert receipt.reason == "stages-incomplete"

def test_extra_advance_after_final_stage_fails_closed():
    state, _ = replay(execution()[:4])
    assert state.stage == len(STAGES)
    unchanged, receipt = transition(
        state, cmd("extra-stage", "advance", state.batch,
                   state.version, state.tick + 1, "duplicate-stage-evidence")
    )
    assert unchanged is state
    assert not receipt.accepted
    assert receipt.reason == "stages-complete-awaiting-quality"


def test_finish_requires_quality_evidence():
    state, _ = replay(execution()[:4])
    unchanged, receipt = transition(state, cmd("finish", "finish", 1, 4, 5))
    assert unchanged is state
    assert receipt.reason == "quality-evidence-missing"

def test_cancel_is_terminal_and_does_not_produce():
    state, _ = transition(ProductionState(), cmd())
    cancelled, receipt = transition(state, cmd("c", "cancel", 1, 1, 2))
    assert receipt.accepted
    assert cancelled.status == "cancelled"
    assert cancelled.products == 0
    unchanged, retry = transition(
        cancelled, cmd("next", "advance", 1, 2, 3, "evidence")
    )
    assert unchanged is cancelled
    assert retry.reason == "not-current-lot"

def test_insufficient_material_fails_closed():
    before = ProductionState(materials=0)
    unchanged, receipt = transition(before, cmd())
    assert unchanged is before
    assert receipt.reason == "insufficient-material"

def test_insufficient_energy_fails_closed():
    before = ProductionState(energy=0)
    state, _ = transition(before, cmd())
    unchanged, receipt = transition(
        state, cmd("a", "advance", 1, 1, 2, "evidence")
    )
    assert unchanged is state
    assert receipt.reason == "insufficient-energy"

def test_duplicate_identity_fails_closed():
    state, _ = transition(ProductionState(), cmd())
    unchanged, receipt = transition(state, cmd("e1", "cancel", 1, 1, 2))
    assert unchanged is state
    assert receipt.reason == "duplicate-event"

def test_stale_version_fails_closed():
    state, _ = transition(ProductionState(), cmd())
    unchanged, receipt = transition(state, cmd("e2", "cancel", 1, 0, 2))
    assert unchanged is state
    assert receipt.reason == "stale-version"

def test_nonmonotonic_tick_fails_closed():
    state, _ = transition(ProductionState(), cmd())
    unchanged, receipt = transition(state, cmd("e2", "cancel", 1, 1, 1))
    assert unchanged is state
    assert receipt.reason == "nonmonotonic-tick"

def test_readonly_observe_not_a_mutation():
    before = ProductionState()
    unchanged, receipt = transition(before, cmd(action="observe"))
    assert unchanged is before
    assert receipt.reason == "observation-readonly"

@pytest.mark.parametrize("bad", [None, True, 0, -1, 2.5, BATCH_LIMIT + 1])
def test_invalid_batch_rejected(bad):
    with pytest.raises(ValueError):
        transition(ProductionState(), cmd(batch=bad))

@pytest.mark.parametrize("action", ["grant", "", None, "override"])
def test_unsupported_action_rejected(action):
    with pytest.raises(ValueError):
        transition(ProductionState(), cmd(action=action))

def test_unknown_fields_rejected():
    with pytest.raises(ValueError):
        transition(ProductionState(), {**cmd(), "force": True})

def test_invalid_state_is_not_accepted():
    with pytest.raises(ValueError):
        ProductionState(materials=-1)
    with pytest.raises(ValueError):
        ProductionState(energy=True)
    with pytest.raises(ValueError):
        ProductionState(status="working", batch=0)
    with pytest.raises(ValueError):
        ProductionState(status="completed", stage=0, batch=1)
    with pytest.raises(ValueError):
        ProductionState(event_ids=frozenset({""}))

def test_replay_is_deterministic():
    assert replay(execution()) == replay(execution())

def test_batch_capacity_fails_closed():
    with pytest.raises(ValueError):
        replay([cmd()] * (MAX_EVENTS + 1))
