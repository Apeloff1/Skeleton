"""Market game vertical acceptance across canonical, editor, CLI and export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_market import original_market
from skeleton.game.gameplay.scene_market_acceptance import (
    audit_market, cli,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_market_acceptance_full_vertical():
    source, actions = original_market()
    result = audit_market(source, actions, include_editor=True)
    assert result["ok"] is True
    assert result["phase"] == "won"
    assert result["credits"] == 1
    assert result["delivered"] == ["sanctuary_seal"]
    assert result["reputation"] == 5
    assert result["tampered_bundle_rejected"] is True
    assert result["interactive_checkpoints"] >= 1
    assert len(result["portable_checksum"]) == 64
    assert len(result["editor_receipt_checksum"]) == 64
    assert result["qualification"] == "single_source_offline_gameplay_only"


def test_missing_delivery_cannot_pass_victory_acceptance():
    source, actions = original_market()
    missing = [a for a in actions if a.get("kind") != "deliver"]
    with pytest.raises(SceneTravelError, match="earned victory"):
        audit_market(source, missing)
    result = audit_market(source, missing, require_victory=False)
    assert result["phase"] == "lost"
    assert result["reputation"] == 0


def test_acceptance_rejects_forged_actions_without_modifying_source():
    source, actions = original_market()
    original = copy.deepcopy(source)
    bad = copy.deepcopy(actions)
    bad[5] = {"kind": "buy", "offer_id": "forged"}
    with pytest.raises(SceneTravelError):
        audit_market(source, bad)
    assert source == original


def test_acceptance_rejects_incorrect_option_types():
    source, actions = original_market()
    with pytest.raises(SceneTravelError, match="options"):
        audit_market(source, actions, require_victory=1)
    with pytest.raises(SceneTravelError, match="options"):
        audit_market(source, actions, include_editor="yes")


def test_main_cli_demo_and_audit(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-accept", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert report["phase"] == "won"
    source, actions = original_market()
    assert cli(["audit", "--source-json", json.dumps(source),
                "--actions-json", json.dumps(actions)]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "won"
    assert cli(["audit", "--source-json", '{"x":1,"x":2}',
                "--actions-json", "[]"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
