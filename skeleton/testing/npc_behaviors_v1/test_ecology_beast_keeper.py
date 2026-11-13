"""NPC beast keeper deterministic behavior regressions."""
from __future__ import annotations
import pytest

from skeleton.forge.npc_behaviors_v1.ecology_beast_keeper import (
    NPCState, WORK_COST, REST_GAIN, SOCIAL_GAIN, MAX_EFFORT,
    ALLOWED_LOCATIONS, transition, snapshot, replay,
)

_UNSET = object()


def event(identity="e1", action="observe", effort=0, tick=1, version=0,
          destination="market", witness=""):
    return {
        "id": identity, "action": action, "effort": effort, "tick": tick,
        "expected_version": version, "destination": destination,
        "witness": witness,
    }


def test_initial_snapshot_is_structured():
    view = snapshot(NPCState())
    assert view["schema"] == "skeleton.npc_behavior.v1"
    assert 0 <= view["energy"] <= 100
    assert view["location"] in ALLOWED_LOCATIONS


def test_observation_is_recorded_without_resource_gain():
    state, receipt = transition(NPCState(), event())
    assert receipt.accepted
    assert state.energy == NPCState().energy
    assert state.version == 1


def test_work_spends_energy_and_adds_stress():
    state, receipt = transition(NPCState(), event(action="work", effort=2))
    assert receipt.accepted
    assert state.energy == NPCState().energy - WORK_COST - 2
    assert state.stress > 0


def test_rest_replenishes_energy_safely():
    initial = NPCState(energy=95, stress=30)
    state, receipt = transition(initial, event(action="rest", effort=MAX_EFFORT))
    assert receipt.accepted
    assert state.energy == 100
    assert state.stress < initial.stress


def test_socialize_improves_trust():
    state, receipt = transition(NPCState(), event(action="socialize", effort=2))
    assert receipt.accepted
    assert state.trust == NPCState().trust + SOCIAL_GAIN + 2


def test_travel_updates_location_and_costs_energy():
    state, receipt = transition(NPCState(), event(action="travel"))
    assert receipt.accepted
    assert state.location == "market"
    assert state.energy == NPCState().energy - 3


def test_travel_same_place_rejected():
    state, receipt = transition(NPCState(), event(action="travel", destination="home"))
    assert state == NPCState()
    assert receipt.reason == "already-at-destination"


def test_negotiation_requires_witness():
    state, receipt = transition(NPCState(), event(action="negotiate"))
    assert state == NPCState()
    assert receipt.reason == "missing-witness"
    advanced, accepted = transition(NPCState(), event(action="negotiate", witness="world-event:1"))
    assert accepted.accepted
    assert advanced.trust > NPCState().trust


def test_guard_consumes_energy():
    state, receipt = transition(NPCState(), event(action="guard"))
    assert receipt.accepted
    assert state.energy < NPCState().energy


def test_retreat_reduces_stress_and_returns_home():
    initial = NPCState(stress=50, location="market")
    state, receipt = transition(initial, event(action="retreat"))
    assert receipt.accepted
    assert state.stress < initial.stress
    assert state.location == "home"


def test_duplicate_identity_fails_closed():
    state, receipt = transition(NPCState(), event())
    unchanged, duplicate = transition(state, event(tick=2, version=1))
    assert receipt.accepted
    assert unchanged is state
    assert duplicate.reason == "duplicate-event"


def test_stale_version_fails_closed():
    state, _ = transition(NPCState(), event())
    unchanged, receipt = transition(state, event("new", tick=2, version=0))
    assert unchanged is state
    assert receipt.reason == "stale-version"


def test_nonmonotonic_tick_fails_closed():
    state, _ = transition(NPCState(), event())
    unchanged, receipt = transition(state, event("new", tick=1, version=1))
    assert unchanged is state
    assert receipt.reason == "nonmonotonic-tick"


def test_insufficient_energy_fails_closed():
    initial = NPCState(energy=0)
    unchanged, receipt = transition(initial, event(action="work"))
    assert unchanged is initial
    assert receipt.reason == "insufficient-energy"


@pytest.mark.parametrize("bad", [True, None, -1, 1.5, MAX_EFFORT + 1])
def test_invalid_effort_is_rejected(bad):
    with pytest.raises(ValueError):
        transition(NPCState(), event(effort=bad))


@pytest.mark.parametrize("bad", ["", None, "teleport", "escalate-privileges"])
def test_unknown_action_is_rejected(bad):
    with pytest.raises(ValueError):
        transition(NPCState(), event(action=bad))


def test_unknown_event_keys_fails_closed():
    with pytest.raises(ValueError):
        transition(NPCState(), {**event(), "force": True})


def test_state_invariants_reject_invalid_fields():
    with pytest.raises(ValueError):
        NPCState(energy=101)
    with pytest.raises(ValueError):
        NPCState(trust=-1)
    with pytest.raises(ValueError):
        NPCState(stress=True)
    with pytest.raises(ValueError):
        NPCState(location="../outside")


def test_replay_is_deterministic():
    commands = [
        event("a", "work", 1, 1, 0),
        event("b", "rest", 2, 2, 1),
        event("c", "socialize", 1, 3, 2),
    ]
    assert replay(commands) == replay(commands)
    assert all(receipt.accepted for receipt in replay(commands)[1])


def test_readonly_snapshot_does_not_mutate():
    initial = NPCState()
    first = snapshot(initial)
    second = snapshot(initial)
    assert first == second
    assert initial == NPCState()
