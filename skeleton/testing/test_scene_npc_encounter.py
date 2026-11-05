"""Playable offline NPC scenes: choices, movement, save and portable replay."""
import copy
import json

import pytest

from skeleton.game.gameplay.scene_npc_encounter import (
    _step, cli, demo_actions, export_encounter, import_encounter,
    new_encounter, normalize_encounter, original_encounter,
    resume_encounter, simulate_encounter, verify_encounter,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _won():
    return simulate_encounter(original_encounter(), demo_actions())


def test_original_npc_encounter_reaches_verified_ending():
    saved = _won()
    assert saved["state"]["phase"] == "finished"
    assert saved["state"]["ending"] == "rescued"
    assert saved["state"]["flags"] == ["keeper_trust"]
    assert saved["state"]["scene"]["state"]["phase"] == "won"
    assert verify_encounter(json.loads(json.dumps(saved))) == saved
    assert import_encounter(export_encounter(saved)) == saved


def test_resume_checkpoint_equals_single_pass():
    source = original_encounter()
    actions = demo_actions()
    first = simulate_encounter(source, actions[:2])
    assert first["state"]["scene"]["state"]["scene_id"] == "quay"
    resumed = resume_encounter(json.loads(json.dumps(first)), actions[2:])
    assert resumed == simulate_encounter(source, actions)


def test_decline_choice_changes_earned_ending():
    actions = demo_actions()
    actions[0] = {"kind": "talk", "npc_id": "quay_keeper", "offer_id": "decline"}
    actions[-1] = {"kind": "finish", "ending_id": "solo"}
    saved = simulate_encounter(original_encounter(), actions)
    assert saved["state"]["flags"] == ["keeper_declined"]
    assert saved["state"]["reputation"] == -2
    assert saved["state"]["ending"] == "solo"
    with pytest.raises(SceneTravelError, match="flags not earned"):
        _step(simulate_encounter(original_encounter(), actions[:-1]),
              {"kind": "finish", "ending_id": "rescued"})


def test_npc_cannot_grant_twice_or_appear_at_wrong_scene():
    source = original_encounter()
    first = _step(new_encounter(source), demo_actions()[0])
    with pytest.raises(SceneTravelError, match="already answered"):
        _step(first, demo_actions()[0])
    moved = simulate_encounter(source, demo_actions()[:3])
    with pytest.raises(SceneTravelError, match="absent"):
        _step(moved, {"kind": "talk", "npc_id": "quay_keeper", "offer_id": "assist"})


def test_cannot_finish_before_terminal_scene():
    with pytest.raises(SceneTravelError, match="requires terminal"):
        _step(new_encounter(original_encounter()),
              {"kind": "finish", "ending_id": "rescued"})


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(source_digest="0" * 64),
    lambda s: s["state"].update(flags=["keeper_declined"]),
    lambda s: s["state"].update(reputation=900),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["state"]["scene"].update(state_digest="0" * 64),
    lambda s: s["save"].update(parent_save_digest=None),
    lambda s: s["state"].update(ending="solo"),
])
def test_forged_npc_save_fails_closed(mutation):
    saved = _won()
    bad = copy.deepcopy(saved)
    mutation(bad)
    with pytest.raises(SceneTravelError):
        verify_encounter(bad)


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(schema_version="unknown"),
    lambda s: s["npcs"].append(copy.deepcopy(s["npcs"][0])),
    lambda s: s["npcs"][0].update(route=["sanctuary"]),
    lambda s: s["npcs"][0]["offers"].append(copy.deepcopy(s["npcs"][0]["offers"][0])),
    lambda s: s["npcs"][0]["offers"][0].update(reputation=True),
    lambda s: s["endings"][0].update(requires_flags=["unearned"]),
    lambda s: s["endings"][0].update(scene_phase="future"),
])
def test_bad_authored_npc_contract_rejected(mutation):
    source = original_encounter()
    mutation(source)
    with pytest.raises(SceneTravelError):
        normalize_encounter(source)


def test_portable_bundle_rejects_corruption():
    bundle = export_encounter(_won())
    bad = copy.deepcopy(bundle)
    bad["checksum"] = "0" * 64
    with pytest.raises(SceneTravelError, match="checksum"):
        import_encounter(bad)


def test_cli_is_canonical_and_rejects_bad_source(capsys):
    from skeleton.__main__ import main
    assert main(["scene-npc", "demo"]) == 0
    session = json.loads(capsys.readouterr().out)
    assert session["state"]["phase"] == "finished"
    assert cli(["verify", "--session-json", json.dumps(session)]) == 0
    assert json.loads(capsys.readouterr().out) == session
    assert cli(["simulate", "--source-json", '{"bad":true}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
