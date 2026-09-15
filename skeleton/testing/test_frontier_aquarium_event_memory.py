from datetime import datetime, timezone

import pytest

from skeleton.frontier.aquarium import add_fish, initial_aquarium, purchase_tank
from skeleton.frontier.aquarium_adapters import (
    aquarium_event,
    aquarium_event_to_memory_item,
    aquarium_identity,
    aquarium_state_digest,
    aquarium_state_memory_item,
)
from skeleton.frontier.aquarium_models import AquariumPosition, AquariumTankSpec, DisplayFish
from skeleton.frontier.aquarium_state import AquariumState, AquariumTankState
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent


def _fish(identity: str) -> DisplayFish:
    return DisplayFish(
        identity,
        "Blue Fish",
        "blue_fish",
        20,
        AquariumPosition(50, 50),
        added_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )


def test_aquarium_event_projects_to_stable_memory_identity():
    starter = AquariumTankSpec("starter", "Starter", 10, 1, 3)
    state = add_fish(initial_aquarium(), starter, _fish("fish-1")).aquarium
    event = aquarium_event(
        state,
        subject_id="player-1",
        action="fish_added",
        occurred_at=datetime(2026, 9, 15, 12, 1, tzinfo=timezone.utc),
    )
    memory = aquarium_event_to_memory_item(event)
    snapshot = aquarium_state_memory_item(state, subject_id="player-1")

    assert event.topic == "aquarium.fish_added"
    assert memory["id"] == aquarium_identity("player-1") == snapshot["id"]
    assert memory["metadata"]["aquarium_state_sha256"] == aquarium_state_digest(state)
    assert memory["metadata"]["fish_count"] == 1
    assert memory["metadata"]["tank_count"] == 1


def test_aquarium_event_rejects_identity_digest_tampering():
    event = aquarium_event(
        initial_aquarium(),
        subject_id="player-1",
        action="theme_changed",
        occurred_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )
    payload = dict(event.payload)
    payload["subject_id"] = "player-2"
    tampered = DomainEvent(event.topic, payload, event.occurred_at)
    with pytest.raises(ValueError, match="identity digest mismatch"):
        aquarium_event_to_memory_item(tampered)


def test_aquarium_event_rejects_state_tampering_even_with_recomputed_digest():
    starter = AquariumTankSpec("starter", "Starter", 10, 1, 3)
    state = add_fish(initial_aquarium(), starter, _fish("fish-1")).aquarium
    event = aquarium_event(
        state,
        subject_id="player-1",
        action="fish_added",
        occurred_at=datetime(2026, 9, 15, 12, 1, tzinfo=timezone.utc),
    )
    payload = dict(event.payload)
    payload["total_fish_displayed"] = 2
    state_payload = {
        "tanks": payload["tanks"],
        "owned_tanks": payload["owned_tanks"],
        "owned_decorations": payload["owned_decorations"],
        "total_fish_displayed": payload["total_fish_displayed"],
    }
    payload["aquarium_state_sha256"] = stable_content_digest(state_payload)
    tampered = DomainEvent(event.topic, payload, event.occurred_at)
    with pytest.raises(ValueError, match="total fish displayed must match"):
        aquarium_event_to_memory_item(tampered)


def test_state_hydration_rejects_cross_tank_duplicate_fish_identity():
    fish = _fish("same-fish")
    with pytest.raises(ValueError, match="duplicate fish identity across aquarium"):
        AquariumState(
            tanks={
                "starter": AquariumTankState("starter", fish=(fish,)),
                "medium": AquariumTankState("medium", fish=(fish,)),
            },
            owned_tanks=frozenset({"starter", "medium"}),
            total_fish_displayed=2,
        )


def test_tank_purchase_then_event_preserves_canonical_digest():
    medium = AquariumTankSpec("medium", "Medium", 25, 10, 6, {"coins": 5000})
    state = purchase_tank(initial_aquarium(), medium)
    event = aquarium_event(
        state,
        subject_id="player-1",
        action="tank_purchased",
        occurred_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )
    memory = aquarium_event_to_memory_item(event)
    assert memory["metadata"]["tank_count"] == 2
    assert memory["metadata"]["aquarium_state_sha256"] == aquarium_state_digest(state)


def test_aquarium_event_action_is_allowlisted():
    with pytest.raises(ValueError, match="unsupported aquarium action"):
        aquarium_event(
            initial_aquarium(),
            subject_id="player-1",
            action="delete_everything",
            occurred_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
        )
