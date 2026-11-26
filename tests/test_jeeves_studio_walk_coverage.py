"""Jeeves typed tool and CLI share source-verified choice coverage authority."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.ai.agents.jeeves import studio_walk_tool as tool
from skeleton.ai.agents.jeeves.jeeves_game_orchestrator import JeevesGameOrchestrator
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import start_walk
from skeleton.ai.game_builder.studio_ecosystem_walk_coverage import (
    audit_walk_choice_coverage,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def request(**updates):
    body = {
        "schema": tool.REQUEST_SCHEMA, "project_id": PROJECT,
        "operation": "coverage", "events": [],
    }
    body.update(updates)
    return body


def test_jeeves_choice_coverage_matches_canonical_walk_authority():
    source = read_blueprint(PROJECT)
    initial = start_walk(source, authorized=True)
    expected = audit_walk_choice_coverage(initial, source, authorized=True)
    orchestrator = JeevesGameOrchestrator()
    result = orchestrator.authoritative_walk(request(), authorized=True)
    assert result["detail"] == expected
    assert result["receipt"] == initial.receipt()
    assert result["replay_verified"] is True
    assert result["release_certified"] is False
    assert result == orchestrator.authoritative_walk(request(), authorized=True)


def test_jeeves_choice_coverage_forged_save_is_rejected():
    result = tool.execute_walk_tool(request(), authorized=True)
    tampered = deepcopy(result["receipt"])
    tampered["session_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        tool.execute_walk_tool(request(receipt=tampered), authorized=True)


def test_jeeves_choice_coverage_cannot_grant_its_own_authority(monkeypatch):
    monkeypatch.setattr(tool, "read_blueprint",
                        lambda _: pytest.fail("unauthorized catalog read"))
    with pytest.raises(PermissionError):
        tool.execute_walk_tool(request(), authorized=False)


def test_jeeves_choice_coverage_descriptor_is_typed():
    schema = tool.tool_schema()
    assert "coverage" in schema["parameters"]["properties"]["operation"]["enum"]
    assert schema["parameters"]["additionalProperties"] is False
    assert "authorized" not in schema["parameters"]["properties"]
