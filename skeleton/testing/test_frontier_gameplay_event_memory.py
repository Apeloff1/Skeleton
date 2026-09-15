from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent
from skeleton.frontier.gameplay_event_adapters import (
    gameplay_event_identity,
    gameplay_event_memory_item,
    gameplay_event_progress_digest,
    gameplay_event_spec_digest,
    gameplay_event_to_memory_item,
    gameplay_event_transition,
)
from skeleton.frontier.gameplay_events import (
    event_spec_from_record,
    initial_event_progress,
    update_event_progress,
)


NOW = datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc)


def _spec():
    return event_spec_from_record(
        {
            "id": "spring_bloom",
            "duration_days": 14,
            "challenges": [
                {
                    "id": "spring_catches",
                    "target": 100,
                    "reward": {"coins": 5000, "event_tokens": 50},
                }
            ],
            "rewards": {1000: {"coins": 1000, "event_tokens": 100}},
            "multipliers": {"xp": 2.0},
        }
    )


def _progress():
    spec = _spec()
    return update_event_progress(
        initial_event_progress(spec, joined_at=NOW),
        spec,
        points_earned=1000,
        challenge_progress={"spring_catches": 100},
    ).progress


def test_gameplay_event_transition_projects_stable_spec_and_progress_digests():
    spec = _spec()
    progress = _progress()
    event = gameplay_event_transition(
        progress,
        spec,
        subject_id="player-1",
        action="challenge_completed",
        occurred_at=NOW,
    )
    memory = gameplay_event_to_memory_item(event)
    snapshot = gameplay_event_memory_item(progress, spec, subject_id="player-1")

    assert event.topic == "gameplay_event.challenge_completed"
    assert memory["id"] == gameplay_event_identity("player-1", spec.id)
    assert memory["id"] == snapshot["id"]
    assert memory["metadata"]["gameplay_event_spec_sha256"] == (
        gameplay_event_spec_digest(spec)
    )
    assert memory["metadata"]["gameplay_event_progress_sha256"] == (
        gameplay_event_progress_digest(progress)
    )
    assert memory["metadata"]["completed_challenge_count"] == 1
    assert memory["metadata"]["points"] == 1000


def test_gameplay_event_identity_tamper_is_rejected():
    spec = _spec()
    event = gameplay_event_transition(
        _progress(),
        spec,
        subject_id="player-1",
        action="progress_updated",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["subject_id"] = "player-2"

    with pytest.raises(ValueError, match="identity digest mismatch"):
        gameplay_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_recomputed_digest_cannot_hide_premature_challenge_completion():
    spec = _spec()
    event = gameplay_event_transition(
        _progress(),
        spec,
        subject_id="player-1",
        action="challenge_completed",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    progress = dict(payload["progress"])
    progress["challenge_progress"] = {"spring_catches": 1}
    payload["progress"] = progress
    payload["gameplay_event_progress_sha256"] = stable_content_digest(progress)

    with pytest.raises(ValueError, match="has not reached target"):
        gameplay_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_recomputed_digest_cannot_hide_unreached_claimed_milestone():
    spec = _spec()
    event = gameplay_event_transition(
        _progress(),
        spec,
        subject_id="player-1",
        action="milestone_claimed",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    progress = dict(payload["progress"])
    progress["points"] = 10
    progress["milestones_claimed"] = [1000]
    payload["progress"] = progress
    payload["gameplay_event_progress_sha256"] = stable_content_digest(progress)

    with pytest.raises(ValueError, match="exceeds current event points"):
        gameplay_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_recomputed_spec_digest_still_rejects_invalid_multiplier():
    spec = _spec()
    event = gameplay_event_transition(
        _progress(),
        spec,
        subject_id="player-1",
        action="progress_updated",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    spec_payload = dict(payload["spec"])
    spec_payload["multipliers"] = {"xp": 0}
    payload["spec"] = spec_payload
    payload["gameplay_event_spec_sha256"] = stable_content_digest(spec_payload)

    with pytest.raises(ValueError, match="positive"):
        gameplay_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )


def test_transition_action_is_allowlisted():
    with pytest.raises(ValueError, match="unsupported gameplay event action"):
        gameplay_event_transition(
            _progress(),
            _spec(),
            subject_id="player-1",
            action="drop_tables",
            occurred_at=NOW,
        )


def test_transition_rejects_malformed_digest():
    spec = _spec()
    event = gameplay_event_transition(
        _progress(),
        spec,
        subject_id="player-1",
        action="progress_updated",
        occurred_at=NOW,
    )
    payload = dict(event.payload)
    payload["gameplay_event_progress_sha256"] = "BAD"

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        gameplay_event_to_memory_item(
            DomainEvent(event.topic, payload, event.occurred_at)
        )
