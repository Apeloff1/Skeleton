"""Campaign stage transitions, replay custody and offline packaging."""
import copy
import json

import pytest

from skeleton.game.gameplay.scene_survival_campaign import (
    SCHEMA, cli, export_campaign, import_campaign, new_campaign,
    normalize_campaign, original_campaign, resume_campaign,
    simulate_campaign, verify_campaign,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_campaign_is_playable_and_rewards_only_verified_wins():
    source, actions = original_campaign()
    finished = simulate_campaign(source, actions)
    assert finished["state"]["phase"] == "won"
    assert finished["state"]["score"] == 30
    assert [s["stage_id"] for s in finished["state"]["completed"]] == [
        "quay_crossing", "gate_return",
    ]
    assert finished["state"]["stage_index"] == 1
    assert finished["state"]["tick"] == len(actions)
    assert verify_campaign(finished) == finished


def test_save_resume_across_stage_boundary_and_portable_roundtrip():
    source, actions = original_campaign()
    first = simulate_campaign(source, actions[:len(actions) // 2])
    assert first["state"]["stage_index"] == 1
    assert first["state"]["score"] == 10
    assert first["state"]["stage"]["state"]["tick"] == 0
    restored = import_campaign(export_campaign(first))
    final = resume_campaign(restored, actions[len(actions) // 2:])
    assert final == simulate_campaign(source, actions)
    assert import_campaign(export_campaign(final)) == final


def test_unauthorized_rewards_and_source_mutations_fail_closed():
    source, actions = original_campaign()
    checkpoint = simulate_campaign(source, actions)
    for path, value in (
        (("state", "score"), 1000),
        (("state", "completed"), []),
        (("state_digest",), "0" * 64),
        (("source_digest",), "0" * 64),
        (("save", "parent_save_digest"), "0" * 64),
    ):
        forged = copy.deepcopy(checkpoint)
        target = forged
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(SceneTravelError):
            verify_campaign(forged)
    forged = copy.deepcopy(export_campaign(checkpoint))
    forged["session"]["state"]["score"] += 1
    with pytest.raises(SceneTravelError):
        import_campaign(forged)


def test_replayed_actions_cannot_be_modified_or_reordered():
    source, actions = original_campaign()
    session = simulate_campaign(source, actions)
    changed = copy.deepcopy(session)
    changed["journal"][0]["action"] = {"kind": "rest"}
    with pytest.raises(SceneTravelError):
        verify_campaign(changed)
    changed = copy.deepcopy(session)
    changed["journal"][0], changed["journal"][1] = (
        changed["journal"][1], changed["journal"][0]
    )
    with pytest.raises(SceneTravelError):
        verify_campaign(changed)
    with pytest.raises(SceneTravelError, match="terminal"):
        resume_campaign(session, [actions[0]])


@pytest.mark.parametrize("mutate", [
    lambda s: s.update(schema_version="unknown"),
    lambda s: s.update(stages=[]),
    lambda s: s.update(required_score=8000),
    lambda s: s["stages"].append(s["stages"][0]),
    lambda s: s["stages"][0].update(reward=True),
    lambda s: s["stages"][0].update(stage_id="../escape"),
])
def test_rejects_invalid_campaign_sources(mutate):
    source, _ = original_campaign()
    mutate(source)
    with pytest.raises(SceneTravelError):
        normalize_campaign(source)


def test_partial_checkpoint_and_input_budgets():
    source, actions = original_campaign()
    checkpoint = new_campaign(source)
    assert checkpoint["state"]["score"] == 0
    assert checkpoint["state"]["completed"] == []
    partial = resume_campaign(checkpoint, actions[:2])
    assert partial["state"]["phase"] == "active"
    assert partial["state"]["score"] == 0
    assert verify_campaign(partial) == partial
    with pytest.raises(SceneTravelError):
        resume_campaign(partial, "east")
    with pytest.raises(SceneTravelError):
        resume_campaign(partial, [actions[0]] * 513)


def test_cli_and_schema_roundtrip(capsys):
    source, actions = original_campaign()
    assert source["schema_version"] == SCHEMA
    assert cli(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["state"]["phase"] == "won"
    assert cli(["simulate", "--source-json", json.dumps(source),
                "--actions-json", json.dumps(actions)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert cli(["export", "--session-json", json.dumps(result)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == result
    assert cli(["verify", "--session-json", "{}"]) == 2
    assert "error" in capsys.readouterr().err
