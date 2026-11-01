"""NPC knowledge provenance, guarded reveals, private custody and Jeeves parity."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import compile_dialogue_staging
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge import (
    REQUEST_SCHEMA, SCHEMA, compile_npc_knowledge, publish_npc_knowledge,
    render_npc_knowledge_html, source_knowledge_facts, verify_npc_knowledge,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_prompt import propose_npc_knowledge
from skeleton.ai.agents.jeeves.studio_npc_knowledge_tool import (
    REQUEST_SCHEMA as TOOL_SCHEMA, execute_npc_knowledge_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    session = replay_quest(docs, [], authorized=True)
    staging = compile_dialogue_staging(
        docs, [], authorized=True, expected_source_digest=source)
    return docs, source, session, staging


def authoring():
    docs, source, session, staging = fixture()
    facts = source_knowledge_facts(
        docs, [], authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)
    cards = staging["cards"]
    for fact in facts["facts"]:
        source_index = next(i for i, c in enumerate(cards)
                            if c["scene_id"] == fact["scene_id"])
        for recipient in cards[source_index + 1:]:
            if recipient["npc_id"] != fact["npc_id"]:
                return {"schema": REQUEST_SCHEMA, "reveals": [{
                    "fact_id": fact["fact_id"],
                    "recipient_scene_id": recipient["scene_id"],
                    "required_alternative": None,
                }]}
    pytest.skip("project has no cross-NPC authored scene pair")


def test_pending_knowledge_never_mints_npc_speech():
    docs, source, session, _ = fixture()
    request = authoring()
    before = json.dumps(docs, sort_keys=True)
    compiled = compile_npc_knowledge(
        docs, [], request, authorized=True,
        expected_source_digest=source, expected_session_digest=session.digest)
    assert compiled["schema"] == SCHEMA
    assert compiled["pending_count"] == 1
    assert compiled["earned_count"] == 0
    assert compiled["npc_speech_verified"] is False
    assert compiled["release_certified"] is False
    assert all(not scene["received_facts"] for scene in compiled["scenes"])
    assert json.dumps(docs, sort_keys=True) == before
    assert compiled == compile_npc_knowledge(
        docs, [], request, authorized=True, expected_source_digest=source)


def test_completed_replay_earns_only_authored_source_facts():
    docs, source, _, _ = fixture()
    program = compile_quest_program(docs)
    actions = [[stage.key, stage.alternatives[0]] for stage in program.stages]
    session = replay_quest(docs, actions, authorized=True)
    compiled = compile_npc_knowledge(
        docs, actions, authoring(), authorized=True,
        expected_source_digest=source, expected_session_digest=session.digest)
    assert compiled["earned_count"] == 1
    assert compiled["pending_count"] == 0
    assert sum(len(scene["received_facts"]) for scene in compiled["scenes"]) == 1
    assert b"<script" not in render_npc_knowledge_html(compiled).lower()


@pytest.mark.parametrize("mutate", [
    lambda x: x.update({"schema": "forged"}),
    lambda x: x["reveals"][0].update({"fact_id": "forged"}),
    lambda x: x["reveals"][0].update({"recipient_scene_id": "forged"}),
    lambda x: x["reveals"][0].update({"required_alternative": True}),
    lambda x: x["reveals"][0].update({"extra": True}),
    lambda x: x["reveals"].append(dict(x["reveals"][0])),
])
def test_invalid_or_duplicate_reveal_fails_closed(mutate):
    docs, source, _, _ = fixture()
    request = authoring()
    mutate(request)
    with pytest.raises(StudioQuestError):
        compile_npc_knowledge(docs, [], request, authorized=True,
                              expected_source_digest=source)


def test_source_session_and_operator_authority_fail_closed():
    docs, source, _, _ = fixture()
    request = authoring()
    with pytest.raises(PermissionError):
        compile_npc_knowledge(docs, [], request, authorized=False,
                              expected_source_digest=source)
    for lease in ("0" * 64, True, "", None):
        with pytest.raises(StudioQuestError):
            compile_npc_knowledge(docs, [], request, authorized=True,
                                  expected_source_digest=lease)
    with pytest.raises(StudioQuestError):
        compile_npc_knowledge(docs, [], request, authorized=True,
                              expected_source_digest=source,
                              expected_session_digest="0" * 64)


def test_private_immutable_publication_and_tamper_rejection(tmp_path):
    docs, source, _, _ = fixture()
    request = authoring()
    compiled = compile_npc_knowledge(
        docs, [], request, authorized=True, expected_source_digest=source)
    publication = publish_npc_knowledge(
        compiled, tmp_path, authorized=True, documents=docs, actions=[])
    assert publication["file_write_performed"] is True
    path = tmp_path / "studio_npc_knowledge.json"
    assert path.is_file() and path.stat().st_mode & 0o077 == 0
    assert verify_npc_knowledge(
        docs, [], tmp_path, authorized=True, expected_source_digest=source) == compiled
    with pytest.raises(FileExistsError):
        publish_npc_knowledge(compiled, tmp_path, authorized=True,
                              documents=docs, actions=[])
    forged = dict(compiled)
    forged["earned_count"] += 1
    path.write_text(json.dumps(forged))
    with pytest.raises(StudioQuestError):
        verify_npc_knowledge(docs, [], tmp_path, authorized=True,
                             expected_source_digest=source)


def test_symlinked_destination_is_rejected(tmp_path):
    docs, source, _, _ = fixture()
    compiled = compile_npc_knowledge(
        docs, [], authoring(), authorized=True, expected_source_digest=source)
    destination = tmp_path / "private"
    destination.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(destination, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported")
    with pytest.raises(OSError):
        publish_npc_knowledge(compiled, linked, authorized=True,
                              documents=docs, actions=[])


def test_prompt_plan_is_deterministic_and_uses_original_source_only():
    docs, source, session, _ = fixture()
    first = propose_npc_knowledge(
        docs, [], "share original NPC knowledge across scenes",
        authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)
    assert first == propose_npc_knowledge(
        docs, [], "share original NPC knowledge across scenes",
        authorized=True, expected_source_digest=source)
    assert first["model_inference_performed"] is False
    assert first["compiled"]["pending_count"] >= 1
    with pytest.raises(StudioQuestError):
        propose_npc_knowledge(docs, [], "bad\ncontrol", authorized=True,
                              expected_source_digest=source)


def test_typed_jeeves_router_matches_direct_adapter():
    docs, source, _, _ = fixture()
    request = {
        "schema": TOOL_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "actions": [],
        "authoring": authoring(),
    }
    envelope = {"tool": "studio_original_npc_knowledge", "arguments": request}
    assert "studio_original_npc_knowledge" in [
        entry["name"] for entry in world_tool_catalog()["tools"]]
    direct = execute_npc_knowledge_tool(request, authorized=True)
    routed = route_world_tool(envelope, authorized=True)
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
    assert routed == route_world_tool(envelope, authorized=True)


def test_cli_strict_authoring_round_trip(capsys):
    from scripts.studio_npc_knowledge_cli import main
    docs, source, _, _ = fixture()
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--authoring-json", json.dumps(authoring()),
                 "--include-html"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["compiled"]["source_digest"] == source
    assert "<main>" in receipt["director_companion_html"]
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--expected-source", source,
              "--authoring-json", '{"schema":"a","schema":"b"}'])
