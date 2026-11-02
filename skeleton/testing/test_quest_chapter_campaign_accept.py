"""Campaign editor, earned gameplay, checkpoint and portable acceptance."""
import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.quest_chapter_campaign import (
    demo_campaign_actions, original_campaign,
)
from skeleton.game.gameplay.quest_chapter_campaign_accept import (
    SCHEMA, accept_campaign, cli, verify_acceptance,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_campaign_acceptance_replays_all_chapters():
    source = original_campaign()
    actions = demo_campaign_actions()
    before = copy.deepcopy(source)
    report = accept_campaign(source, actions)
    assert source == before
    assert report["schema_version"] == SCHEMA
    assert report["phase"] == "won"
    assert report["plan"]["status"] == "found"
    assert report["terminal"]["state"]["phase"] == "won"
    assert len(report["terminal"]["state"]["history"]) == 2
    assert report["bundle"]["session"] == report["terminal"]
    assert report["checkpoint"]["state"]["tick"] < report["terminal"]["state"]["tick"]
    assert verify_acceptance(json.loads(json.dumps(report))) == report


def test_editor_change_preserves_earned_victory_and_source_identity():
    source = original_campaign()
    before = copy.deepcopy(source)
    edits = [{"op": "set_granted_flags", "id": "night_watch",
              "value": ["harbor_secured", "night_shift"]}]
    report = accept_campaign(source, demo_campaign_actions(), operations=edits)
    assert source == before
    assert report["edit_receipt"] is not None
    assert report["source_digest"] == report["edit_receipt"]["source_digest"]
    assert report["terminal"]["state"]["flags"] == [
        "beacon_raised", "harbor_secured", "night_shift",
    ]
    assert verify_acceptance(report) == report


@pytest.mark.parametrize("field,value", [
    ("max_states", 1),
    ("max_depth", 1),
])
def test_insufficient_route_budget_does_not_certify(field, value):
    kwargs = {field: value, "split_at": 0}
    with pytest.raises(CombatSessionError, match="planner returned"):
        accept_campaign(original_campaign(), demo_campaign_actions(), **kwargs)


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(receipt="0" * 64),
    lambda r: r["plan"].update(checksum="0" * 64),
    lambda r: r["checkpoint"]["state"].update(phase="lost"),
    lambda r: r["terminal"]["state"].update(phase="blocked"),
    lambda r: r["bundle"].update(checksum="0" * 64),
    lambda r: r.update(source_digest="0" * 64),
    lambda r: r["actions"][0].update(kind="advance"),
    lambda r: r.update(split_at=0),
])
def test_forged_acceptance_is_rejected(mutate):
    report = accept_campaign(original_campaign(), demo_campaign_actions())
    bad = copy.deepcopy(report)
    mutate(bad)
    assert bad != report
    with pytest.raises(CombatSessionError):
        verify_acceptance(bad)


def test_bad_checkpoint_boundary_and_source_edit_fail_closed():
    source, actions = original_campaign(), demo_campaign_actions()
    with pytest.raises(CombatSessionError):
        accept_campaign(source, actions, split_at=len(actions))
    with pytest.raises(CombatSessionError):
        accept_campaign(source, actions, split_at=True)
    with pytest.raises(CombatSessionError):
        accept_campaign(source, actions, operations=[{
            "op": "set_required_ending", "id": "missing", "value": "beacon_lit",
        }])
    with pytest.raises(CombatSessionError):
        verify_acceptance({"schema_version": SCHEMA})


def test_cli_demo_verify_dispatch_and_errors(capsys):
    assert cli(["demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["phase"] == "won"
    assert cli(["verify", "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert main(["quest-campaign-accept", "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "won"
    assert cli(["check", "--source-json", "{}", "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
