"""Real cooperative play, interactive restart, source and export acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_market_party import original_party
from skeleton.game.gameplay.scene_market_party_acceptance import (
    accept_party_delivery, cli,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.mark.parametrize("split", [0, 1, 3, 6, 9])
def test_end_to_end_cooperative_play_and_restart(split):
    source, turns = original_party()
    cut = min(split, len(turns) - 1)
    result = accept_party_delivery(source, turns, split=cut)
    assert result["phase"] == "won"
    assert result["turn_count"] == len(turns)
    assert result["interactive_accepted"] == len(turns) - cut
    assert result["checkpoint_count"] >= 1
    assert result["portable_final_checksum"]
    assert result["route_checksum"]
    assert result == accept_party_delivery(
        json.loads(json.dumps(source)), json.loads(json.dumps(turns)), split=cut)


def test_source_and_turn_input_are_not_mutated():
    source, turns = original_party()
    before = copy.deepcopy((source, turns))
    accept_party_delivery(source, turns)
    assert (source, turns) == before


def test_incomplete_campaign_never_receives_acceptance():
    source, turns = original_party()
    with pytest.raises(SceneTravelError):
        accept_party_delivery(source, turns[:2])


def test_wrong_actor_fails_closed():
    source, turns = original_party()
    bad = copy.deepcopy(turns)
    bad[0]["player_id"] = "intruder"
    with pytest.raises(SceneTravelError):
        accept_party_delivery(source, bad)


@pytest.mark.parametrize("split", [-1, True, 100000])
def test_invalid_restart_boundary_rejected(split):
    source, turns = original_party()
    with pytest.raises(SceneTravelError):
        accept_party_delivery(source, turns, split=split)


def test_main_cli_is_reachable_and_rejects_duplicate_keys(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-accept", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["phase"] == "won"
    assert report["checksum"]
    assert cli(["accept", "--source-json", '{"x":1,"x":2}',
                "--turns-json", "[]"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
