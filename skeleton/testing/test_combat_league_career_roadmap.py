"""Deterministic coaching roadmap acceptance over real season replays."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_league_career import (
    advance_career, export_career, finish_career, import_career,
    new_career, original_career,
)
from skeleton.game.gameplay.combat_league_career_roadmap import (
    cli, plan_career, verify_career_roadmap,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_three_season_roadmap_replays_and_exports():
    source = original_career()
    start = new_career(source)
    untouched = copy.deepcopy(start)
    report = plan_career(start, "amber_guard", beam_width=2)
    assert report["status"] == "replayable_advice"
    assert report["seasons_remaining"] == 3
    assert len(report["choices"]) == 3
    assert report["expansions"] <= 64
    final = finish_career(source, report["choices"], resume=start)
    assert final["state_digest"] == report["terminal_state_digest"]
    assert import_career(report["portable_bundle"]) == final
    assert import_career(export_career(final)) == final
    assert verify_career_roadmap(start, report) == report
    assert start == untouched


def test_resume_career_roadmap_from_checkpoint():
    source = original_career()
    checkpoint = advance_career(new_career(source), {"kind": "rest"})
    report = plan_career(checkpoint, "amber_guard", beam_width=2)
    assert report["status"] == "replayable_advice"
    assert len(report["choices"]) == 2
    assert report["seasons_remaining"] == 2
    assert verify_career_roadmap(checkpoint, report) == report


def test_budget_exhaustion_never_fabricates_winner():
    start = new_career(original_career())
    report = plan_career(start, "amber_guard", max_expansions=1)
    assert report["status"] == "inconclusive"
    assert report["choices"] == []
    assert report["terminal_state_digest"] is None
    assert report["portable_bundle"] is None
    assert verify_career_roadmap(start, report) == report


def test_tamper_recomputed_receipt_rejected():
    start = new_career(original_career())
    report = plan_career(start, "amber_guard", beam_width=1)
    forged = copy.deepcopy(report)
    forged["predicted_champion"] = "forged"
    forged["receipt"] = dig({
        key: value for key, value in forged.items() if key != "receipt"
    })
    with pytest.raises(CombatSessionError, match="witness mismatch"):
        verify_career_roadmap(start, forged)


@pytest.mark.parametrize("beam,budget", [
    (0, 20), (9, 20), (True, 20), (2, 0),
    (2, 129), (2, True),
])
def test_bad_search_limits_rejected(beam, budget):
    start = new_career(original_career())
    with pytest.raises(CombatSessionError):
        plan_career(start, "amber_guard", beam_width=beam,
                    max_expansions=budget)


def test_forged_save_and_unknown_target_fail_closed():
    start = new_career(original_career())
    bad = copy.deepcopy(start)
    bad["state"]["tokens_remaining"] = 100
    with pytest.raises(CombatSessionError):
        plan_career(bad, "amber_guard")
    with pytest.raises(CombatSessionError, match="not authored"):
        plan_career(start, "ghost")


def test_cli_reachable_and_strict_json(capsys):
    from skeleton.__main__ import main
    assert main(["combat-career-roadmap", "demo", "--beam-width", "1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "replayable_advice"
    assert cli(["plan", "--session-json", '{"x":1,"x":2}',
                "--target-id", "amber_guard"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
