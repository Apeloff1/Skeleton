"""Whole vertical source-to-runtime-to-export acceptance and tamper regression."""
from __future__ import annotations

import json

import pytest

from skeleton.game.gameplay.scene_market_contract import original_contract
from skeleton.game.gameplay.scene_market_contract_acceptance import (
    accept_contract, cli,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_complete_offline_commission_acceptance():
    source, actions = original_contract()
    report = accept_contract(source, actions)
    assert report["ok"] is True
    assert report["phase"] == "won"
    assert report["score"] == 25
    assert report["credits"] == 1
    assert report["goods"] == {}
    assert report["reputation"] == 5
    assert report["tampered_score_rejected"] is True
    assert report["terminal_checkpoint_count"] >= 1
    assert report["author_receipt_checksum"] is not None
    assert report["qualification"] == "single_source_offline_gameplay_only"


def test_incomplete_mission_is_not_certified_as_win():
    source, actions = original_contract()
    incomplete = [a for a in actions if a.get("kind") != "deliver"]
    with pytest.raises(SceneTravelError, match="victory"):
        accept_contract(source, incomplete)


def test_acceptance_cli_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-contract-accept", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["phase"] == "won"
    assert cli(["audit", "--source-json", '{"x":1,"x":2}',
                "--actions-json", "[]"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
