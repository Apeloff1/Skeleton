"""End-to-end combat contract replay, earned reward and source-policy tests."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, original_demo
from skeleton.game.gameplay.combat_contract import (
    cli, demo_contract, export_contract, import_contract, new_contract,
    normalize_contract, original_contract, resume_contract, simulate_contract,
    verify_contract,
)


def test_original_contract_is_playable_and_rewards_are_earned():
    saved = demo_contract()
    assert saved["state"]["phase"] == "won"
    assert saved["state"]["credits"] == 14
    assert saved["state"]["inventory"] == {"bridge_pass": 1}
    assert all(saved["state"]["objectives"].values())
    assert verify_contract(json.loads(json.dumps(saved))) == saved
    assert import_contract(json.loads(json.dumps(export_contract(saved)))) == saved


@pytest.mark.parametrize("split", [0, 1, 2, 3])
def test_every_checkpoint_split_has_identical_lineage(split):
    _, actions = original_demo()
    whole = simulate_contract(original_contract(), actions)
    part = simulate_contract(original_contract(), actions[:split])
    assert resume_contract(part, actions[split:]) == whole


def test_unearned_guard_objective_denies_rewards_after_combat_victory():
    source = original_contract()
    source["objectives"].append(
        {"id": "defensive_discipline", "kind": "guard", "minimum": 1}
    )
    _, actions = original_demo()
    saved = simulate_contract(source, actions)
    assert saved["state"]["combat"]["state"]["phase"] == "won"
    assert saved["state"]["phase"] == "failed"
    assert saved["state"]["credits"] == 0
    assert saved["state"]["inventory"] == {}
    assert verify_contract(saved) == saved


def test_speed_gate_cannot_be_claimed_by_faster_receipt():
    source = original_contract()
    source["objectives"][1]["maximum_turns"] = 2
    _, actions = original_demo()
    saved = simulate_contract(source, actions)
    assert saved["state"]["phase"] == "failed"
    assert saved["state"]["objectives"]["swift_resolution"] is False


@pytest.mark.parametrize("mutate", [
    lambda s: s.update(player_team="outsiders"),
    lambda s: s["objectives"].append(s["objectives"][0]),
    lambda s: s["objectives"][0].update(actor_id="scout"),
    lambda s: s["objectives"][1].update(maximum_turns=True),
    lambda s: s["objectives"][1].update(maximum_turns=999),
    lambda s: s["reward"].update(credits=-1),
    lambda s: s["reward"].update(item_id="unsafe / path"),
    lambda s: s.update(unexpected=True),
    lambda s: s["objectives"][0].update(kind="execute"),
])
def test_invalid_authoring_fails_closed(mutate):
    source = original_contract()
    mutate(source)
    with pytest.raises(CombatSessionError):
        normalize_contract(source)


@pytest.mark.parametrize("mutate", [
    lambda s: s["state"].update(credits=999),
    lambda s: s["state"]["inventory"].update(bridge_pass=99),
    lambda s: s["state"]["objectives"].update(swift_resolution=False),
    lambda s: s["state"]["combat"]["state"].update(winner="reedbound"),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["journal"][0]["action"].update(kind="guard"),
    lambda s: s["save"].update(parent_save_digest=None),
    lambda s: s.update(source_digest="0" * 64),
])
def test_tampered_nested_replay_is_rejected(mutate):
    saved = copy.deepcopy(demo_contract())
    mutate(saved)
    with pytest.raises(CombatSessionError):
        verify_contract(saved)


def test_rejected_action_does_not_mutate_prior_checkpoint():
    saved = new_contract(original_contract())
    frozen = copy.deepcopy(saved)
    with pytest.raises(CombatSessionError):
        resume_contract(saved, [{"kind": "attack", "actor_id": "warden",
                                 "target_id": "scout"}])
    assert saved == frozen
    with pytest.raises(CombatSessionError):
        resume_contract(saved, [{}] * 1000)


def test_bundle_tamper_is_rejected_even_with_recomputed_checksum():
    bundle = export_contract(demo_contract())
    for change in (
        lambda b: b.update(state_digest="0" * 64),
        lambda b: b["session"]["state"].update(credits=999),
        lambda b: b["session"]["journal"][0].update(receipt="0" * 64),
    ):
        bad = copy.deepcopy(bundle)
        change(bad)
        bad["checksum"] = dig({k: v for k, v in bad.items() if k != "checksum"})
        with pytest.raises(CombatSessionError):
            import_contract(bad)


def test_cli_real_entrypoint_play_export_import(capsys):
    from skeleton.__main__ import main
    assert main(["combat-contract", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["phase"] == "won"
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert main(["combat-contract", "simulate", "--source-json", "{}",
                 "--actions-json", "[]"]) == 2
