"""Route planning: actual weather, earned payouts, replay, uncertainty."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather_market import (
    new_market, original_market, resume_market, verify_market_package,
)
from skeleton.game.gameplay.scene_weather_market_planner import (
    plan_market, verify_market_route,
)


def test_original_market_has_replayable_profitable_route():
    source, actions = original_market()
    baseline = resume_market(new_market(source), actions)
    result = plan_market(source, max_states=128, max_depth=16)
    assert result["status"] in ("feasible_unproven", "optimal_within_bounds")
    assert result["terminal_package"] is not None
    terminal = verify_market_package(result["terminal_package"])["snapshot"]
    assert terminal["state"]["phase"] == "won"
    assert terminal["state"]["net"] >= baseline["state"]["net"]
    assert resume_market(result["start_session"], result["actions"]) == terminal
    assert verify_market_route(json.loads(json.dumps(result))) == result


def test_starting_from_verified_terminal_requires_no_actions():
    source, actions = original_market()
    terminal = resume_market(new_market(source), actions)
    report = plan_market(session=terminal)
    assert report["status"] == "optimal_within_bounds"
    assert report["complete"] is True
    assert report["actions"] == []
    assert report["terminal_package"]["snapshot"] == terminal


def test_tight_search_budget_reports_inconclusive_not_false_victory():
    source, _ = original_market()
    report = plan_market(source, max_states=1, max_depth=0)
    assert report["status"] == "inconclusive"
    assert report["complete"] is False
    assert report["terminal_package"] is None
    assert report["actions"] == []
    assert verify_market_route(report) == report


def test_tampered_witness_and_payout_fail_closed():
    source, _ = original_market()
    report = plan_market(source)
    tampered = copy.deepcopy(report)
    tampered["actions"] = [{"kind": "wait"}]
    tampered["receipt"] = dig({k: v for k, v in tampered.items() if k != "receipt"})
    with pytest.raises(SceneTravelError):
        verify_market_route(tampered)
    tampered = copy.deepcopy(report)
    tampered["terminal_package"]["manifest"]["net"] = 99999
    with pytest.raises(SceneTravelError):
        verify_market_route(tampered)


@pytest.mark.parametrize("kwargs", [
    {"max_states": 0}, {"max_states": 129},
    {"max_depth": -1}, {"max_depth": 17},
    {"max_depth": True}, {"max_states": False},
])
def test_invalid_search_budgets_fail_closed(kwargs):
    source, _ = original_market()
    with pytest.raises(SceneTravelError):
        plan_market(source, **kwargs)


def test_invalid_source_session_selector_rejected():
    source, _ = original_market()
    with pytest.raises(SceneTravelError):
        plan_market()
    with pytest.raises(SceneTravelError):
        plan_market(source, session=new_market(source))


def _run(capsys, *args):
    status = main(list(args))
    output = capsys.readouterr()
    return status, json.loads(output.out or output.err)


def test_main_cli_market_planner_and_proof_verification(capsys):
    source, _ = original_market()
    status, route = _run(capsys, "weather-market-plan", "solve",
                         "--source-json", json.dumps(source))
    assert status == 0 and route["terminal_package"] is not None
    status, checked = _run(capsys, "weather-market-plan", "verify",
                           "--report-json", json.dumps(route))
    assert status == 0 and checked == route


def test_cli_bad_input_fails_without_fake_plan(capsys):
    status, error = _run(capsys, "weather-market-plan", "solve",
                         "--source-json", '{"bad":true}')
    assert status == 2 and error["ok"] is False
