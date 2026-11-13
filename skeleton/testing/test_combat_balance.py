"""End-to-end deterministic, source-bound offline combat balance tests."""
from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, original_demo, new_session, resume_session,
)
from skeleton.game.gameplay.combat_balance import (
    SCHEMA, analyze, verify_report,
)


def test_original_encounter_has_replayable_victory() -> None:
    scenario, _ = original_demo()
    report = analyze(scenario, "wayfarers")
    assert report["schema_version"] == SCHEMA
    assert report["status"] == "victory_witness"
    assert report["source_digest"] == new_session(scenario)["source_digest"]
    assert report["witness_actions"]
    replay = resume_session(new_session(scenario), report["witness_actions"])
    assert replay["state"]["winner"] == "wayfarers"
    assert replay["state_digest"] == report["witness_state_digest"]
    assert verify_report(json.loads(json.dumps(report))) == report


def test_repeatable_across_source_actor_order() -> None:
    scenario, _ = original_demo()
    alternate = copy.deepcopy(scenario)
    alternate["actors"].reverse()
    a = analyze(scenario, "wayfarers")
    b = analyze(alternate, "wayfarers")
    assert a == b


def test_exhaustive_no_witness_is_not_a_budget_timeout() -> None:
    scenario, _ = original_demo()
    scenario["turn_limit"] = 1
    result = analyze(scenario, "wayfarers", max_states=128, max_turns=16)
    assert result["status"] == "exhaustive_no_witness"
    assert result["witness_actions"] is None
    assert verify_report(result) == result


def test_state_budget_is_conservatively_inconclusive() -> None:
    scenario, _ = original_demo()
    result = analyze(scenario, "wayfarers", max_states=1)
    assert result["status"] == "inconclusive_budget"
    assert result["witness_state_digest"] is None
    assert verify_report(result) == result


def test_turn_budget_is_conservatively_inconclusive() -> None:
    scenario, _ = original_demo()
    result = analyze(scenario, "wayfarers", max_turns=1)
    assert result["status"] == "inconclusive_budget"
    assert verify_report(result) == result


@pytest.mark.parametrize("team", ["unknown", "", "wayfarers\n"])
def test_unknown_or_malformed_team_denied(team: str) -> None:
    scenario, _ = original_demo()
    with pytest.raises(CombatSessionError, match="team"):
        analyze(scenario, team)


@pytest.mark.parametrize("budget", [0, -1, 4097, True, 1.5, "20"])
def test_invalid_state_budget_denied(budget: object) -> None:
    scenario, _ = original_demo()
    with pytest.raises(CombatSessionError, match="max_states"):
        analyze(scenario, "wayfarers", max_states=budget)


@pytest.mark.parametrize("budget", [0, 33, True, 1.5, "16"])
def test_invalid_turn_budget_denied(budget: object) -> None:
    scenario, _ = original_demo()
    with pytest.raises(CombatSessionError, match="max_turns"):
        analyze(scenario, "wayfarers", max_turns=budget)


@pytest.mark.parametrize("key,value", [
    ("status", "victory_witness"),
    ("team", "reedbound"),
    ("opponent_policy", "legacy"),
    ("checksum", "0" * 64),
    ("explored_states", 0),
    ("witness_actions", []),
])
def test_forged_reports_fail_closed(key: str, value: object) -> None:
    scenario, _ = original_demo()
    report = analyze(scenario, "wayfarers", max_states=1)
    report[key] = value
    with pytest.raises(CombatSessionError):
        verify_report(report)


def test_extra_fields_are_not_accepted() -> None:
    scenario, _ = original_demo()
    report = analyze(scenario, "wayfarers")
    report["pretend_verified"] = True
    with pytest.raises(CombatSessionError, match="fields"):
        verify_report(report)


def test_cli_demo_and_replay_verify() -> None:
    demo = subprocess.run(
        [sys.executable, "-m", "skeleton", "combat-balance", "demo"],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert demo.returncode == 0, demo.stderr
    report = json.loads(demo.stdout)
    verified = subprocess.run(
        [sys.executable, "-m", "skeleton", "combat-balance", "verify",
         "--report-json", json.dumps(report)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout) == report


def test_cli_rejects_bad_input_without_traceback() -> None:
    run = subprocess.run(
        [sys.executable, "-m", "skeleton", "combat-balance", "analyze",
         "--scenario-json", '{"broken":true}', "--team", "wayfarers"],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert run.returncode == 2
    assert json.loads(run.stderr)["ok"] is False
    assert "Traceback" not in run.stderr
