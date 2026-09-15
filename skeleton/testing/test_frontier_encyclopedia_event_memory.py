from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.encyclopedia import empty_collection, record_fish_catch
from skeleton.frontier.encyclopedia_adapters import (
    collection_digest,
    collection_event,
    collection_event_to_memory_item,
    collection_identity,
    collection_memory_item,
)
from skeleton.frontier.events import DomainEvent


NOW = datetime(2026, 9, 15, 14, 30, tzinfo=timezone.utc)


def _collection():
    return record_fish_catch(
        empty_collection(), fish_id="trout", size=42, occurred_at=NOW
    ).collection


def _state_material(payload):
    return {
        "discovered_fish": payload["discovered_fish"],
        "fish_stats": payload["fish_stats"],
    }


def test_collection_event_projects_stable_identity_and_state_digest():
    collection = _collection()
    event = collection_event(
        collection,
        subject_id="player-1",
        fish_id="trout",
        action="fish_discovered",
        occurred_at=NOW,
    )
    memory = collection_event_to_memory_item(event)
    snapshot = collection_memory_item(collection, subject_id="player-1")

    assert event.topic == "encyclopedia.fish_discovered"
    assert memory["id"] == collection_identity("player-1") == snapshot["id"]
    assert memory["metadata"]["collection_state_sha256"] == collection_digest(
        collection
    )
    assert memory["metadata"]["unique_species_discovered"] == 1
    assert memory["metadata"]["total_fish_caught"] == 1
    assert memory["metadata"]["largest_catch_id"] == "trout"


def test_collection_event_rejects_subject_identity_tampering():
    event = collection_event(
        _collection(),
        subject_id="player-1",
        fish_id="trout",
        action="fish_caught",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["subject_id"] = "player-2"

    with pytest.raises(ValueError, match="identity digest mismatch"):
        collection_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_collection_event_rejects_fish_absent_from_rehydrated_state():
    event = collection_event(
        _collection(),
        subject_id="player-1",
        fish_id="trout",
        action="fish_caught",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["fish_id"] = "bass"

    with pytest.raises(ValueError, match="absent from rehydrated state"):
        collection_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_recomputed_digest_cannot_hide_discovery_stats_identity_drift():
    event = collection_event(
        _collection(),
        subject_id="player-1",
        fish_id="trout",
        action="fish_caught",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["discovered_fish"] = ["trout"]
    payload["fish_stats"] = {"bass": payload["fish_stats"]["trout"]}
    payload["collection_state_sha256"] = stable_content_digest(
        _state_material(payload)
    )

    with pytest.raises(ValueError, match="exactly match"):
        collection_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_recomputed_digest_cannot_hide_invalid_size_invariants():
    event = collection_event(
        _collection(),
        subject_id="player-1",
        fish_id="trout",
        action="fish_caught",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    stats = dict(payload["fish_stats"]["trout"])
    stats["smallest"] = 100
    stats["largest"] = 10
    payload["fish_stats"] = {"trout": stats}
    payload["collection_state_sha256"] = stable_content_digest(
        _state_material(payload)
    )

    with pytest.raises(ValueError, match="cannot exceed"):
        collection_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_recomputed_digest_cannot_hide_naive_first_catch_time():
    event = collection_event(
        _collection(),
        subject_id="player-1",
        fish_id="trout",
        action="fish_caught",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    stats = dict(payload["fish_stats"]["trout"])
    stats["first_caught"] = "2026-09-15T14:30:00"
    payload["fish_stats"] = {"trout": stats}
    payload["collection_state_sha256"] = stable_content_digest(
        _state_material(payload)
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        collection_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_collection_event_action_is_allowlisted():
    with pytest.raises(ValueError, match="unsupported collection action"):
        collection_event(
            _collection(),
            subject_id="player-1",
            fish_id="trout",
            action="delete_catalog",
            occurred_at=NOW,
        )


def test_collection_event_requires_lowercase_sha256_digest():
    event = collection_event(
        _collection(),
        subject_id="player-1",
        fish_id="trout",
        action="fish_caught",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["collection_state_sha256"] = "BAD-DIGEST"

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        collection_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )
