"""Source-backed original NPC scene cards, chronology and CLI/Jeeves parity."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import (
    DIALOGUE_SCHEMA, compile_dialogue_staging,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_STAGING_REQUEST_SCHEMA, execute_dialogue_staging_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"
FIRST = ["investigate", "Document fracturing ice without entering restricted ground"]


def test_scene_cues_are_original_source_anchored_and_quest_gated():
    docs = read_blueprint(PROJECT)
    original = deepcopy(docs)
    result = compile_dialogue_staging(docs, [], authorized=True)
    assert result["schema"] == DIALOGUE_SCHEMA
    assert result["scene_count"] == 3
    assert [card["status"] for card in result["cards"]] == [
        "available", "locked", "locked"]
    first = result["cards"][0]
    assert first["npc_id"] == "witness"
    assert first["npc_name"] == "Iva Wynn"
    assert first["authored_cues"][0]["text"] == docs["cast"]["support"][0]["knows"]
    assert first["authored_cues"][0]["source_ref"] == "cast.support.witness.knows"
    assert first["selected_alternative"] is None
    assert first["dialogue_spoken_verified"] is False
    assert docs == original
    assert result == compile_dialogue_staging(deepcopy(docs), [], authorized=True)


def test_quest_replay_unlocks_dialogue_without_forging_testimony():
    docs = read_blueprint(PROJECT)
    result = compile_dialogue_staging(docs, [FIRST], authorized=True)
    assert [card["status"] for card in result["cards"]] == [
        "completed", "available", "locked"]
    assert result["cards"][0]["selected_alternative"] == FIRST[1]
    assert result["cards"][1]["npc_id"] == "rival"
    assert result["cards"][1]["selected_alternative"] is None
    selected = compile_dialogue_staging(
        docs, [FIRST], scene_id="contest", authorized=True)
    assert selected["scene_count"] == 1
    assert selected["cards"][0]["card_digest"] == result["cards"][1]["card_digest"]
    assert selected["external_evidence_verified"] is False


def test_scene_dialogue_rejects_forged_source_and_history():
    docs = read_blueprint(PROJECT)
    with pytest.raises(PermissionError):
        compile_dialogue_staging(docs, [], authorized=False)
    with pytest.raises(StudioQuestError, match="stale"):
        compile_dialogue_staging(
            docs, [], authorized=True, expected_source_digest="0" * 64)
    with pytest.raises(StudioQuestError):
        compile_dialogue_staging(docs, [["ratify", "residents_vote"]], authorized=True)
    with pytest.raises(StudioQuestError):
        compile_dialogue_staging(docs, [], authorized=True, scene_id="unwritten")
    for section, key, value in (
        ("scene", "dialogue_hook", "unwritten"),
        ("scene", "quest_stage", "unwritten"),
        ("scene", "id", "contest"),
    ):
        altered = deepcopy(docs)
        altered["scene"]["episode_plan"][0][key] = value
        with pytest.raises(StudioQuestError):
            compile_dialogue_staging(altered, [], authorized=True)
    repeated = deepcopy(docs)
    repeated["cast"]["support"][1]["id"] = "witness"
    with pytest.raises(StudioQuestError):
        compile_dialogue_staging(repeated, [], authorized=True)


def test_dialogue_cli_and_jeeves_replay_same_source(capsys):
    from scripts.studio_ecosystem_cli import main
    docs = read_blueprint(PROJECT)
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    request = {
        "schema": DIALOGUE_STAGING_REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": digest, "actions": [FIRST], "scene_id": "contest",
    }
    with pytest.raises(PermissionError):
        execute_dialogue_staging_tool(request, authorized=False)
    typed = execute_dialogue_staging_tool(request, authorized=True)
    assert typed["file_write_performed"] is False
    assert main(["--project", PROJECT, "--dialogue-stage",
                 "--dialogue-scene-id", "contest",
                 "--dialogue-actions", json.dumps([FIRST]),
                 "--dialogue-expected-digest", digest]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_dialogue_staging_tool({**request, "unexpected": 1}, authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-actions", '[["ratify","residents_vote"]]'])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-scene-id", "origin"])
