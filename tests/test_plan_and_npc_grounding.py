"""A plan or an NPC is not accepted when nothing grounds it."""

import pytest

from skeleton.intelligence.npc_verifier import NpcVerifier
from skeleton.intelligence.plan_verifier import PlanVerifier


def test_a_plan_without_a_vision_is_not_accepted() -> None:
    plan = {"era": "soulslike", "primary_dps": "bleed", "room_bias": "ruins"}
    refused = PlanVerifier(accept_at=0.7).verify(plan)
    assert refused.accepted is False
    assert any(issue.startswith("hard:") for issue in refused.issues)
    accepted = PlanVerifier(accept_at=0.7).verify(plan, vision="soulslike ruins")
    assert accepted.accepted is True
    with pytest.raises(ValueError):
        PlanVerifier(accept_at=0)


def test_a_string_is_not_a_dialogue_tree() -> None:
    spec = {
        "name": "merchant",
        "persona": {"archetype": "mentor", "traits": ["mentor"]},
        "dialogue_tree": "hello there",
        "behaviour_graph": [{"id": "idle"}, {"id": "talk"}],
    }
    refused = NpcVerifier(accept_at=0.7).verify(spec, description="merchant mentor")
    assert refused.accepted is False
    spec["dialogue_tree"] = [{"id": "hello"}, {"id": "farewell"}]
    accepted = NpcVerifier(accept_at=0.7).verify(spec, description="merchant mentor")
    assert accepted.accepted is True
