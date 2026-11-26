"""Jeeves choice replay is typed, source-bound and operator-gated."""
from __future__ import annotations

import pytest

from skeleton.ai.agents.jeeves.jeeves_game_orchestrator import JeevesGameOrchestrator
from skeleton.ai.agents.jeeves.studio_choice_rehearsal_tool import (
    REQUEST_SCHEMA, execute_choice_rehearsal_tool, tool_schema,
)
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_director_choice_rehearsal import EXPORT_SCHEMA
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def request():
    documents = read_blueprint(PROJECT)
    source = audit_canon_source(documents, authorized=True)["source_digest"]
    program = compile_quest_program(documents)
    session = replay_quest(documents, [], authorized=True).digest
    export = {
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "source_digest": source, "quest_source_digest": program.source_digest,
        "base_session_digest": session, "base_actions": [], "actions": [],
    }
    return {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "expected_session_digest": session,
        "export": export,
    }


def test_jeeves_choice_replay_is_deterministic_and_has_no_write_authority():
    value = request()
    first = execute_choice_rehearsal_tool(value, authorized=True)
    second = JeevesGameOrchestrator().authoritative_choice_rehearsal(
        value, authorized=True)
    assert first == second
    assert first["canonical_replay"]["replay_verified"] is True
    assert first["canonical_replay"]["verified_actions"] == []
    assert first["file_write_performed"] is False
    assert first["browser_export_trusted"] is False
    assert first["release_certified"] is False


def test_schema_is_closed_and_requires_exact_fields():
    schema = tool_schema()
    assert schema["name"] == "studio_original_choice_rehearsal"
    assert schema["parameters"]["additionalProperties"] is False
    assert set(schema["parameters"]["required"]) == set(request())


def test_model_cannot_self_grant_authorization():
    with pytest.raises(PermissionError):
        execute_choice_rehearsal_tool(request(), authorized=False)
    with pytest.raises(PermissionError):
        JeevesGameOrchestrator().authoritative_choice_rehearsal(
            request(), authorized=False)


@pytest.mark.parametrize("field,wrong", [
    ("schema", "v2"),
    ("project_id", "../other"),
    ("project_id", True),
    ("expected_source_digest", "0" * 64),
    ("expected_session_digest", "0" * 64),
    ("export", {}),
    ("export", True),
])
def test_bad_typed_request_or_stale_lease_rejected(field, wrong):
    value = request()
    value[field] = wrong
    with pytest.raises((StudioQuestError, ValueError, TypeError)):
        execute_choice_rehearsal_tool(value, authorized=True)


def test_extra_and_missing_fields_fail_closed():
    value = request()
    value["authorized"] = True
    with pytest.raises(StudioQuestError):
        execute_choice_rehearsal_tool(value, authorized=True)
    del value["authorized"]
    del value["export"]
    with pytest.raises(StudioQuestError):
        execute_choice_rehearsal_tool(value, authorized=True)


def test_one_authored_choice_replays_to_derived_session():
    value = request()
    stage = compile_quest_program(read_blueprint(PROJECT)).stages[0]
    value["export"]["actions"] = [[stage.key, stage.alternatives[0]]]
    result = execute_choice_rehearsal_tool(value, authorized=True)
    assert result["canonical_replay"]["progress"]["stage_completed"] == 1
    assert result["canonical_replay"]["result_session_digest"] != (
        value["expected_session_digest"])
