from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.frontier.biotope import initial_progress, record_catch
from skeleton.frontier.biotope_adapters import (
    biotope_event,
    biotope_event_to_memory_item,
    biotope_identity,
    biotope_progress_digest,
    biotope_progress_memory_item,
)
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent


NOW = datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc)
_PROGRESS_KEYS = (
    "unlocked_biotopes",
    "unlocked_stages",
    "current_biotope",
    "current_stage",
    "biotope_xp",
    "biotope_level",
    "fish_caught_by_biotope",
)


def _raw_progress_payload(payload):
    return {key: payload[key] for key in _PROGRESS_KEYS}


def test_biotope_event_projects_stable_identity_digest_and_progress_evidence():
    progress = record_catch(
        initial_progress(),
        "freshwater_lake",
        xp_earned=25,
    ).progress
    event = biotope_event(
        progress,
        subject_id="player-1",
        action="catch_recorded",
        occurred_at=NOW,
    )
    memory = biotope_event_to_memory_item(event)
    snapshot = biotope_progress_memory_item(progress, subject_id="player-1")

    assert event.topic == "biotope.catch_recorded"
    assert memory["id"] == biotope_identity("player-1") == snapshot["id"]
    assert memory["metadata"]["biotope_progress_sha256"] == biotope_progress_digest(
        progress
    )
    assert memory["metadata"]["total_catches"] == 1
    assert memory["metadata"]["highest_mastery_level"] == 1
    assert memory["metadata"]["current_stage"] == "pond"


def test_biotope_event_rejects_subject_identity_tampering():
    event = biotope_event(
        initial_progress(),
        subject_id="player-1",
        action="stage_entered",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["subject_id"] = "player-2"

    with pytest.raises(ValueError, match="identity digest mismatch"):
        biotope_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_recomputed_digest_cannot_bypass_stale_mastery_xp_rejection():
    event = biotope_event(
        initial_progress(),
        subject_id="player-1",
        action="catch_recorded",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["biotope_xp"] = {"freshwater_lake": 100}
    payload["biotope_progress_sha256"] = stable_content_digest(
        _raw_progress_payload(payload)
    )

    with pytest.raises(ValueError, match="XP residue"):
        biotope_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_recomputed_digest_cannot_hide_partial_progress_maps():
    event = biotope_event(
        initial_progress(),
        subject_id="player-1",
        action="stage_entered",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["fish_caught_by_biotope"] = {}
    payload["biotope_progress_sha256"] = stable_content_digest(
        _raw_progress_payload(payload)
    )

    with pytest.raises(ValueError, match="exactly cover unlocked biotopes"):
        biotope_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_recomputed_digest_rejects_half_populated_active_location():
    event = biotope_event(
        initial_progress(),
        subject_id="player-1",
        action="stage_entered",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["current_stage"] = None
    payload["biotope_progress_sha256"] = stable_content_digest(
        _raw_progress_payload(payload)
    )

    with pytest.raises(ValueError, match="must either both be set"):
        biotope_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_biotope_event_action_is_allowlisted():
    with pytest.raises(ValueError, match="unsupported biotope action"):
        biotope_event(
            initial_progress(),
            subject_id="player-1",
            action="drop_database",
            occurred_at=NOW,
        )


def test_biotope_event_requires_normalized_sha256_digest():
    event = biotope_event(
        initial_progress(),
        subject_id="player-1",
        action="stage_entered",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["biotope_progress_sha256"] = "NOT-A-DIGEST"

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        biotope_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )
