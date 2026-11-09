from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace

import pytest

from skeleton.frontier.breeding import OffspringPlan
from skeleton.frontier.breeding_adapters import (
    achievement_signals_from_offspring,
    breeding_event_to_memory_item,
    breeding_offspring_digest,
    breeding_offspring_event,
    breeding_offspring_identity,
)
from skeleton.frontier.events import DomainEvent


def _plan() -> OffspringPlan:
    return OffspringPlan(
        id="offspring-1",
        species="rainbow_bass",
        name="Rainbow Bass",
        traits={"color": "rainbow", "rarity_gene": "rare"},
        size=61.5,
        value=1125,
        parents=("bass", "koi"),
        bred_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
        special_breed_id="rainbow_bass",
        is_new_discovery=True,
        xp_reward=60,
    )


def test_breeding_event_maps_to_stable_memory_identity():
    plan = _plan()
    event = breeding_offspring_event(
        plan,
        subject_id="player-1",
        occurred_at=plan.bred_at,
    )
    item = breeding_event_to_memory_item(event)
    assert item["id"] == breeding_offspring_identity("player-1", "offspring-1")
    assert item["metadata"]["breeding_offspring_sha256"] == breeding_offspring_digest(plan)
    assert item["metadata"]["species"] == "rainbow_bass"
    assert item["metadata"]["is_new_discovery"] is True


def test_breeding_event_rejects_tampered_offspring_payload():
    plan = _plan()
    event = breeding_offspring_event(
        plan,
        subject_id="player-1",
        occurred_at=plan.bred_at,
    )
    payload = dict(event.payload)
    payload["value"] = 1
    tampered = DomainEvent(
        topic=event.topic,
        payload=payload,
        occurred_at=event.occurred_at,
    )
    with pytest.raises(ValueError, match="offspring digest mismatch"):
        breeding_event_to_memory_item(tampered)


def test_breeding_event_rejects_identity_rebinding():
    plan = _plan()
    event = breeding_offspring_event(
        plan,
        subject_id="player-1",
        occurred_at=plan.bred_at,
    )
    payload = dict(event.payload)
    payload["subject_id"] = "player-2"
    rebound = DomainEvent(
        topic=event.topic,
        payload=payload,
        occurred_at=event.occurred_at,
    )
    with pytest.raises(ValueError, match="identity digest mismatch"):
        breeding_event_to_memory_item(rebound)


def test_special_breed_projects_to_existing_achievement_signal():
    assert achievement_signals_from_offspring(_plan()) == {"special_breed": 1}
    normal = replace(_plan(), special_breed_id=None, is_new_discovery=False, xp_reward=10)
    assert achievement_signals_from_offspring(normal) == {"special_breed": 0}
