"""Source-bound NPC chronology: deterministic replay, typed/CLI parity and guards."""
import json

import pytest

from skeleton.ai.agents.jeeves.studio_walk_tool import (
    NPC_CONTINUITY_REQUEST_SCHEMA, execute_npc_continuity_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import compile_dialogue_staging
from skeleton.ai.game_builder.studio_ecosystem_npc_continuity import (
    NPC_CONTINUITY_SCHEMA, audit_npc_continuity,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    return docs, source


def test_canonical_chronology_and_causal_replay_is_deterministic():
    docs, source = fixture()
    unchanged = json.dumps(docs, sort_keys=True)
    result = audit_npc_continuity(
        docs, [], expected_source_digest=source, authorized=True)
    assert result["schema"] == NPC_CONTINUITY_SCHEMA
    assert result["source_digest"] == source
    assert result["session_digest"] == replay_quest(
        docs, [], authorized=True).digest
    assert result["authored_scene_count"] == len(
        compile_dialogue_staging(docs, [], authorized=True)["cards"])
    assert result["visible_scene_count"] == len(result["timeline"])
    assert sum(len(npc["scene_ids"]) for npc in result["cast"]) == len(result["timeline"])
    assert [scene["scene_index"] for scene in result["timeline"]] == list(
        range(result["authored_scene_count"]))
    assert all(not scene["interaction_verified"] for scene in result["timeline"])
    assert all(scene["authored_cue_sources"] for scene in result["timeline"])
    assert result["replay_verified"] and result["source_unchanged"]
    assert not result["file_write_performed"] and not result["release_certified"]
    assert json.dumps(docs, sort_keys=True) == unchanged
    assert result == audit_npc_continuity(
        docs, [], expected_source_digest=source, authorized=True)


def test_cast_filter_keeps_global_causality_and_replay_lease():
    docs, source = fixture()
    all_scenes = audit_npc_continuity(
        docs, [], expected_source_digest=source, authorized=True)
    npc = all_scenes["cast"][0]["npc_id"]
    subset = audit_npc_continuity(
        docs, [], authorized=True, expected_source_digest=source,
        expected_session_digest=all_scenes["session_digest"], npc_id=npc)
    assert subset["cast_count"] == 1
    assert subset["visible_scene_count"] == len(subset["cast"][0]["scene_ids"])
    assert all(scene["npc_id"] == npc for scene in subset["timeline"])
    assert subset["causality_violations"] == all_scenes["causality_violations"]
    assert subset["source_digest"] == all_scenes["source_digest"]


def test_choices_change_status_not_authored_chronology():
    docs, source = fixture()
    initial = audit_npc_continuity(
        docs, [], authorized=True, expected_source_digest=source)
    stage = compile_quest_program(docs).stages[0]
    actions = [[stage.key, stage.alternatives[0]]]
    played = audit_npc_continuity(
        docs, actions, authorized=True, expected_source_digest=source)
    assert played["session_digest"] != initial["session_digest"]
    assert [s["scene_id"] for s in played["timeline"]] == [
        s["scene_id"] for s in initial["timeline"]]
    assert any(s["status"] == "completed" for s in played["timeline"])
    assert not any(s["interaction_verified"] for s in played["timeline"])


@pytest.mark.parametrize("override", [
    {"expected_source_digest": "0" * 64},
    {"expected_source_digest": "invalid"},
    {"expected_session_digest": "0" * 64},
    {"expected_session_digest": True},
    {"npc_id": "../escape"},
    {"npc_id": "unknown_npc"},
    {"npc_id": True},
    {"require_chronological_prerequisites": 1},
])
def test_bad_leases_filters_and_flags_fail_closed(override):
    docs, source = fixture()
    kwargs = {"expected_source_digest": source, "authorized": True}
    kwargs.update(override)
    with pytest.raises(StudioQuestError):
        audit_npc_continuity(docs, [], **kwargs)


def test_requires_real_operator_authority():
    docs, source = fixture()
    with pytest.raises(PermissionError):
        audit_npc_continuity(
            docs, [], expected_source_digest=source, authorized=False)


def test_typed_jeeves_and_cli_parity_and_mode_exclusion(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, source = fixture()
    req = {"schema": NPC_CONTINUITY_REQUEST_SCHEMA, "project_id": PROJECT,
           "expected_source_digest": source, "actions": []}
    typed = execute_npc_continuity_tool(req, authorized=True)
    assert main(["--project", PROJECT, "--dialogue-stage",
                 "--dialogue-actions", "[]", "--dialogue-expected-digest", source,
                 "--dialogue-continuity"]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_npc_continuity_tool({**req, "forged": True}, authorized=True)
    with pytest.raises(PermissionError):
        execute_npc_continuity_tool(req, authorized=False)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-continuity"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-continuity", "--dialogue-npc-codex"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-continuity-npc-id", "npc"])
