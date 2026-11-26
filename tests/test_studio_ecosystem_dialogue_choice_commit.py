"""Canonical NPC dialogue preview -> choice commit -> save/replay parity."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_choice_preview import (
    preview_dialogue_choices,
)
from skeleton.ai.game_builder.studio_ecosystem_dialogue_choice_commit import (
    COMMIT_SCHEMA, commit_dialogue_choice,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_COMMIT_REQUEST_SCHEMA, execute_dialogue_commit_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def _preview():
    docs = read_blueprint(PROJECT)
    proof = audit_canon_source(docs, authorized=True)
    before = preview_dialogue_choices(
        docs, [], authorized=True, expected_source_digest=proof["source_digest"])
    return docs, proof["source_digest"], before["previews"][0]


def test_commit_replays_preview_and_roundtrips_source_bound_quest_receipt():
    docs, digest, choice = _preview()
    result = commit_dialogue_choice(
        docs, [], stage_id=choice["quest_stage"], alternative=choice["alternative"],
        expected_preview_digest=choice["preview_digest"],
        expected_source_digest=digest, authorized=True)
    assert result["schema"] == COMMIT_SCHEMA
    assert result["source_digest"] == digest
    assert result["session_digest"] == choice["after_session_digest"]
    assert result["quest_receipt"] == replay_quest(
        docs, [[choice["quest_stage"], choice["alternative"]]],
        authorized=True).receipt()
    assert result["staging_after"]["session_digest"] == result["session_digest"]
    assert result["choice_committed_to_receipt"] is True
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    assert result == commit_dialogue_choice(
        docs, [], stage_id=choice["quest_stage"], alternative=choice["alternative"],
        expected_preview_digest=choice["preview_digest"], authorized=True)


def test_forged_stale_locked_and_repeated_commit_rejected():
    docs, digest, choice = _preview()
    args = dict(stage_id=choice["quest_stage"], alternative=choice["alternative"],
                expected_preview_digest=choice["preview_digest"], authorized=True)
    with pytest.raises(PermissionError):
        commit_dialogue_choice(docs, [], **{**args, "authorized": False})
    with pytest.raises(StudioQuestError):
        commit_dialogue_choice(docs, [], **{**args, "expected_preview_digest": "0" * 64})
    with pytest.raises(StudioQuestError):
        commit_dialogue_choice(docs, [], **{**args, "expected_source_digest": "0" * 64})
    with pytest.raises(StudioQuestError):
        commit_dialogue_choice(docs, [], **{**args, "alternative": "invented"})
    with pytest.raises(StudioQuestError):
        commit_dialogue_choice(docs, [[choice["quest_stage"], choice["alternative"]]], **args)
    with pytest.raises(StudioQuestError):
        commit_dialogue_choice(docs, [], **{**args, "expected_preview_digest": "invalid"})
    assert digest == audit_canon_source(docs, authorized=True)["source_digest"]


def test_cli_and_typed_jeeves_commit_match(capsys):
    from scripts.studio_ecosystem_cli import main
    _, digest, choice = _preview()
    request = {
        "schema": DIALOGUE_COMMIT_REQUEST_SCHEMA,
        "project_id": PROJECT, "expected_source_digest": digest,
        "expected_preview_digest": choice["preview_digest"],
        "stage_id": choice["quest_stage"],
        "alternative": choice["alternative"], "actions": [],
    }
    typed = execute_dialogue_commit_tool(request, authorized=True)
    assert main([
        "--project", PROJECT, "--dialogue-stage", "--dialogue-commit",
        "--dialogue-choice-stage", choice["quest_stage"],
        "--dialogue-choice-alternative", choice["alternative"],
        "--dialogue-preview-digest", choice["preview_digest"],
        "--dialogue-expected-digest", digest,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_dialogue_commit_tool({**request, "unexpected": 1}, authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage", "--dialogue-commit"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage", "--dialogue-commit",
              "--dialogue-choice-stage", choice["quest_stage"],
              "--dialogue-choice-alternative", choice["alternative"],
              "--dialogue-preview-digest", "0" * 64])
