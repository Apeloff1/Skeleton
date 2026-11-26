"""Canonical source -> transactional editor -> combat -> save/replay/export acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.combat_campaign import (
    finish_campaign, normalize_campaign, original_campaign, verify_campaign,
)
from skeleton.game.gameplay.combat_campaign_author import (
    author_campaign, cli, original_authoring_demo, verify_authoring,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _source_digest(source):
    return dig(normalize_campaign(source))


def test_demo_round_trips_full_gameplay_save_and_export():
    source = original_campaign()
    receipt = original_authoring_demo()
    assert receipt["before_digest"] == _source_digest(source)
    assert receipt["after_digest"] == _source_digest(receipt["source"])
    assert receipt["preview_session"]["state"]["phase"] in {"won", "lost", "draw"}
    assert verify_campaign(receipt["preview_session"]) == receipt["preview_session"]
    assert receipt["preview_session"] == finish_campaign(receipt["source"])
    assert verify_authoring(source, json.loads(json.dumps(receipt))) == receipt


def test_caller_source_is_immutable_even_when_transaction_fails():
    source = original_campaign()
    pristine = copy.deepcopy(source)
    edits = [
        {"kind": "set-reward", "encounter_id": "reed_watch", "value": 11},
        {"kind": "set-foe-stat", "encounter_id": "tide_gate",
         "actor_id": "scout", "stat": "attack", "value": 9},
    ]
    with pytest.raises(CombatSessionError, match="hero"):
        author_campaign(source, edits, _source_digest(source))
    assert source == pristine


def test_stale_digest_rejected_before_edit():
    with pytest.raises(CombatSessionError, match="stale"):
        author_campaign(original_campaign(), [
            {"kind": "set-reward", "encounter_id": "reed_watch", "value": 12}
        ], "0" * 64)


@pytest.mark.parametrize("edit", [
    {"kind": "set-reward", "encounter_id": "reed_watch", "value": True},
    {"kind": "set-reward", "encounter_id": "reed_watch", "value": -1},
    {"kind": "set-reward", "encounter_id": "unknown", "value": 11},
    {"kind": "set-reward", "encounter_id": "reed_watch", "value": 10},
    {"kind": "set-turn-limit", "encounter_id": "reed_watch", "value": 100},
    {"kind": "set-foe-stat", "encounter_id": "reed_watch",
     "actor_id": "warden", "stat": "speed", "value": -1},
    {"kind": "set-foe-stat", "encounter_id": "reed_watch",
     "actor_id": "warden", "stat": "team", "value": 1},
    {"kind": "set-foe-stat", "encounter_id": "reed_watch",
     "actor_id": "missing", "stat": "attack", "value": 4},
    {"kind": "set-reward", "encounter_id": "reed_watch", "value": 12, "extra": 1},
])
def test_invalid_edits_fail_closed(edit):
    source = original_campaign()
    with pytest.raises(CombatSessionError):
        author_campaign(source, [edit], _source_digest(source))


def test_overflow_and_repeated_edits_fail_closed():
    source = original_campaign()
    with pytest.raises(CombatSessionError):
        author_campaign(source, [
            {"kind": "set-reward", "encounter_id": "reed_watch", "value": 1000000},
        ], _source_digest(source))
    with pytest.raises(CombatSessionError, match="no-op"):
        author_campaign(source, [
            {"kind": "set-reward", "encounter_id": "reed_watch", "value": 11},
            {"kind": "set-reward", "encounter_id": "reed_watch", "value": 11},
        ], _source_digest(source))


@pytest.mark.parametrize("mutate", [
    lambda x: x["source"]["encounters"][0].update(reward=999),
    lambda x: x["preview_session"]["state"].update(currency=999),
    lambda x: x.update(after_digest="0" * 64),
    lambda x: x["operations"][0].update(value=999),
    lambda x: x.update(receipt="0" * 64),
])
def test_tampered_receipt_rejected(mutate):
    source = original_campaign()
    receipt = copy.deepcopy(original_authoring_demo())
    mutate(receipt)
    with pytest.raises(CombatSessionError):
        verify_authoring(source, receipt)


def test_cli_demo_verify_and_invalid_json(capsys):
    source = original_campaign()
    assert cli(["demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--source-json", json.dumps(source),
                "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert cli(["edit", "--source-json", '{"bad":1,"bad":2}',
                "--operations-json", "[]", "--expected-digest", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_cli_edit_matches_authoring_and_is_replayable(capsys):
    source = original_campaign()
    edits = [{"kind": "set-turn-limit", "encounter_id": "reed_watch", "value": 17}]
    assert cli(["edit", "--source-json", json.dumps(source),
                "--operations-json", json.dumps(edits),
                "--expected-digest", _source_digest(source)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == author_campaign(source, edits, _source_digest(source))
    assert verify_authoring(source, receipt) == receipt
