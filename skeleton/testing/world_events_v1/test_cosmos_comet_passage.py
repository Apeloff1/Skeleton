"""World event lifecycle regression suite: cosmos_comet_passage."""
from __future__ import annotations

import pytest

from skeleton.forge.world_events_v1.cosmos_comet_passage import (
    State, MAX_IDS, TRIGGER_THRESHOLD, RESOLUTION_COST,
    COOLDOWN_TICKS, transition, snapshot, replay
)


def command(identity="e1", action="activate", tick=1, version=0,
            intensity=0, evidence=""):
    return {
        "id": identity, "action": action, "tick": tick,
        "expected_version": version, "intensity": intensity,
        "evidence": evidence
    }


def ready():
    return State(pressure=100, resources=100)


def test_metadata_and_initial_state():
    report = snapshot(State())
    assert report["schema"] == "skeleton.world_event.v1"
    assert report["world_event"] == "cosmos_comet_passage"
    assert report["threshold"] == TRIGGER_THRESHOLD
    assert report["lifecycle"] == "idle"


def test_activation_requires_threshold():
    low = State(pressure=0)
    unchanged, receipt = transition(low, command())
    assert unchanged is low
    assert receipt.reason == "trigger-threshold-not-met"


def test_activate_issues_active_identity():
    activated, receipt = transition(ready(), command())
    assert receipt.accepted
    assert receipt.reason == "activated"
    assert activated.lifecycle == "active"
    assert activated.active_id == "e1"
    assert activated.version == 1


def test_resolution_requires_evidence():
    activated, _ = transition(ready(), command())
    unchanged, receipt = transition(
        activated, command("e2", "resolve", 2, 1)
    )
    assert unchanged is activated
    assert receipt.reason == "resolution-evidence-missing"


def test_resolution_enters_cooldown():
    activated, _ = transition(ready(), command())
    updated, receipt = transition(
        activated, command("e2", "resolve", 2, 1, 0, "world-proof")
    )
    assert receipt.accepted
    assert updated.lifecycle == "cooldown"
    assert updated.active_id == ""
    assert updated.resources == 100 - RESOLUTION_COST
    assert updated.resilience >= activated.resilience
    assert updated.cooldown_until == 2 + COOLDOWN_TICKS


def test_cooldown_cannot_be_released_early():
    state, _ = transition(ready(), command())
    state, _ = transition(state, command("e2", "abort", 2, 1))
    unchanged, receipt = transition(
        state, command("e3", "release_cooldown", 3, 2)
    )
    assert unchanged is state
    assert receipt.reason == "cooldown-not-expired"


def test_cooldown_eventually_returns_idle():
    state, _ = transition(ready(), command())
    state, _ = transition(state, command("e2", "abort", 2, 1))
    until = state.cooldown_until
    state, receipt = transition(
        state, command("e3", "release_cooldown", until, 2)
    )
    assert receipt.accepted
    assert state.lifecycle == "idle"
    assert state.cooldown_until == 0


def test_duplicate_receipts_have_no_side_effect():
    state, _ = transition(ready(), command())
    unchanged, receipt = transition(
        state, command("e1", "abort", 2, 1)
    )
    assert unchanged is state
    assert receipt.reason == "duplicate-event"


def test_stale_version_is_rejected():
    state, _ = transition(ready(), command())
    unchanged, receipt = transition(state, command("e2", "abort", 2, 0))
    assert unchanged is state
    assert receipt.reason == "stale-version"


def test_nonmonotonic_clock_is_rejected():
    state, _ = transition(ready(), command())
    unchanged, receipt = transition(state, command("e2", "abort", 1, 1))
    assert unchanged is state
    assert receipt.reason == "nonmonotonic-tick"


def test_active_event_cannot_reactivate():
    state, _ = transition(ready(), command())
    unchanged, receipt = transition(state, command("e2", "activate", 2, 1))
    assert unchanged is state
    assert receipt.reason == "event-not-idle"


def test_abort_is_accounted_as_cooldown():
    state, _ = transition(ready(), command())
    state, receipt = transition(state, command("e2", "abort", 2, 1))
    assert receipt.reason == "aborted"
    assert state.lifecycle == "cooldown"
    assert state.active_id == ""


def test_readonly_observation_is_nonmutating():
    state, receipt = transition(ready(), command(action="observe"))
    assert state == ready()
    assert receipt.reason == "observation-readonly"


@pytest.mark.parametrize("invalid", [True, None, -1, 1.5, 21])
def test_invalid_intensity_fails_closed(invalid):
    with pytest.raises(ValueError):
        transition(ready(), command(intensity=invalid))


@pytest.mark.parametrize("invalid", [None, "grant", "force", ""])
def test_unknown_action_fails_closed(invalid):
    with pytest.raises(ValueError):
        transition(ready(), command(action=invalid))


def test_extra_command_fields_are_rejected():
    with pytest.raises(ValueError):
        transition(ready(), {**command(), "bypass": True})


def test_state_invariant_guardrails():
    with pytest.raises(ValueError):
        State(resources=-1)
    with pytest.raises(ValueError):
        State(pressure=True)
    with pytest.raises(ValueError):
        State(lifecycle="active")
    with pytest.raises(ValueError):
        State(lifecycle="idle", active_id="ghost")
    with pytest.raises(ValueError):
        State(region="../secret")


def test_replay_is_deterministic():
    actions = [
        command("a", "activate", 1, 0),
        command("b", "resolve", 2, 1, 0, "world-proof"),
        command("c", "release_cooldown", 2 + COOLDOWN_TICKS, 2)
    ]
    assert replay(actions, ready()) == replay(actions, ready())
    result, receipts = replay(actions, ready())
    assert result.lifecycle == "idle"
    assert all(receipt.accepted for receipt in receipts)


def test_batch_limit_fails_closed():
    with pytest.raises(ValueError):
        replay([command()] * (MAX_IDS + 1))
