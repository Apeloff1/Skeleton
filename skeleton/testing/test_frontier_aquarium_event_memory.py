from datetime import datetime, timezone

import pytest

from skeleton.frontier.aquarium import (
    AquariumPosition,
    AquariumTankSpec,
    DisplayFish,
    add_fish,
    initial_aquarium,
    record_visit,
)
from skeleton.frontier.aquarium_adapters import (
    aquarium_event,
    aquarium_event_to_memory_item,
    aquarium_identity,
    aquarium_state_digest,
    aquarium_state_memory_item,
)
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _starter() -> AquariumTankSpec:
    return AquariumTankSpec(
        id="starter",
        name="Starter",
        capacity=10,
        width=100,
        height=50,
        decorations_allowed=3,
    )


def _fish(identity: str = "fish-1") -> DisplayFish:
    return DisplayFish(
        id=identity,
        name="Blue Fish",
        species="blue_fish",
        size=20,
        color="#4A90D9",
        traits={},
        position=AquariumPosition(50, 50),
        added_at=NOW,
    )


def _state_with_fish():
    return add_fish(initial_aquarium(), _starter(), _fish()).aquarium


def test_aquarium_event_projects_to_stable_memory_identity_and_derived_counts():
    state = _state_with_fish()
    event = aquarium_event(
        state,
        subject_id="player-1",
        action="fish_added",
        occurred_at=NOW,
    )
    memory = aquarium_event_to_memory_item(event)
    snapshot = aquarium_state_memory_item(state, subject_id="player-1")

    assert event.topic == "aquarium.fish_added"
    assert memory["id"] == aquarium_identity("player-1") == snapshot["id"]
    assert memory["metadata"]["aquarium_state_sha256"] == aquarium_state_digest(state)
    assert memory["metadata"]["fish_count"] == state.total_fish_displayed == 1
    assert memory["metadata"]["decoration_count"] == 0


def test_aquarium_event_rejects_identity_tampering():
    event = aquarium_event(
        initial_aquarium(),
        subject_id="player-1",
        action="theme_changed",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["subject_id"] = "player-2"

    with pytest.raises(ValueError, match="identity digest mismatch"):
        aquarium_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_recomputed_digest_cannot_bypass_state_rehydration_invariants():
    event = aquarium_event(
        initial_aquarium(),
        subject_id="player-1",
        action="theme_changed",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    tanks = {key: dict(value) for key, value in payload["tanks"].items()}
    tanks["starter"]["tank_id"] = "different-id"
    payload["tanks"] = tanks
    malformed_state_payload = {
        "tanks": payload["tanks"],
        "owned_tanks": payload["owned_tanks"],
        "owned_decorations": payload["owned_decorations"],
        "visitors": payload["visitors"],
        "likes": payload["likes"],
    }
    payload["aquarium_state_sha256"] = stable_content_digest(malformed_state_payload)

    with pytest.raises(ValueError, match="tank key must match tank_id"):
        aquarium_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_visit_projection_reuses_same_aquarium_identity():
    state = record_visit(initial_aquarium())
    event = aquarium_event(
        state,
        subject_id="player-1",
        action="visit_recorded",
        occurred_at=NOW,
    )
    memory = aquarium_event_to_memory_item(event)

    assert memory["id"] == aquarium_identity("player-1")
    assert memory["metadata"]["visitors"] == 1
    assert memory["metadata"]["fish_count"] == 0


def test_event_action_is_allowlisted():
    with pytest.raises(ValueError, match="unsupported aquarium action"):
        aquarium_event(
            initial_aquarium(),
            subject_id="player-1",
            action="drop_database",
            occurred_at=NOW,
        )


def test_payload_requires_normalized_sha256_digests():
    event = aquarium_event(
        initial_aquarium(),
        subject_id="player-1",
        action="theme_changed",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["aquarium_state_sha256"] = "NOT-A-DIGEST"

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        aquarium_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )
