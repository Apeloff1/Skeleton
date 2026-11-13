"""Replay-verified cooperative role contribution and starvation audit."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_party import original_party, simulate_party
from skeleton.game.gameplay.scene_market_party_balance import (
    accept_balance, analyze_party_balance, cli, verify_party_balance,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def played():
    source, turns = original_party()
    return simulate_party(source, turns)


def test_balance_derived_from_real_replay(played):
    report = analyze_party_balance(played)
    assert report["phase"] == "won"
    assert report["turns"] == len(played["journal"])
    assert sum(p["total_turns"] for p in report["players"]) == report["turns"]
    assert sum(report["role_totals"].values()) == sum(
        p["productive_turns"] for p in report["players"])
    assert report["checksum"] == dig({k: v for k, v in report.items()
                                     if k != "checksum"})
    assert verify_party_balance(played, json.loads(json.dumps(report))) == report


@pytest.mark.parametrize("field", ["turns", "role_totals", "players", "phase"])
def test_forged_report_fails_even_with_recomputed_checksum(played, field):
    report = analyze_party_balance(played)
    forged = copy.deepcopy(report)
    if field == "turns":
        forged[field] += 1
    elif field == "role_totals":
        forged[field]["artisan"] += 1
    elif field == "players":
        forged[field][0]["productive_turns"] += 1
    else:
        forged[field] = "active"
    forged["checksum"] = dig({k: v for k, v in forged.items()
                              if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_party_balance(played, forged)


def test_unearned_credits_and_journal_tampering_fail_closed(played):
    forged = copy.deepcopy(played)
    forged["state"]["market"]["state"]["credits"] += 1000
    with pytest.raises(SceneTravelError):
        analyze_party_balance(forged)
    forged = copy.deepcopy(played)
    forged["journal"][0]["turn"]["action"]["kind"] = "pass"
    with pytest.raises(SceneTravelError):
        analyze_party_balance(forged)


def test_cli_main_dispatch_and_error(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-balance", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["phase"] == "won"
    assert cli(["inspect", "--session-json", "{}"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
