"""Route acceptance composes source, gameplay, save, editor and export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    new_market, original_market, simulate_market,
)
from skeleton.game.gameplay.scene_market_route_acceptance import (
    accept_market_route, cli, verify_market_route_acceptance,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_route_acceptance_reaches_playable_exported_victory():
    source, _ = original_market()
    session = new_market(source)
    report = accept_market_route(session)
    assert report["status"] == "accepted_offline_witness"
    assert report["actions_from_checkpoint"] > 0
    assert report["remaining_goods"] == {}
    assert report["remaining_credits"] == 1
    assert report["delivered"] == ["sanctuary_seal"]
    assert report["reputation"] == 5
    assert report["total_replayed_actions"] == report["actions_from_checkpoint"]
    assert report["qualification"] == "one_exact_offline_source_not_device_release"
    assert verify_market_route_acceptance(session, report) == report


def test_acceptance_from_saved_partial_game_reconciles_append_only():
    source, actions = original_market()
    checkpoint = simulate_market(source, actions[:5])
    before = copy.deepcopy(checkpoint)
    report = accept_market_route(checkpoint, include_editor=False)
    assert report["status"] == "accepted_offline_witness"
    assert report["total_replayed_actions"] == 5 + report["actions_from_checkpoint"]
    assert report["terminal_state_digest"] != report["initial_state_digest"]
    assert checkpoint == before


def test_inconclusive_is_not_falsely_accepted():
    source, _ = original_market()
    session = new_market(source)
    with pytest.raises(SceneTravelError, match="not proven"):
        accept_market_route(session, max_depth=0)
    report = accept_market_route(
        session, max_depth=0, require_victory=False,
    )
    assert report["status"] == "inconclusive"
    assert report["qualification"] == "no_playable_victory_witness"
    assert verify_market_route_acceptance(session, report) == report


def test_forged_rechecksummed_evidence_rejected():
    source, _ = original_market()
    session = new_market(source)
    report = accept_market_route(session, include_editor=False)
    forged = copy.deepcopy(report)
    forged["remaining_credits"] = 999
    forged["checksum"] = dig({
        k: v for k, v in forged.items() if k != "checksum"
    })
    with pytest.raises(SceneTravelError, match="evidence mismatch"):
        verify_market_route_acceptance(session, forged)


@pytest.mark.parametrize("change", [
    lambda s: s["state"].update(credits=100),
    lambda s: s["save"].update(tick=100),
    lambda s: s.update(source_digest="0" * 64),
])
def test_forged_market_checkpoints_fail_closed(change):
    source, _ = original_market()
    bad = new_market(source)
    change(bad)
    with pytest.raises(SceneTravelError):
        accept_market_route(bad)


def test_cli_route_acceptance_is_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-route-accept", "demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "accepted_offline_witness"
    assert cli(["audit", "--session-json", '{"invalid":true}']) == 2
    assert "error" in json.loads(capsys.readouterr().err)
