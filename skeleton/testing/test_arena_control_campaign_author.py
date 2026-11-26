"""Transactional campaign editing, nested control previews and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.arena_control import original_actions
from skeleton.game.gameplay.arena_control_campaign import (
    normalize_campaign, original_campaign, verify_campaign,
)
from skeleton.game.gameplay.arena_control_campaign_author import (
    author_campaign, original_authoring_demo, verify_authoring,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_transaction_changes_earned_rewards_and_replays():
    source = original_campaign()
    before = copy.deepcopy(source)
    result = original_authoring_demo()
    assert source == before
    assert result["preview"]["state"]["phase"] == "won"
    assert result["preview"]["state"]["currency"] == 32
    assert result["source"]["required_wins"] == 1
    assert verify_campaign(result["preview"]) == result["preview"]
    assert verify_authoring(source, json.loads(json.dumps(result))) == result


def test_nested_control_edit_compiles_actual_playable_stage():
    source = original_campaign()
    edit = [{
        "kind": "edit-stage-control",
        "control_id": "lantern_canal_control",
        "operations": [{"kind": "set-score-target", "value": 1}],
        "preview_actions": original_actions()[:1],
    }]
    receipt = author_campaign(
        source, edit, dig(normalize_campaign(source)),
        [original_actions()[:1], original_actions()],
    )
    assert receipt["source"]["stages"][0]["control"]["score_target"] == 1
    assert len(receipt["child_receipts"]) == 1
    assert receipt["preview"]["state"]["wins"] == 2
    assert receipt["preview"]["state"]["currency"] == 30
    assert verify_authoring(source, receipt) == receipt


@pytest.mark.parametrize("operations,error", [
    ([{"kind": "set-required-wins", "value": 2}], "no-op"),
    ([{"kind": "set-stage-reward", "control_id": "unknown", "value": 1}], "unknown"),
    ([{"kind": "set-stage-reward", "control_id": "lantern_canal_control", "value": -1}], "reward"),
    ([{"kind": "set-required-wins", "value": 3}], "required_wins"),
    ([{"kind": "unknown"}], "unsupported"),
    ([{"kind": "set-required-wins", "value": 1, "extra": 2}], "fields"),
])
def test_invalid_edits_fail_atomically(operations, error):
    source = original_campaign()
    before = copy.deepcopy(source)
    with pytest.raises(CombatSessionError, match=error):
        author_campaign(source, operations, dig(normalize_campaign(source)),
                        [original_actions(), original_actions()])
    assert source == before


def test_stale_source_and_incomplete_preview_fail_closed():
    source = original_campaign()
    edits = [{"kind": "set-required-wins", "value": 1}]
    with pytest.raises(CombatSessionError, match="stale"):
        author_campaign(source, edits, "0" * 64,
                        [original_actions(), original_actions()])
    with pytest.raises(CombatSessionError):
        author_campaign(source, edits, dig(normalize_campaign(source)),
                        [original_actions()[:1], original_actions()])


def test_tampered_nested_and_parent_receipts_rejected():
    source = original_campaign()
    edit = [{
        "kind": "edit-stage-control",
        "control_id": "lantern_canal_control",
        "operations": [{"kind": "set-score-target", "value": 1}],
        "preview_actions": original_actions()[:1],
    }]
    result = author_campaign(
        source, edit, dig(normalize_campaign(source)),
        [original_actions()[:1], original_actions()],
    )
    bad = copy.deepcopy(result)
    bad["child_receipts"][0]["preview"]["state"]["scores"]["wayfarers"] = 999
    with pytest.raises(CombatSessionError):
        verify_authoring(source, bad)
    bad = copy.deepcopy(result)
    bad["preview"]["state"]["currency"] = 999
    with pytest.raises(CombatSessionError):
        verify_authoring(source, bad)
    bad = copy.deepcopy(result)
    bad["operations"][0]["operations"][0]["value"] = 2
    with pytest.raises(CombatSessionError):
        verify_authoring(source, bad)


def test_installed_cli_edit_preview_verify_and_source_identity(capsys):
    assert main(["arena-control-campaign-author", "demo"]) == 0
    edited = json.loads(capsys.readouterr().out)
    assert edited["schema_version"] == "skeleton.arena_control_campaign_author.v1"
    assert main([
        "arena-control-campaign-author", "verify",
        "--source-json", json.dumps(original_campaign()),
        "--receipt-json", json.dumps(edited),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == edited
    assert main([
        "arena-control-campaign", "play",
        "--source-json", json.dumps(edited["source"]),
        "--rounds-json", json.dumps(edited["preview_rounds"]),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == edited["preview"]
