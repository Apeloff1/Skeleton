"""Jeeves routing and operator CLI acceptance for quest readiness."""
from __future__ import annotations
import json
import pytest
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.agents.jeeves import studio_quest_readiness_tool as tool


def docs():
    return {
        "quest": {"project_id": "route", "release_certified": False,
                  "stage_graph": [{
                      "id": "finish", "prerequisites": [],
                      "alternatives": ["win"], "reward": "done",
                  }]},
        "narrative": {"project_id": "route", "release_certified": False,
                      "endings": [{"id": "victory", "requires": ["done"]}]},
    }


def request(source):
    return {
        "schema": tool.REQUEST_SCHEMA,
        "project_id": "route",
        "authoring": {"max_states": 32, "max_depth": 1},
        "expected_source_digest": compile_quest_program(source).source_digest,
        "expected_initial_session_digest": start_quest(
            source, authorized=True).digest,
    }


def test_typed_tool_requires_authority_and_is_read_only(monkeypatch):
    source = docs()
    monkeypatch.setattr(tool, "read_blueprint", lambda _: source)
    payload = request(source)
    with pytest.raises(PermissionError):
        tool.execute_quest_readiness_tool(payload, authorized=False)
    result = tool.execute_quest_readiness_tool(payload, authorized=True)
    assert result["detail"]["playable_handoff_allowed"] is True
    assert result["file_write_performed"] is False
    with pytest.raises(StudioQuestError):
        tool.execute_quest_readiness_tool(
            {**payload, "allow_authoring": True}, authorized=True)


def test_static_router_exposes_read_only_joint_proof(monkeypatch):
    from skeleton.ai.agents.jeeves.studio_world_tool_router import (
        route_world_tool, world_tool_catalog,
    )
    source = docs()
    monkeypatch.setattr(tool, "read_blueprint", lambda _: source)
    descriptor = next(x for x in world_tool_catalog()["tools"]
                      if x["name"] == "studio_original_quest_readiness")
    assert descriptor["explicit_authoring_permission_required"] is False
    envelope = {
        "tool": "studio_original_quest_readiness",
        "arguments": request(source),
    }
    with pytest.raises(PermissionError):
        route_world_tool(envelope, authorized=False)
    result = route_world_tool(envelope, authorized=True)
    assert result["file_write_performed"] is False
    assert result["result"]["detail"]["playable_handoff_allowed"] is True
    with pytest.raises(StudioQuestError):
        route_world_tool({
            **envelope, "arguments": {
                **envelope["arguments"], "allow_authoring": True,
            },
        }, authorized=True)


def test_cli_publishes_replayable_evidence_and_handoff(monkeypatch, tmp_path, capsys):
    from scripts import studio_quest_readiness_cli as cli
    source = docs()
    monkeypatch.setattr(cli, "read_blueprint", lambda _: source)
    req = request(source)
    base = [
        "--project", "route",
        "--expected-source", req["expected_source_digest"],
        "--expected-session", req["expected_initial_session_digest"],
    ]
    assert cli.main(base + [
        "--prompt", "--playable", "--publish", str(tmp_path)]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["readiness"]["playable_handoff_allowed"] is True
    assert response["playable_handoff"]["canonical_quest_replay_verified"] is True
    assert response["file_write_performed"] is True
    assert cli.main(base + ["--restore", str(tmp_path)]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["readiness"] == response["readiness"]
    assert restored["file_write_performed"] is False
