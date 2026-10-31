"""Jeeves invokes the canonical offline walk engine with explicit authority."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.ai.agents.jeeves import studio_walk_tool as tool
from skeleton.ai.agents.jeeves.jeeves_game_orchestrator import JeevesGameOrchestrator
from skeleton.ai.game_builder import studio_ecosystem_walk_replay as replay
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

WORLD = {
    "project_id": "original-world", "source_digest": "f" * 64,
    "width": 4, "height": 4, "spawn": [1, 1], "target": [2, 1],
    "maps": [["####", "#..#", "#..#", "####"]],
    "stages": [{"id": "scene-one", "alternatives": ["inspect"],
                "prerequisites": []}],
}


def request(**changes):
    value = {"schema": tool.REQUEST_SCHEMA, "project_id": "original-world",
             "operation": "replay", "events": []}
    value.update(changes)
    return value


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setattr(tool, "read_blueprint", lambda _: {})
    monkeypatch.setattr(replay, "playable_world_source", lambda _: WORLD)


def test_jeeves_orchestrator_calls_real_canonical_replay(source):
    orchestrator = JeevesGameOrchestrator()
    start = orchestrator.authoritative_walk(request(), authorized=True)
    assert start["schema"] == tool.RESULT_SCHEMA
    assert start["receipt"]["position"] == [1, 1]
    assert start["replay_verified"] is True
    assert start["release_certified"] is False
    assert start["native_genre_runtime_verified"] is False
    moved = orchestrator.authoritative_walk(request(
        receipt=start["receipt"], events=[["move", "right"]]), authorized=True)
    assert moved["receipt"]["position"] == [2, 1]
    finished = orchestrator.authoritative_walk(request(
        receipt=moved["receipt"], events=[["choose", "inspect"]]), authorized=True)
    assert finished["receipt"]["scene_index"] == 1
    assert finished["receipt"]["choices"] == [["scene-one", "inspect"]]
    assert finished == orchestrator.authoritative_walk(request(
        receipt=moved["receipt"], events=[["choose", "inspect"]]), authorized=True)


def test_jeeves_tool_read_only_inspection_and_route(source):
    route = tool.execute_walk_tool(request(operation="route"), authorized=True)
    assert route["detail"]["status"] in {"ready", "already_near"}
    assert route["receipt"]["events"] == []
    choices = tool.execute_walk_tool(request(operation="choices"), authorized=True)
    assert choices["receipt"]["events"] == []
    timeline = tool.execute_walk_tool(request(operation="timeline"), authorized=True)
    assert timeline["receipt"]["events"] == []


def test_jeeves_tool_denies_untrusted_calls_before_source(monkeypatch):
    monkeypatch.setattr(tool, "read_blueprint", lambda _: pytest.fail("source read without authorization"))
    with pytest.raises(PermissionError):
        tool.execute_walk_tool(request())
    with pytest.raises(PermissionError):
        tool.execute_walk_tool(request(), authorized=1)


@pytest.mark.parametrize("change", [
    {"schema": "future"}, {"project_id": ""}, {"operation": "delete"},
    {"events": "not events"}, {"events": [["move", "north"]]},
    {"events": [["move", "right", "extra"]]}, {"unauthorized": True},
    {"forecast_depth": True}, {"forecast_depth": 4},
    {"compare_events": []},
    {"operation": "compare"},
    {"operation": "compare", "compare_events": "bad"},
])
def test_jeeves_tool_rejects_malformed_request_before_source(change, monkeypatch):
    monkeypatch.setattr(tool, "read_blueprint", lambda _: pytest.fail("malformed request reached source"))
    with pytest.raises(StudioQuestError):
        tool.execute_walk_tool(request(**change), authorized=True)


def test_jeeves_tool_rejects_forged_saved_receipt(source):
    original = tool.execute_walk_tool(request(), authorized=True)
    forged = deepcopy(original["receipt"])
    forged["position"] = [2, 1]
    with pytest.raises(StudioQuestError):
        tool.execute_walk_tool(request(receipt=forged), authorized=True)


def test_jeeves_tool_rejects_source_drift(source, monkeypatch):
    original = tool.execute_walk_tool(request(), authorized=True)
    monkeypatch.setattr(replay, "playable_world_source",
                        lambda _: dict(WORLD, source_digest="e" * 64))
    with pytest.raises(StudioQuestError):
        tool.execute_walk_tool(request(receipt=original["receipt"]), authorized=True)


def test_tool_descriptor_is_typed_and_operator_gated():
    schema = tool.tool_schema()
    assert schema["parameters"]["additionalProperties"] is False
    assert schema["parameters"]["properties"]["operation"]["enum"] == sorted(tool.OPERATIONS)
    assert schema["parameters"]["required"] == ["schema", "project_id", "operation", "events"]
