"""Deterministic NPC dialogue knowledge gate source and custody regressions."""
from __future__ import annotations

import copy

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_npc_dialogue_knowledge_gate import (
    PROMPT, SCHEMA, compile_npc_dialogue_knowledge_gate,
    propose_npc_dialogue_knowledge_gate, replay_npc_dialogue_knowledge_gate,
    compile_npc_dialogue_gate_playable, publish_npc_dialogue_knowledge_gate,
    restore_npc_dialogue_knowledge_gate, FILENAME,
)
from skeleton.ai.agents.jeeves.studio_npc_dialogue_knowledge_gate_tool import (
    REQUEST_SCHEMA, execute_npc_dialogue_knowledge_gate_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from tests.test_studio_npc_relay_impact import fixture, PROJECT


def test_prompt_to_typed_dialogue_gate_and_exact_replay():
    docs, source, _, relay = fixture()
    result = propose_npc_dialogue_knowledge_gate(
        docs, relay, PROMPT, authorized=True, expected_source_digest=source)
    assert result["schema"] == SCHEMA
    assert result == compile_npc_dialogue_knowledge_gate(
        docs, relay, result["authoring"], authorized=True,
        expected_source_digest=source)
    assert replay_npc_dialogue_knowledge_gate(
        docs, result, authorized=True) == result
    assert result["dialogue_spoken_verified"] is False
    assert result["release_certified"] is False
    assert all(row["source_text_in_gate_row"] is False for row in result["gates"])
    assert result["allowed_count"] + result["blocked_count"] == len(result["gates"])
    if not result["playable_handoff_allowed"]:
        with pytest.raises(StudioQuestError):
            compile_npc_dialogue_gate_playable(docs, result, authorized=True)


def test_invalid_gate_identity_stale_proof_and_forged_replay():
    docs, source, _, relay = fixture()
    valid = propose_npc_dialogue_knowledge_gate(
        docs, relay, PROMPT, authorized=True, expected_source_digest=source)
    with pytest.raises(PermissionError):
        compile_npc_dialogue_knowledge_gate(
            docs, relay, {"gates": []}, authorized=False,
            expected_source_digest=source)
    for bad in ({"gates": [1]}, {"gates": [{}]},
                {"gates": "wrong"}, {"gates": [], "authorized": True}):
        with pytest.raises(StudioQuestError):
            compile_npc_dialogue_knowledge_gate(
                docs, relay, bad, authorized=True,
                expected_source_digest=source)
    for field, value in (("allowed_count", 99),
                         ("source_replay_verified", 1),
                         ("release_certified", True),
                         ("blocked_count", False)):
        forged = copy.deepcopy(valid)
        forged[field] = value
        with pytest.raises(StudioQuestError):
            replay_npc_dialogue_knowledge_gate(
                docs, forged, authorized=True)
    if valid["authoring"]["gates"]:
        altered = copy.deepcopy(valid["authoring"])
        altered["gates"][0]["expected_relay_proof_digest"] = "0" * 64
        with pytest.raises(StudioQuestError):
            compile_npc_dialogue_knowledge_gate(
                docs, relay, altered, authorized=True,
                expected_source_digest=source)


def test_private_immutable_gate_receipt_and_symlink_rejection(tmp_path):
    docs, source, _, relay = fixture()
    valid = propose_npc_dialogue_knowledge_gate(
        docs, relay, PROMPT, authorized=True, expected_source_digest=source)
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    saved = publish_npc_dialogue_knowledge_gate(
        docs, valid, directory, authorized=True)
    assert saved["file_write_performed"] is True
    assert restore_npc_dialogue_knowledge_gate(
        docs, directory, authorized=True,
        expected_source_digest=source) == valid
    with pytest.raises(FileExistsError):
        publish_npc_dialogue_knowledge_gate(
            docs, valid, directory, authorized=True)
    (directory / FILENAME).unlink()
    (directory / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((OSError, StudioQuestError)):
        restore_npc_dialogue_knowledge_gate(
            docs, directory, authorized=True,
            expected_source_digest=source)


def test_jeeves_static_tool_and_bounded_router():
    docs, source, _, relay = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "relay_receipt": relay,
        "prompt": PROMPT,
    }
    from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical
    if len(_canonical(request)) <= 60 * 1024:
        result = execute_npc_dialogue_knowledge_gate_tool(
            request, authorized=True)
        assert result["detail"]["source_replay_verified"] is True
        envelope = {
            "tool": "studio_original_npc_dialogue_knowledge_gate",
            "arguments": request,
        }
        if len(_canonical(envelope)) <= 64 * 1024:
            routed = route_world_tool(envelope, authorized=True)
            assert routed["result"]["detail"] == result["detail"]
        else:
            with pytest.raises(StudioQuestError):
                route_world_tool(envelope, authorized=True)
    else:
        with pytest.raises(StudioQuestError):
            execute_npc_dialogue_knowledge_gate_tool(
                request, authorized=True)
    assert "studio_original_npc_dialogue_knowledge_gate" in {
        item["name"] for item in world_tool_catalog()["tools"]
    }
    with pytest.raises(PermissionError):
        execute_npc_dialogue_knowledge_gate_tool(
            request, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_npc_dialogue_knowledge_gate_tool(
            {**request, "authorized": True}, authorized=True)
