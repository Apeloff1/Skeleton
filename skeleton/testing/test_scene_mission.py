"""Source-bound mission DAG, branching choices, replay and export acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_mission import (
    _advance, cli, demo_actions, export_mission, import_mission, new_mission,
    normalize_mission_world, original_mission, resume_mission, simulate_mission,
    verify_mission,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_complete_playable_mission_reaches_restored_ending():
    source = original_mission()
    saved = simulate_mission(source, demo_actions())
    assert saved["state"]["phase"] == "finished"
    assert saved["state"]["ending"] == "lantern_restored"
    assert saved["state"]["scene"]["state"]["phase"] == "won"
    assert saved["state"]["missions"] == [
        "pledge", "recover_key", "reach_sanctuary",
    ]
    assert saved["state"]["reputation"] == 6
    assert verify_mission(json.loads(json.dumps(saved))) == saved
    assert import_mission(json.loads(json.dumps(export_mission(saved)))) == saved


def test_partial_save_resume_is_deterministic_for_every_boundary():
    actions = demo_actions()
    source = original_mission()
    complete = simulate_mission(source, actions)
    for cut in range(len(actions) + 1):
        partial = simulate_mission(source, actions[:cut])
        assert resume_mission(json.loads(json.dumps(partial)), actions[cut:]) == complete


def test_declining_choice_changes_earned_missions_and_ending():
    actions = demo_actions()
    actions[0]["option_id"] = "decline"
    actions[-1]["ending_id"] = "unpledged_victory"
    saved = simulate_mission(original_mission(), actions)
    assert saved["state"]["reputation"] == -2
    assert saved["state"]["missions"] == []
    assert saved["state"]["ending"] == "unpledged_victory"
    with pytest.raises(SceneTravelError, match="mission requirements"):
        simulate_mission(original_mission(), [*actions[:-1], {
            "kind": "finish", "ending_id": "lantern_restored",
        }])


def test_failure_ending_is_replay_proven():
    saved = simulate_mission(original_mission(), [
        {"kind": "scene", "action": {"kind": "travel", "exit_id": "down"}},
        {"kind": "finish", "ending_id": "sinkhole_failure"},
    ])
    assert saved["state"]["scene"]["state"]["phase"] == "lost"
    assert saved["state"]["ending"] == "sinkhole_failure"
    assert verify_mission(saved) == saved


@pytest.mark.parametrize("actions,pattern", [
    ([{"kind": "finish", "ending_id": "lantern_restored"}], "not earned"),
    ([{"kind": "choose", "choice_id": "missing", "option_id": "help"}],
     "unavailable"),
    ([{"kind": "choose", "choice_id": "restore_lantern",
       "option_id": "missing"}], "invalid choice option"),
    ([{"kind": "choose", "choice_id": "restore_lantern",
       "option_id": "help"},
      {"kind": "choose", "choice_id": "restore_lantern",
       "option_id": "help"}], "already resolved"),
    ([{"kind": "scene", "action": {"kind": "travel", "exit_id": "north"}}],
     "uncollected"),
])
def test_unearned_decisions_and_travel_fail_closed(actions, pattern):
    with pytest.raises(SceneTravelError, match=pattern):
        simulate_mission(original_mission(), actions)


def test_terminal_scene_cannot_take_more_world_actions():
    saved = simulate_mission(original_mission(), [
        {"kind": "scene", "action": {"kind": "travel", "exit_id": "down"}},
    ])
    with pytest.raises(SceneTravelError, match="terminal"):
        _advance(saved, {"kind": "scene", "action": {
            "kind": "travel", "exit_id": "north",
        }})


@pytest.mark.parametrize("mutate", [
    lambda s: s.update(schema_version="future"),
    lambda s: s["missions"][0]["requires"].append("missing"),
    lambda s: s["missions"][0]["requires"].append("reach_sanctuary"),
    lambda s: s["missions"][0]["trigger"].update(value="missing"),
    lambda s: s["missions"][0]["trigger"].update(kind="execute"),
    lambda s: s["choices"][0].update(scene_id="sanctuary"),
    lambda s: s["choices"][0]["options"][0].update(reputation=True),
    lambda s: s["endings"][0]["requires"].append("unknown"),
    lambda s: s["endings"][0].update(min_reputation=10001),
])
def test_bad_authored_mission_rejected(mutate):
    source = original_mission()
    mutate(source)
    with pytest.raises(SceneTravelError):
        normalize_mission_world(source)


@pytest.mark.parametrize("mutate", [
    lambda s: s["state"].update(reputation=1000),
    lambda s: s["state"]["scene"]["state"].update(scene_id="sanctuary"),
    lambda s: s["state"]["missions"].append("phantom"),
    lambda s: s["state"]["choices"].update(restore_lantern="decline"),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["save"].update(parent_save_digest=None),
    lambda s: s.update(source_digest="0" * 64),
])
def test_save_tamper_is_detected(mutate):
    saved = simulate_mission(original_mission(), demo_actions())
    bad = copy.deepcopy(saved)
    mutate(bad)
    with pytest.raises(SceneTravelError):
        verify_mission(bad)


def test_bundle_tamper_detected():
    saved = simulate_mission(original_mission(), demo_actions())
    bundle = export_mission(saved)
    for mutate in (
        lambda b: b.update(checksum="0" * 64),
        lambda b: b.update(source_digest="0" * 64),
        lambda b: b["session"]["state"].update(reputation=999),
    ):
        bad = copy.deepcopy(bundle)
        mutate(bad)
        with pytest.raises(SceneTravelError):
            import_mission(bad)


def test_action_limits_and_strict_fields():
    with pytest.raises(SceneTravelError):
        resume_mission(new_mission(original_mission()), [
            {"kind": "choose", "choice_id": "restore_lantern",
             "option_id": "help", "script": "evil"},
        ])
    with pytest.raises(SceneTravelError, match="batch"):
        resume_mission(new_mission(original_mission()), [
            {"kind": "scene", "action": {"kind": "collect", "pickup_id": "find_key"}}
        ] * 513)


def test_installed_cli_end_to_end(capsys):
    from skeleton.__main__ import main
    assert main(["scene-mission", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["ending"] == "lantern_restored"
    assert cli(["verify", "--session-json", json.dumps(saved)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"bad":true}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
