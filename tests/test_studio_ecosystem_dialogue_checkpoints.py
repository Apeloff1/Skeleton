"""Canonical NPC checkpoint timeline: replay, paging, guards, CLI/Jeeves parity."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_choice_preview import (
    preview_dialogue_choices,
)
from skeleton.ai.game_builder.studio_ecosystem_dialogue_checkpoints import (
    CHECKPOINTS_SCHEMA, page_dialogue_checkpoints,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_CHECKPOINT_REQUEST_SCHEMA, execute_dialogue_checkpoint_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def _fixture():
    docs = read_blueprint(PROJECT)
    previews = preview_dialogue_choices(docs, [], authorized=True)["previews"]
    assert previews
    actions = [[previews[0]["quest_stage"], previews[0]["alternative"]]]
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    session = replay_quest(docs, actions, authorized=True)
    return docs, actions, source, session.digest


def test_checkpoint_zero_and_choice_prefix_replay_are_exact():
    docs, actions, source, lease = _fixture()
    result = page_dialogue_checkpoints(
        docs, actions, authorized=True,
        expected_source_digest=source, expected_session_digest=lease)
    assert result["schema"] == CHECKPOINTS_SCHEMA
    assert result["total_checkpoints"] == 2
    assert result["next_offset"] is None
    assert result["entries"][0]["quest_receipt"]["choices"] == []
    assert result["entries"][1]["quest_receipt"]["choices"] == actions
    assert result["entries"][1]["previous_stage"] == actions[0][0]
    assert result["entries"][1]["previous_alternative"] == actions[0][1]
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    assert result == page_dialogue_checkpoints(
        docs, actions, authorized=True,
        expected_source_digest=source, expected_session_digest=lease)


def test_pagination_reconstructs_same_receipts_without_mutation():
    docs, actions, source, lease = _fixture()
    original = json.dumps(actions)
    first = page_dialogue_checkpoints(
        docs, actions, authorized=True, limit=1)
    second = page_dialogue_checkpoints(
        docs, actions, authorized=True, offset=first["next_offset"],
        limit=1, expected_session_digest=lease)
    assert first["next_offset"] == 1
    assert second["next_offset"] is None
    assert [e["checkpoint_index"] for e in first["entries"] + second["entries"]] == [0, 1]
    assert json.dumps(actions) == original


@pytest.mark.parametrize("kwargs", [
    {"offset": -1}, {"offset": 2}, {"offset": True},
    {"limit": 0}, {"limit": 9}, {"limit": True},
    {"expected_source_digest": "0" * 64},
    {"expected_session_digest": "0" * 64},
])
def test_checkpoint_invalid_bounds_and_stale_leases_fail_closed(kwargs):
    docs, actions, source, lease = _fixture()
    with pytest.raises(StudioQuestError):
        page_dialogue_checkpoints(docs, actions, authorized=True, **kwargs)


def test_unauthorized_and_forged_histories_are_rejected():
    docs, actions, source, lease = _fixture()
    with pytest.raises(PermissionError):
        page_dialogue_checkpoints(docs, actions, authorized=False)
    with pytest.raises(StudioQuestError):
        page_dialogue_checkpoints(
            docs, [["forged", "win"]], authorized=True)


def test_typed_jeeves_cli_checkpoint_page_parity(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, actions, source, lease = _fixture()
    request = {
        "schema": DIALOGUE_CHECKPOINT_REQUEST_SCHEMA,
        "project_id": PROJECT, "expected_source_digest": source,
        "expected_session_digest": lease, "actions": actions,
        "offset": 0, "limit": 1,
    }
    typed = execute_dialogue_checkpoint_tool(request, authorized=True)
    assert main([
        "--project", PROJECT, "--dialogue-stage",
        "--dialogue-actions", json.dumps(actions),
        "--dialogue-checkpoints", "--dialogue-checkpoint-limit", "1",
        "--dialogue-checkpoint-expected-session", lease,
        "--dialogue-expected-digest", source,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_dialogue_checkpoint_tool({**request, "extra": True},
                                         authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-checkpoint-offset", "1"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-checkpoints"])
