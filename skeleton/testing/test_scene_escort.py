"""Playable convoy delivery, earned supplies, replay and export contracts."""
from __future__ import annotations

import json

import pytest

from skeleton.game.gameplay.scene_escort import (
    cli, demo_actions, export_escort, import_escort,
    normalize_escort_source, original_escort, resume_escort,
    simulate_escort, verify_escort,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_full_original_escort_delivers_earned_reward():
    saved = simulate_escort(original_escort(), demo_actions())
    assert saved["state"]["phase"] == "delivered"
    assert saved["state"]["integrity"] == 1
    assert saved["state"]["reward"] == 20
    assert saved["state"]["supplies"] == 0
    assert saved["state"]["mission"]["state"]["ending"] == "lantern_restored"
    assert verify_escort(json.loads(json.dumps(saved))) == saved
    assert import_escort(json.loads(json.dumps(export_escort(saved)))) == saved


def test_every_checkpoint_replays_to_same_terminal_save():
    actions = demo_actions()
    expected = simulate_escort(original_escort(), actions)
    for cut in range(len(actions) + 1):
        partial = simulate_escort(original_escort(), actions[:cut])
        assert resume_escort(json.loads(json.dumps(partial)), actions[cut:]) == expected


def test_without_protection_convoy_is_lost_and_reward_never_granted():
    actions = [a for a in demo_actions() if a["kind"] != "protect"]
    lost = simulate_escort(original_escort(), actions[:-1])
    assert lost["state"]["phase"] == "lost"
    assert lost["state"]["integrity"] == 0
    assert lost["state"]["reward"] == 0
    with pytest.raises(SceneTravelError, match="terminal"):
        resume_escort(lost, [actions[-1]])


def test_supply_cannot_be_minted_or_shield_stacked():
    source = original_escort()
    with pytest.raises(SceneTravelError, match="earned"):
        simulate_escort(source, [{"kind": "protect"}])
    actions = demo_actions()
    with pytest.raises(SceneTravelError, match="earned"):
        simulate_escort(source, [*actions[:3], {"kind": "protect"}])


def test_hazard_damage_and_recovery_follow_authored_source():
    source = original_escort()
    source["hazards"] = [{"scene_id": "sanctuary", "damage": 1}]
    saved = simulate_escort(source, demo_actions()[:-1])
    assert saved["state"]["phase"] == "lost"
    assert saved["state"]["reward"] == 0
    assert verify_escort(saved) == saved


@pytest.mark.parametrize("mutate", [
    lambda s: s.update(schema_version="future"),
    lambda s: s.update(destination_scene="missing"),
    lambda s: s.update(destination_scene="quay"),
    lambda s: s.update(max_integrity=True),
    lambda s: s.update(travel_damage=-1),
    lambda s: s.update(turn_budget=0),
    lambda s: s.update(delivery_reward=10001),
    lambda s: s["supply_pickups"].append("quay:missing"),
    lambda s: s["supply_pickups"].append("quay:find_key"),
    lambda s: s["hazards"].append({"scene_id": "missing", "damage": 1}),
    lambda s: s["hazards"].append({"scene_id": "sanctuary", "damage": True}),
])
def test_invalid_authored_source_is_rejected(mutate):
    source = original_escort()
    mutate(source)
    with pytest.raises(SceneTravelError):
        normalize_escort_source(source)


@pytest.mark.parametrize("mutate", [
    lambda s: s["state"].update(reward=999),
    lambda s: s["state"].update(integrity=100),
    lambda s: s["state"].update(supplies=50),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["source"].update(delivery_reward=999),
    lambda s: s["save"].update(tick=999),
    lambda s: s.update(event_bus_digest="0" * 64),
])
def test_tampered_session_fails_closed(mutate):
    saved = simulate_escort(original_escort(), demo_actions())
    mutate(saved)
    with pytest.raises(SceneTravelError):
        verify_escort(saved)


def test_tampered_portable_bundle_fails_closed():
    bundle = export_escort(simulate_escort(original_escort(), demo_actions()))
    bundle["session"]["state"]["reward"] = 9999
    with pytest.raises(ValueError):
        import_escort(bundle)


def test_invalid_action_and_turn_budget_fail_closed():
    with pytest.raises(SceneTravelError, match="unsupported"):
        simulate_escort(original_escort(), [{"kind": "grant", "reward": 999}])
    source = original_escort()
    source["turn_budget"] = 2
    with pytest.raises(SceneTravelError, match="budget"):
        simulate_escort(source, demo_actions()[:3])


def test_cli_demo_and_bad_payload(capsys):
    assert cli(["demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["phase"] == "delivered"
    assert cli(["simulate", "--source-json", "{}", "--actions-json", "[]"]) == 2
    assert "error" in capsys.readouterr().err
