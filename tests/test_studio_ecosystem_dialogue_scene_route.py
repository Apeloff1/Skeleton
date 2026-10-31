"""Canonical NPC route planner: prerequisite closure, replay, CLI/Jeeves."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import (
    compile_dialogue_staging,
)
from skeleton.ai.game_builder.studio_ecosystem_dialogue_scene_route import (
    ROUTE_SCHEMA, plan_dialogue_scene_route,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_ROUTE_REQUEST_SCHEMA, execute_dialogue_route_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def _fixture():
    docs = read_blueprint(PROJECT)
    staging = compile_dialogue_staging(docs, [], authorized=True)
    target = staging["cards"][-1]["scene_id"]
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    return docs, target, source


def test_source_bound_route_unlocks_target_and_keeps_original_unchanged():
    docs, target, source = _fixture()
    before = json.dumps(docs, sort_keys=True)
    result = plan_dialogue_scene_route(
        docs, [], target_scene_id=target, authorized=True,
        expected_source_digest=source)
    assert result["schema"] == ROUTE_SCHEMA
    assert result["target_scene_id"] == target
    assert result["target_status"] == "available"
    assert result["step_count"] == len(result["steps"])
    assert result["planned_quest_receipt"]["session_digest"] == result["planned_session_digest"]
    assert result["target_choice_previews"]["session_digest"] == result["planned_session_digest"]
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    assert json.dumps(docs, sort_keys=True) == before
    assert result == plan_dialogue_scene_route(
        docs, [], target_scene_id=target, authorized=True,
        expected_source_digest=source)


def test_explicit_author_alternative_preferences_are_replayed():
    docs, target, source = _fixture()
    original = plan_dialogue_scene_route(
        docs, [], target_scene_id=target, authorized=True)
    assert original["steps"]
    stage = original["steps"][0]["quest_stage"]
    alternative = original["steps"][0]["alternative"]
    chosen = plan_dialogue_scene_route(
        docs, [], target_scene_id=target,
        preferred_alternatives={stage: alternative}, authorized=True)
    assert chosen["step_count"] == original["step_count"]
    assert chosen["steps"][0]["alternative"] == alternative
    assert chosen["target_status"] == "available"
    with pytest.raises(StudioQuestError):
        plan_dialogue_scene_route(
            docs, [], target_scene_id=target,
            preferred_alternatives={stage: "forged"}, authorized=True)


def test_completed_target_does_not_replay_unnecessary_ancestors():
    docs, target, source = _fixture()
    route = plan_dialogue_scene_route(
        docs, [], target_scene_id=target, authorized=True)
    history = route["planned_quest_receipt"]["choices"]
    session = replay_quest(docs, history, authorized=True)
    after = plan_dialogue_scene_route(
        docs, history, target_scene_id=target, authorized=True)
    assert after["step_count"] == 0
    assert after["original_session_digest"] == session.digest
    assert after["target_status"] == "available"


@pytest.mark.parametrize("overrides", [
    {"target_scene_id": "forged"},
    {"target_scene_id": "../scene"},
    {"expected_source_digest": "0" * 64},
    {"preferred_alternatives": []},
    {"preferred_alternatives": {"unrelated": "forged"}},
])
def test_route_invalid_target_and_preferences_fail_closed(overrides):
    docs, target, source = _fixture()
    kwargs = dict(target_scene_id=target, authorized=True,
                  expected_source_digest=source)
    kwargs.update(overrides)
    with pytest.raises(StudioQuestError):
        plan_dialogue_scene_route(docs, [], **kwargs)


def test_route_requires_operator_authority():
    docs, target, source = _fixture()
    with pytest.raises(PermissionError):
        plan_dialogue_scene_route(
            docs, [], target_scene_id=target, authorized=False)


def test_cli_and_typed_jeeves_route_parity(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, target, source = _fixture()
    request = {
        "schema": DIALOGUE_ROUTE_REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "actions": [],
        "target_scene_id": target,
    }
    typed = execute_dialogue_route_tool(request, authorized=True)
    assert main([
        "--project", PROJECT, "--dialogue-stage",
        "--dialogue-actions", "[]",
        "--dialogue-route-scene", target,
        "--dialogue-expected-digest", source,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_dialogue_route_tool({**request, "unknown": 1}, authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-route-choices", "{}"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-route-scene", target])

def test_route_private_handoff_is_source_replayable_and_exclusive(tmp_path, capsys):
    from scripts.studio_ecosystem_cli import main
    docs, target, source = _fixture()
    output = tmp_path / "npc-route"
    args = [
        "--project", PROJECT, "--dialogue-stage",
        "--dialogue-actions", "[]",
        "--dialogue-route-scene", target,
        "--dialogue-expected-digest", source,
        "--output", str(output),
    ]
    assert main(args) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["file_write_performed"] is True
    assert written["route"]["file_write_performed"] is False
    assert written["handoff"]["file_write_performed"] is True
    assert main([
        "--project", PROJECT, "--dialogue-stage",
        "--dialogue-import", str(output),
        "--dialogue-expected-digest", source,
    ]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["session_digest"] == written["route"]["planned_session_digest"]
    with pytest.raises(SystemExit):
        main(args)
    assert sorted(p.name for p in output.iterdir()) == ["dialogue.json", "receipt.json"]
