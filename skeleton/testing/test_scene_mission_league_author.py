"""Scoring authoring never rewrites earned results or bypasses replay."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_mission import demo_actions, original_mission
from skeleton.game.gameplay.scene_mission_league import (
    demo_league, new_league, original_rules,
)
from skeleton.game.gameplay.scene_mission_league_author import (
    cli, demo_edit, edit_league, export_edit, import_edit, preview_edit,
    verify_edit,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _empty():
    return new_league(original_mission(), original_rules())


def test_original_scoring_authoring_replays_and_previews_real_play():
    receipt = demo_edit()
    assert receipt["before_digest"] != receipt["after_digest"]
    assert receipt["after"]["rules"]["victory_bonus"] == 250
    assert verify_edit(json.loads(json.dumps(receipt))) == receipt
    assert import_edit(json.loads(json.dumps(export_edit(receipt)))) == receipt
    preview = preview_edit(receipt, demo_actions())
    assert preview["playable_score"]["score"] > 0
    assert preview["after_digest"] == receipt["after_digest"]


def test_multi_field_edits_have_deterministic_order_and_receipt():
    base = _empty()
    changes = [
        {"field": "victory_bonus", "value": 300},
        {"field": "action_cost", "value": 4},
    ]
    first = edit_league(base, changes, expected_digest=base["league_digest"])
    second = edit_league(base, list(reversed(changes)),
                         expected_digest=base["league_digest"])
    assert first == second
    assert [x["field"] for x in first["edits"]] == ["action_cost", "victory_bonus"]


def test_existing_earned_attempts_are_immutable():
    scored = demo_league()
    with pytest.raises(SceneTravelError, match="after earned"):
        edit_league(scored, [{"field": "victory_bonus", "value": 400}],
                    expected_digest=scored["league_digest"])


def test_stale_expected_digest_fails_closed():
    base = _empty()
    with pytest.raises(SceneTravelError, match="stale"):
        edit_league(base, [{"field": "victory_bonus", "value": 250}],
                    expected_digest="0" * 64)


@pytest.mark.parametrize("changes", [
    [],
    [{"field": "victory_bonus", "value": 250}] * 17,
    [{"field": "victory_bonus", "value": True}],
    [{"field": "victory_bonus", "value": 5001}],
    [{"field": "victory_bonus", "value": 200}],
    [{"field": "rules_id", "value": 1}],
    [{"field": "victory_bonus", "value": 250},
     {"field": "victory_bonus", "value": 300}],
    [{"field": "victory_bonus", "value": 250, "grant": 100}],
])
def test_invalid_or_noop_edits_rejected(changes):
    base = _empty()
    with pytest.raises(SceneTravelError):
        edit_league(base, changes, expected_digest=base["league_digest"])


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(after_digest="0" * 64),
    lambda r: r.update(receipt_digest="0" * 64),
    lambda r: r["after"]["rules"].update(victory_bonus=5000),
    lambda r: r["edits"][0].update(value=5000),
    lambda r: r["before"].update(revision=True),
    lambda r: r.update(untrusted_reward=999),
])
def test_author_receipt_tampering_rejected(mutate):
    receipt = copy.deepcopy(demo_edit())
    mutate(receipt)
    with pytest.raises(SceneTravelError):
        verify_edit(receipt)


def test_bundle_tampering_rejected():
    bundle = export_edit(demo_edit())
    for change in (
        lambda b: b.update(checksum="0" * 64),
        lambda b: b.update(after_digest="0" * 64),
        lambda b: b["receipt"]["edits"][0].update(value=999),
    ):
        bad = copy.deepcopy(bundle)
        change(bad)
        with pytest.raises(SceneTravelError):
            import_edit(bad)


def test_preview_does_not_accept_unfinished_gameplay():
    with pytest.raises(SceneTravelError, match="finish"):
        preview_edit(demo_edit(), [])


def test_installed_cli_author_preview_export_and_failure(capsys):
    from skeleton.__main__ import main
    assert main(["scene-mission-league-author", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert cli(["preview", "--receipt-json", json.dumps(receipt),
                "--actions-json", json.dumps(demo_actions())]) == 0
    assert json.loads(capsys.readouterr().out)["playable_score"]["score"] > 0
    assert cli(["export", "--receipt-json", json.dumps(receipt)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert cli(["verify", "--receipt-json", '{"x":1,"x":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
