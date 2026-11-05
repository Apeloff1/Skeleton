"""Replay, NPC rescue, earned protection and consequence acceptance contracts."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_evacuation import (
    advance_evacuation, demo_actions, export_evacuation, import_evacuation,
    new_evacuation, normalize_evacuation, original_evacuation,
    resume_evacuation, simulate_evacuation, verify_evacuation,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_rescue_earns_two_survivors_and_only_authored_reward():
    source, actions = original_evacuation(), demo_actions()
    saved = simulate_evacuation(source, actions)
    assert saved["state"]["phase"] == "evacuated"
    assert saved["state"]["reward"] == 60
    assert saved["state"]["rescued"] == ["dock_apprentice", "watch_keeper"]
    assert saved["state"]["lost"] == []
    assert saved["state"]["supplies"] == 0
    assert saved["state"]["shielded"] is False
    assert saved["state"]["mission"]["state"]["ending"] == "lantern_restored"
    assert [p["health"] for p in saved["state"]["passengers"]] == [2, 2]
    assert verify_evacuation(json.loads(json.dumps(saved))) == saved
    assert import_evacuation(json.loads(json.dumps(export_evacuation(saved)))) == saved


def test_every_intermediate_checkpoint_restores_identical_canonical_replay():
    source, actions = original_evacuation(), demo_actions()
    expected = simulate_evacuation(source, actions)
    for cut in range(len(actions) + 1):
        checkpoint = simulate_evacuation(source, actions[:cut])
        assert resume_evacuation(json.loads(json.dumps(checkpoint)),
                                 actions[cut:]) == expected


def test_protection_requires_earned_pickup_and_cannot_stack():
    source = original_evacuation()
    with pytest.raises(SceneTravelError, match="earned"):
        simulate_evacuation(source, [{"kind": "protect"}])
    actions = demo_actions()
    before = simulate_evacuation(source, actions[:2])
    protected = advance_evacuation(before, {"kind": "protect"})
    with pytest.raises(SceneTravelError, match="earned"):
        advance_evacuation(protected, {"kind": "protect"})
    assert protected["state"]["supplies"] == 0
    assert protected["state"]["shielded"] is True


def test_hazard_can_kill_passenger_and_partial_victory_never_mints_reward():
    source = original_evacuation()
    source["npcs"][0]["health"] = 1
    actions = [a for a in demo_actions() if a["kind"] != "protect"]
    result = simulate_evacuation(source, actions)
    assert result["state"]["phase"] == "partial"
    assert result["state"]["reward"] == 0
    assert "dock_apprentice" in result["state"]["lost"]
    assert len(result["state"]["passengers"]) == 1


def test_rescue_cannot_teleport_duplicate_or_overfill():
    source = original_evacuation()
    with pytest.raises(SceneTravelError, match="available"):
        simulate_evacuation(source, [{"kind": "rescue", "npc_id": "watch_keeper"}])
    first = simulate_evacuation(source, [{"kind": "rescue", "npc_id": "dock_apprentice"}])
    with pytest.raises(SceneTravelError, match="available"):
        advance_evacuation(first, {"kind": "rescue", "npc_id": "dock_apprentice"})
    source["capacity"] = 1
    source["required_rescues"] = 1
    actions = demo_actions()[:6]
    full = simulate_evacuation(source, actions)
    with pytest.raises(SceneTravelError, match="capacity"):
        advance_evacuation(full, {"kind": "rescue", "npc_id": "watch_keeper"})


def test_npc_expiry_and_turn_budget_fail_closed():
    source = original_evacuation()
    source["npcs"][0]["expires_at"] = 0
    waited = simulate_evacuation(source, [{"kind": "wait"}])
    assert waited["state"]["lost"] == ["dock_apprentice"]
    with pytest.raises(SceneTravelError, match="available"):
        advance_evacuation(waited, {"kind": "rescue", "npc_id": "dock_apprentice"})
    source = original_evacuation()
    source["turn_budget"] = 1
    source["npcs"][1]["expires_at"] = 1
    source["npcs"][0]["expires_at"] = 1
    expired = simulate_evacuation(source, [{"kind": "wait"}])
    assert expired["state"]["phase"] == "expired"
    with pytest.raises(SceneTravelError, match="terminal"):
        advance_evacuation(expired, {"kind": "wait"})


@pytest.mark.parametrize("mutate", [
    lambda s: s.update(schema_version="future"),
    lambda s: s.update(capacity=True),
    lambda s: s.update(required_rescues=0),
    lambda s: s.update(required_rescues=3),
    lambda s: s.update(turn_budget=97),
    lambda s: s["npcs"][0].update(health=0),
    lambda s: s["npcs"][0].update(scene_id="sinkhole"),
    lambda s: s["npcs"][0].update(expires_at=-1),
    lambda s: s["npcs"][0].update(available_from=10, expires_at=2),
    lambda s: s["npcs"][1].update(id="dock_apprentice"),
    lambda s: s["supplies"].append("quay:unknown"),
    lambda s: s["supplies"].append("quay:find_bandage"),
    lambda s: s["hazards"].append({"scene_id": "gate", "damage": 1}),
    lambda s: s["hazards"].append({"scene_id": "sinkhole", "damage": 1}),
    lambda s: s["success_endings"].append("sinkhole_failure"),
    lambda s: s.update(base_reward=float("nan")),
])
def test_invalid_authored_sources_rejected(mutate):
    source = original_evacuation()
    mutate(source)
    with pytest.raises(SceneTravelError):
        normalize_evacuation(source)


@pytest.mark.parametrize("mutate", [
    lambda s: s["state"].update(reward=999),
    lambda s: s["state"].update(supplies=100),
    lambda s: s["state"]["passengers"][0].update(health=9),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["source"].update(base_reward=999),
    lambda s: s["save"].update(tick=999),
    lambda s: s.update(event_bus_digest="0" * 64),
    lambda s: s.update(state_digest="0" * 64),
])
def test_forged_save_or_event_cannot_pass_replay(mutate):
    saved = simulate_evacuation(original_evacuation(), demo_actions())
    mutate(saved)
    with pytest.raises(SceneTravelError):
        verify_evacuation(saved)


def test_export_tampering_and_wrong_source_resume_rejected():
    source = original_evacuation()
    saved = simulate_evacuation(source, demo_actions())
    bundle = export_evacuation(saved)
    bundle["session"]["state"]["reward"] = 9999
    with pytest.raises(ValueError):
        import_evacuation(bundle)
    altered = copy.deepcopy(source)
    altered["base_reward"] += 1
    with pytest.raises(SceneTravelError, match="source mismatch"):
        simulate_evacuation(altered, [], resume=new_evacuation(source))


def test_illegal_actions_and_terminal_extra_turn_fail_closed():
    with pytest.raises(SceneTravelError, match="unsupported"):
        simulate_evacuation(original_evacuation(), [{"kind": "grant", "reward": 999}])
    with pytest.raises(SceneTravelError, match="fields"):
        simulate_evacuation(original_evacuation(), [{"kind": "wait", "mint": 1}])
    final = simulate_evacuation(original_evacuation(), demo_actions())
    with pytest.raises(SceneTravelError, match="terminal"):
        advance_evacuation(final, {"kind": "wait"})
