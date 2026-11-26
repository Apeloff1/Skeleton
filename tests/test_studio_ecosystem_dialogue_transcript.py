"""NPC source-bound authored transcript, pagination, CLI and Jeeves parity."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_choice_preview import (
    preview_dialogue_choices,
)
from skeleton.ai.game_builder.studio_ecosystem_dialogue_transcript import (
    TRANSCRIPT_SCHEMA, compile_dialogue_transcript,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_TRANSCRIPT_REQUEST_SCHEMA, execute_dialogue_transcript_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def _history():
    docs = read_blueprint(PROJECT)
    choice = preview_dialogue_choices(docs, [], authorized=True)["previews"][0]
    return docs, [[choice["quest_stage"], choice["alternative"]]]


def test_original_npc_cues_follow_replayed_choice_without_fabricated_speech():
    docs, actions = _history()
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    result = compile_dialogue_transcript(
        docs, actions, authorized=True, expected_source_digest=digest)
    assert result["schema"] == TRANSCRIPT_SCHEMA
    assert result["total_completed_scenes"] == 1
    assert result["entries"][0]["selected_alternative"] == actions[0][1]
    assert len(result["entries"][0]["authored_cues"]) == 5
    assert result["entries"][0]["dialogue_spoken_verified"] is False
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    assert result == compile_dialogue_transcript(
        docs, actions, authorized=True, expected_source_digest=digest)
    assert compile_dialogue_transcript(
        docs, [], authorized=True)["entries"] == []


def test_transcript_cursor_is_bound_to_history_and_source():
    docs, actions = _history()
    first = compile_dialogue_transcript(
        docs, actions, authorized=True, limit=1)
    assert first["next_offset"] is None
    empty = compile_dialogue_transcript(
        docs, actions, authorized=True, offset=1,
        expected_session_digest=first["session_digest"])
    assert empty["entries"] == []
    for options in (
        {"offset": 2}, {"offset": -1}, {"limit": 0},
        {"offset": True}, {"limit": 17},
        {"expected_session_digest": "0" * 64},
        {"expected_source_digest": "0" * 64},
    ):
        with pytest.raises(StudioQuestError):
            compile_dialogue_transcript(docs, actions, authorized=True, **options)
    with pytest.raises(PermissionError):
        compile_dialogue_transcript(docs, actions, authorized=False)


def test_cli_and_typed_jeeves_transcript_parity(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, actions = _history()
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    request = {
        "schema": DIALOGUE_TRANSCRIPT_REQUEST_SCHEMA,
        "project_id": PROJECT, "expected_source_digest": digest,
        "actions": actions, "offset": 0, "limit": 1,
    }
    typed = execute_dialogue_transcript_tool(request, authorized=True)
    assert main([
        "--project", PROJECT, "--dialogue-stage", "--dialogue-transcript",
        "--dialogue-actions", json.dumps(actions),
        "--dialogue-transcript-limit", "1",
        "--dialogue-expected-digest", digest,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_dialogue_transcript_tool({**request, "unexpected": 1},
                                         authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-transcript"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage", "--dialogue-transcript",
              "--dialogue-transcript-offset", "65"])
