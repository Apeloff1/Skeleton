"""Source-bound NPC choice previews through canonical CLI and typed Jeeves."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_choice_preview import (
    PREVIEW_SCHEMA, preview_dialogue_choices,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_PREVIEW_REQUEST_SCHEMA, execute_dialogue_preview_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def test_original_npc_choices_are_replay_verified_without_mutation():
    docs = read_blueprint(PROJECT)
    original = deepcopy(docs)
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    result = preview_dialogue_choices(
        docs, [], authorized=True, expected_source_digest=digest)
    assert result["schema"] == PREVIEW_SCHEMA
    assert result["source_digest"] == digest
    assert result["preview_count"] > 0
    assert result["choice_committed"] is False
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    assert docs == original
    assert result == preview_dialogue_choices(
        deepcopy(docs), [], authorized=True, expected_source_digest=digest)
    before = replay_quest(docs, [], authorized=True)
    for item in result["previews"]:
        assert item["before_session_digest"] == before.digest
        after = replay_quest(
            docs, [[item["quest_stage"], item["alternative"]]], authorized=True)
        assert item["after_session_digest"] == after.digest
        assert item["choice_committed"] is False


def test_locked_completed_and_unknown_scene_holds():
    docs = read_blueprint(PROJECT)
    initial = preview_dialogue_choices(docs, [], authorized=True)
    assert any(card["status"] == "locked" for card in initial["cards"])
    first = initial["previews"][0]
    chosen = [[first["quest_stage"], first["alternative"]]]
    result = preview_dialogue_choices(docs, chosen, authorized=True)
    completed = next(card for card in result["cards"]
                     if card["quest_stage"] == first["quest_stage"])
    assert completed["status"] == "completed"
    assert completed["available_alternatives"] == []
    assert all(preview["quest_stage"] != first["quest_stage"]
               for preview in result["previews"])
    with pytest.raises(StudioQuestError):
        preview_dialogue_choices(docs, [], scene_id="nonexistent", authorized=True)


def test_preview_fails_closed_on_forged_source_and_replay():
    docs = read_blueprint(PROJECT)
    with pytest.raises(PermissionError):
        preview_dialogue_choices(docs, [], authorized=False)
    with pytest.raises(StudioQuestError):
        preview_dialogue_choices(docs, [], authorized=True,
                                 expected_source_digest="0" * 64)
    with pytest.raises(StudioQuestError):
        preview_dialogue_choices(docs, [["forged", "win"]], authorized=True)
    with pytest.raises(StudioQuestError):
        preview_dialogue_choices(docs, ["not an action"], authorized=True)
    with pytest.raises(StudioQuestError):
        preview_dialogue_choices(docs, [], authorized=True, scene_id="")
    with pytest.raises(StudioQuestError):
        preview_dialogue_choices(docs, [], authorized=True, scene_id="a\n")


def test_cli_and_typed_jeeves_preview_parity(capsys):
    from scripts.studio_ecosystem_cli import main
    docs = read_blueprint(PROJECT)
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    request = {
        "schema": DIALOGUE_PREVIEW_REQUEST_SCHEMA,
        "project_id": PROJECT,
        "expected_source_digest": digest,
        "actions": [],
    }
    with pytest.raises(PermissionError):
        execute_dialogue_preview_tool(request, authorized=False)
    typed = execute_dialogue_preview_tool(request, authorized=True)
    assert typed["file_write_performed"] is False
    assert main(["--project", PROJECT, "--dialogue-stage", "--dialogue-preview",
                 "--dialogue-expected-digest", digest]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_dialogue_preview_tool({**request, "unexpected": True},
                                      authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-preview"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage", "--dialogue-preview",
              "--dialogue-export", "--output", "must-not-create"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage", "--dialogue-preview",
              "--dialogue-actions", '{"a":1,"a":2}'])


def test_typed_preview_of_authored_revision_preserves_source_identity():
    docs = read_blueprint(PROJECT)
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    request = {
        "schema": DIALOGUE_PREVIEW_REQUEST_SCHEMA,
        "project_id": PROJECT, "expected_source_digest": digest,
        "actions": [],
        "edits": [{"section": "cast", "path": ["support", 0, "knows"],
                   "value": "An original archive witness must reconcile two signed records."}],
    }
    result = execute_dialogue_preview_tool(request, authorized=True)
    assert result["detail"]["source_digest"] == result["author_receipt"]["revised_source_digest"]
    assert result["detail"]["source_digest"] != digest
    assert result["detail"]["choice_committed"] is False
    assert result == execute_dialogue_preview_tool(request, authorized=True)
