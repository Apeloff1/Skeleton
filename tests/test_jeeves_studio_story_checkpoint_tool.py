"""Jeeves browser checkpoint preview and comparison are typed and fail closed."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from skeleton.ai.agents.jeeves.jeeves_game_orchestrator import JeevesGameOrchestrator
from skeleton.ai.agents.jeeves.studio_story_checkpoint_tool import (
    REQUEST_SCHEMA, execute_story_checkpoint_tool, tool_schema,
)
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_story_html import story_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

PROJECT = "studio_arena_fighting_glacial_fjord"


def _checkpoint(source, actions):
    return json.dumps({
        "schema": "skeleton.game_builder.offline_story_choices.v1",
        "project_id": source["project_id"], "source_digest": source["source_digest"],
        "choices": actions, "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }, sort_keys=True)


def _request(operation="preview"):
    source = story_source(read_blueprint(PROJECT))
    stage = source["stages"][0]
    return {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_quest_source_digest": source["source_digest"],
        "operation": operation,
        "current_checkpoint": _checkpoint(source, []),
        "candidate_checkpoint": (
            _checkpoint(source, [[stage["id"], stage["alternatives"][0]]])
            if operation == "compare" else None),
        "stage_id": stage["id"] if operation == "preview" else None,
        "alternative": stage["alternatives"][0] if operation == "preview" else None,
    }


@pytest.mark.parametrize("operation", ["preview", "compare"])
def test_jeeves_tool_replays_authoritative_source_and_is_deterministic(operation):
    request = _request(operation)
    direct = execute_story_checkpoint_tool(request, authorized=True)
    via_jeeves = JeevesGameOrchestrator().authoritative_story_checkpoint(
        request, authorized=True)
    assert direct == via_jeeves
    assert direct["operation"] == operation
    assert direct["canonical_replay"]["replayed_from_authoritative_source"] is True
    assert direct["file_write_performed"] is False
    assert direct["browser_checkpoint_trusted"] is False
    assert direct["release_certified"] is False


def test_schema_is_closed_and_model_cannot_grant_itself_authority():
    descriptor = tool_schema()
    assert descriptor["name"] == "studio_original_story_checkpoint"
    assert descriptor["parameters"]["additionalProperties"] is False
    assert set(descriptor["parameters"]["required"]) == set(_request())
    with pytest.raises(PermissionError):
        execute_story_checkpoint_tool(_request(), authorized=False)
    with pytest.raises(PermissionError):
        JeevesGameOrchestrator().authoritative_story_checkpoint(
            _request(), authorized=False)
    request = _request()
    request["authorized"] = True
    with pytest.raises(StudioQuestError):
        execute_story_checkpoint_tool(request, authorized=True)


@pytest.mark.parametrize("field,bad", [
    ("schema", "v2"), ("project_id", "../wrong"),
    ("expected_quest_source_digest", "0" * 64),
    ("operation", "write"), ("current_checkpoint", 1),
    ("stage_id", True), ("candidate_checkpoint", "unexpected"),
])
def test_invalid_typed_preview_fails_closed(field, bad):
    request = _request()
    request[field] = bad
    with pytest.raises((StudioQuestError, ValueError, TypeError)):
        execute_story_checkpoint_tool(request, authorized=True)


def test_comparison_rejects_stale_source_forged_flags_and_duplicate_json():
    request = _request("compare")
    bad = deepcopy(request)
    bad["candidate_checkpoint"] = '{"schema":1,"schema":2}'
    with pytest.raises(StudioQuestError):
        execute_story_checkpoint_tool(bad, authorized=True)
    bad = deepcopy(request)
    forged = json.loads(bad["candidate_checkpoint"])
    forged["release_certified"] = True
    bad["candidate_checkpoint"] = json.dumps(forged)
    with pytest.raises(StudioQuestError):
        execute_story_checkpoint_tool(bad, authorized=True)
    bad = deepcopy(request)
    bad["stage_id"] = "forged"
    with pytest.raises(StudioQuestError):
        execute_story_checkpoint_tool(bad, authorized=True)
