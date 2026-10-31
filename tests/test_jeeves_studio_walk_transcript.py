"""Jeeves typed transcript is the canonical source-backed walk transcript."""
from __future__ import annotations

import pytest

from skeleton.ai.agents.jeeves import studio_walk_tool as tool
from skeleton.ai.agents.jeeves.jeeves_game_orchestrator import JeevesGameOrchestrator
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

PROJECT = "studio_arena_fighting_glacial_fjord"


def request(**kwargs):
    payload = {"schema": tool.REQUEST_SCHEMA, "project_id": PROJECT,
               "operation": "transcript", "events": []}
    payload.update(kwargs)
    return payload


def test_jeeves_transcript_matches_canonical_source_and_is_stable():
    orchestrator = JeevesGameOrchestrator()
    a = orchestrator.authoritative_walk(request(), authorized=True)
    b = orchestrator.authoritative_walk(request(), authorized=True)
    assert a == b
    assert a["detail"]["schema"] == "skeleton.game_builder.studio_walk_story_transcript.v1"
    assert a["detail"]["session_digest"] == a["receipt"]["session_digest"]
    assert a["detail"]["completed_scene_count"] == 0
    assert a["replay_verified"] is True
    assert a["release_certified"] is False


def test_jeeves_transcript_rejects_bad_authority_and_cross_operation_options():
    orchestrator = JeevesGameOrchestrator()
    with pytest.raises(PermissionError):
        orchestrator.authoritative_walk(request(), authorized=False)
    with pytest.raises(StudioQuestError):
        orchestrator.authoritative_walk(request(transcript_offset=True), authorized=True)
    with pytest.raises(StudioQuestError):
        orchestrator.authoritative_walk(request(transcript_limit=33), authorized=True)
    with pytest.raises(StudioQuestError):
        orchestrator.authoritative_walk(request(transcript_offset=1), authorized=True)
    with pytest.raises(StudioQuestError):
        orchestrator.authoritative_walk(request(transcript_expected_digest="0"*64), authorized=True)
    with pytest.raises(StudioQuestError):
        orchestrator.authoritative_walk(request(operation="route", transcript_limit=2), authorized=True)
    with pytest.raises(StudioQuestError):
        orchestrator.authoritative_walk(request(is_admin=True), authorized=True)


def test_jeeves_transcript_schema_has_bounded_paging_fields():
    schema = tool.tool_schema()["parameters"]
    assert "transcript" in schema["properties"]["operation"]["enum"]
    assert schema["properties"]["transcript_limit"]["maximum"] == 32
    assert schema["additionalProperties"] is False
