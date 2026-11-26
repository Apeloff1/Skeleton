"""Bounded delivery routing must produce canonical replayable witnesses."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather_delivery import (
    new_deliveries, original_deliveries, resume_deliveries,
    verify_delivery_package,
)
from skeleton.game.gameplay.scene_weather_delivery_solver import (
    plan_deliveries, verify_delivery_route,
)


def test_shortest_original_delivery_route_is_replay_proven():
    source, _ = original_deliveries()
    report = plan_deliveries(source)
    assert report["status"] == "solved"
    assert report["complete"] is True
    assert len(report["actions"]) == 3
    assert report["terminal_package"]["manifest"]["earned"] == 30
    assert report["terminal_package"]["manifest"]["phase"] == "won"
    assert verify_delivery_package(report["terminal_package"]) == report["terminal_package"]
    assert verify_delivery_route(json.loads(json.dumps(report))) == report


def test_resumed_route_starts_at_verified_checkpoint():
    source, actions = original_deliveries()
    first = resume_deliveries(new_deliveries(source), actions[:1])
    report = plan_deliveries(session=first)
    assert report["status"] == "solved"
    assert len(report["actions"]) == 2
    assert report["start_state_digest"] == first["state_digest"]
    assert verify_delivery_route(report) == report


def test_depth_exhaustion_is_inconclusive_not_false_unreachable():
    source, _ = original_deliveries()
    report = plan_deliveries(source, max_depth=0)
    assert report["status"] == "inconclusive"
    assert report["complete"] is False
    assert report["terminal_package"] is None


def test_insufficient_state_budget_is_inconclusive():
    source, _ = original_deliveries()
    report = plan_deliveries(source, max_states=1)
    assert report["status"] == "inconclusive"
    assert report["complete"] is False


@pytest.mark.parametrize("bounds", [
    {"max_states": True}, {"max_states": 0}, {"max_states": 257},
    {"max_depth": -1}, {"max_depth": 33},
])
def test_invalid_search_budgets_fail_closed(bounds):
    source, _ = original_deliveries()
    with pytest.raises(SceneTravelError):
        plan_deliveries(source, **bounds)


def test_source_and_session_are_mutually_exclusive():
    source, _ = original_deliveries()
    with pytest.raises(SceneTravelError):
        plan_deliveries()
    with pytest.raises(SceneTravelError):
        plan_deliveries(source, session=new_deliveries(source))


@pytest.mark.parametrize("edit", [
    lambda r: r.update(status="solved"),
    lambda r: r.update(explored=999),
    lambda r: r["actions"].append({"kind": "wait"}),
    lambda r: r["terminal_package"]["manifest"].update(earned=999),
    lambda r: r.update(receipt="0" * 64),
    lambda r: r["start_session"]["state"].update(earned=999),
])
def test_tampered_witness_and_report_fail_closed(edit):
    source, _ = original_deliveries()
    report = plan_deliveries(source)
    changed = copy.deepcopy(report)
    edit(changed)
    with pytest.raises(SceneTravelError):
        verify_delivery_route(changed)


def test_cli_demo_and_report_verification(capsys):
    assert main(["weather-deliveries-plan", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "solved"
    assert main(["weather-deliveries-plan", "verify",
                 "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report


def test_cli_rejects_malformed_duplicate_json(capsys):
    assert main(["weather-deliveries-plan", "solve",
                 "--source-json", '{"a":1,"a":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
