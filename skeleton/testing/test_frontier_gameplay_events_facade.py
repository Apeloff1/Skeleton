from __future__ import annotations

from datetime import datetime, timezone

import skeleton.frontier.gameplay as gameplay


NOW = datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc)


def _record():
    return {
        "id": "midnight_madness",
        "duration_days": 3,
        "time_restriction": {"start_hour": 20, "end_hour": 6},
        "challenges": [
            {
                "id": "night_catches",
                "target": 10,
                "reward": {"coins": 1000, "event_tokens": 25},
            }
        ],
        "rewards": {1000: {"coins": 1000, "event_tokens": 100}},
        "multipliers": {"xp": 2.5},
    }


def test_gameplay_facade_exposes_distinct_gameplay_event_policy_surface():
    assert gameplay.GameplayEventSpec.__module__ == "skeleton.frontier.gameplay_events"
    assert gameplay.GameplayEventProgress.__module__ == (
        "skeleton.frontier.gameplay_events"
    )
    assert gameplay.gameplay_event_transition.__module__ == (
        "skeleton.frontier.gameplay_event_adapters"
    )
    assert gameplay.gameplay_event_to_memory_item.__module__ == (
        "skeleton.frontier.gameplay_event_adapters"
    )
    assert not hasattr(gameplay, "EventBus")
    assert not hasattr(gameplay, "DomainEvent")


def test_gameplay_facade_composes_update_transition_and_memory():
    spec = gameplay.gameplay_event_from_record(_record())
    progress = gameplay.initial_event_progress(spec, joined_at=NOW)
    update = gameplay.update_event_progress(
        progress,
        spec,
        points_earned=1000,
        challenge_progress={"night_catches": 10},
    )
    transition = gameplay.gameplay_event_transition(
        update.progress,
        spec,
        subject_id="player-1",
        action="challenge_completed",
        occurred_at=NOW,
    )
    memory = gameplay.gameplay_event_to_memory_item(transition)

    assert memory["metadata"]["gameplay_event_id"] == "midnight_madness"
    assert memory["metadata"]["points"] == 1000
    assert memory["metadata"]["event_tokens"] == 25
    assert memory["metadata"]["completed_challenge_count"] == 1
    assert memory["metadata"]["gameplay_event_progress_sha256"] == (
        gameplay.gameplay_event_progress_digest(update.progress)
    )
