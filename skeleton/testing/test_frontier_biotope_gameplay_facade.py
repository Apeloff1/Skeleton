from __future__ import annotations

from datetime import datetime, timezone

import skeleton.frontier.gameplay as gameplay


NOW = datetime(2026, 9, 15, 13, 30, tzinfo=timezone.utc)


def test_gameplay_facade_exposes_single_canonical_biotope_surface():
    assert gameplay.BiotopeProgress.__module__ == "skeleton.frontier.biotope"
    assert gameplay.BiotopeSpec.__module__ == "skeleton.frontier.biotope"
    assert gameplay.BiotopeStageSpec.__module__ == "skeleton.frontier.biotope"
    assert gameplay.biotope_event.__module__ == "skeleton.frontier.biotope_adapters"
    assert gameplay.enter_biotope_stage.__module__ == "skeleton.frontier.biotope"
    assert gameplay.unlock_biotope_stage.__module__ == "skeleton.frontier.biotope"


def test_gameplay_facade_composes_biotope_progress_with_event_memory():
    progress = gameplay.record_biotope_catch(
        gameplay.initial_biotope_progress(),
        "freshwater_lake",
        xp_earned=25,
    ).progress
    event = gameplay.biotope_event(
        progress,
        subject_id="player-1",
        action="catch_recorded",
        occurred_at=NOW,
    )
    memory = gameplay.biotope_event_to_memory_item(event)

    assert memory["metadata"]["total_catches"] == 1
    assert memory["metadata"]["current_biotope"] == "freshwater_lake"
    assert memory["metadata"]["biotope_progress_sha256"] == (
        gameplay.biotope_progress_digest(progress)
    )
