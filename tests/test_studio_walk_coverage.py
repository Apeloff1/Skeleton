"""Source-backed authored choice coverage and CLI regression contracts."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import (
    start_walk, walk_action, walk_route_hint,
)
from skeleton.ai.game_builder import studio_ecosystem_walk_coverage as coverage

PROJECT = "studio_arena_fighting_glacial_fjord"


@pytest.fixture(scope="module")
def documents():
    return read_blueprint(PROJECT)


def test_source_backed_choices_are_executable_and_deterministic(documents):
    initial = start_walk(documents, authorized=True)
    unchanged = initial.receipt()
    result = coverage.audit_walk_choice_coverage(
        initial, documents, authorized=True,
    )
    assert result == coverage.audit_walk_choice_coverage(
        initial, documents, authorized=True,
    )
    assert initial.receipt() == unchanged
    assert result["project_id"] == PROJECT
    assert result["alternatives_verified"] > 0
    assert result["alternatives_unverified"] >= 0
    assert result["all_branch_combinations_verified"] is False
    assert result["release_certified"] is False
    assert result["coverage_digest"] and len(result["coverage_digest"]) == 64
    assert result["alternatives_verified"] == len(result["choices"])
    assert result["replay_work_events"] <= coverage.MAX_COVERAGE_REPLAY_EVENTS
    assert all(row["route_distance"] >= 0 and row["after_choice_digest"]
               for row in result["choices"])


def test_real_route_then_choice_matches_audited_successor(documents):
    initial = start_walk(documents, authorized=True)
    result = coverage.audit_walk_choice_coverage(
        initial, documents, authorized=True,
    )
    first = result["choices"][0]
    hint = walk_route_hint(initial, documents, authorized=True)
    assert first["route_digest"] == hint["route_digest"]
    approached = initial
    for move in hint["moves"]:
        approached = walk_action(
            approached, documents, action="move", value=move, authorized=True,
        )
    successor = walk_action(
        approached, documents, action="choose",
        value=first["alternative"], authorized=True,
    )
    assert successor.digest == first["after_choice_digest"]


def test_unauthorized_rejected_before_source_read(documents, monkeypatch):
    initial = start_walk(documents, authorized=True)
    monkeypatch.setattr(coverage, "playable_world_source",
                        lambda _: pytest.fail("unauthorized source read"))
    with pytest.raises(PermissionError):
        coverage.audit_walk_choice_coverage(
            initial, documents, authorized=False,
        )


def test_forged_session_fails_closed(documents):
    initial = start_walk(documents, authorized=True)
    with pytest.raises(StudioQuestError):
        coverage.audit_walk_choice_coverage(
            replace(initial, digest="0" * 64), documents, authorized=True,
        )


def test_replay_budget_reports_partial_without_fake_coverage(documents, monkeypatch):
    initial = start_walk(documents, authorized=True)
    monkeypatch.setattr(coverage, "MAX_COVERAGE_REPLAY_EVENTS", 1)
    result = coverage.audit_walk_choice_coverage(
        initial, documents, authorized=True,
    )
    assert result["stop_reason"] == "replay_budget_exhausted"
    assert result["alternatives_verified"] == 0
    assert result["complete_reference_path_coverage"] is False
    assert result["alternatives_unverified"] == result["alternatives_expected_from_input"]


def test_stage_budget_reports_omissions(documents, monkeypatch):
    initial = start_walk(documents, authorized=True)
    monkeypatch.setattr(coverage, "MAX_COVERAGE_STAGES", 0)
    result = coverage.audit_walk_choice_coverage(
        initial, documents, authorized=True,
    )
    assert result["stop_reason"] == "stage_budget_exhausted"
    assert result["stages_audited"] == 0
    assert not result["complete_reference_path_coverage"]


def test_cli_choice_coverage_and_mode_exclusion(documents, monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: documents)
    assert cli.main([
        "--project", PROJECT, "--play-walk", "--walk-audit-choices",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["choice_coverage"]["project_id"] == PROJECT
    assert payload["receipt"]["session_digest"] == payload[
        "choice_coverage"]["input_session_digest"]
    with pytest.raises(SystemExit) as error:
        cli.main([
            "--project", PROJECT, "--play-walk",
            "--walk-audit-choices", "--walk-route",
        ])
    assert error.value.code == 2
