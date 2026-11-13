"""Focused authored episode contract: Moonlit Breakwater / Sentinel."""
from dataclasses import replace

import pytest

from skeleton.game.expedition_ledger import (
    ExpeditionError, evidence, load_episode, new_game,
    restore, run_episode, shortest_plan, snapshot, step,
)

CHAPTER = "moonlit_breakwater__sentinel"


def test_authored_moonlit_breakwater__sentinel_contract_and_shortest_win() -> None:
    ep = load_episode(CHAPTER)
    assert ep.quest["title"] == "Moonlit Breakwater: The Sentinel's Harbor Charter"
    assert ep.quest["faction"] == "Night Harbor Guild"
    assert ep.encounters["hazard"] == "undertow gate"
    assert len(ep.rows) == 9 and all(len(row) == 13 for row in ep.rows)
    assert ep.rows[1] == "#S.K.H.O.R.E#"
    plan = shortest_plan(ep)
    assert plan == ("east",) * 10
    finished = run_episode(ep, plan)
    assert finished.status == "won"
    assert finished.health == 9
    assert finished.objective and finished.has_key
    assert finished.events.count("environmental_hazard") == 1
    assert "expedition_completed" in finished.events


def test_authored_moonlit_breakwater__sentinel_resume_and_tamper_hold() -> None:
    ep = load_episode(CHAPTER)
    state = run_episode(ep, ["east", "east", "east"])
    receipt = snapshot(ep, state)
    assert restore(ep, receipt) == state
    receipt["state"]["reputation"] = 99
    with pytest.raises(ExpeditionError, match="save digest mismatch"):
        restore(ep, receipt)


def test_authored_moonlit_breakwater__sentinel_alternative_supply_route() -> None:
    ep = load_episode(CHAPTER)
    start = new_game(ep)
    branch = run_episode(ep, ["south", "east", "east", "east"])
    assert branch.status == "active"
    assert branch.energy >= start.energy - 4
    assert branch.turns == 4
    assert evidence(ep, branch)["integrity_only"] is True


def test_authored_moonlit_breakwater__sentinel_cannot_teleport_or_rebind() -> None:
    ep = load_episode(CHAPTER)
    with pytest.raises(ExpeditionError, match="unsupported movement"):
        step(ep, new_game(ep), "skip_to_exit")
    forged = replace(new_game(ep), x=11, y=1, objective=True)
    with pytest.raises(ExpeditionError, match="deterministic replay"):
        snapshot(ep, forged)
