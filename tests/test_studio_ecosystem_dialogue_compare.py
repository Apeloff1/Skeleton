"""Canonical original NPC dialogue branching comparisons and abuse cases."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_choice_preview import (
    preview_dialogue_choices,
)
from skeleton.ai.game_builder.studio_ecosystem_dialogue_compare import (
    COMPARE_SCHEMA, compare_dialogue_histories,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_COMPARE_REQUEST_SCHEMA, execute_dialogue_compare_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def _histories():
    docs = read_blueprint(PROJECT)
    alternatives = preview_dialogue_choices(docs, [], authorized=True)["previews"]
    assert len(alternatives) >= 2
    left = [[alternatives[0]["quest_stage"], alternatives[0]["alternative"]]]
    right = [[alternatives[1]["quest_stage"], alternatives[1]["alternative"]]]
    return docs, left, right


def test_branch_comparison_is_source_verified_and_deterministic():
    docs, left, right = _histories()
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    result = compare_dialogue_histories(
        docs, left, right, authorized=True, expected_source_digest=digest)
    assert result["schema"] == COMPARE_SCHEMA
    assert result["common_choice_prefix"] == 0
    assert result["first_divergence_index"] == 0
    assert result["left_suffix"] == left
    assert result["right_suffix"] == right
    assert result["identical_history"] is False
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    assert result == compare_dialogue_histories(
        docs, left, right, authorized=True, expected_source_digest=digest)
    same = compare_dialogue_histories(docs, left, left, authorized=True)
    assert same["identical_history"] is True
    assert same["first_divergence_index"] is None
    assert same["scene_changes"] == []


def test_branch_comparison_fails_closed_on_stale_or_illegal_history():
    docs, left, right = _histories()
    with pytest.raises(PermissionError):
        compare_dialogue_histories(docs, left, right, authorized=False)
    with pytest.raises(StudioQuestError):
        compare_dialogue_histories(docs, left, right, authorized=True,
                                   expected_source_digest="0" * 64)
    with pytest.raises(StudioQuestError):
        compare_dialogue_histories(docs, left, [["forged", "win"]],
                                   authorized=True)
    with pytest.raises(StudioQuestError):
        compare_dialogue_histories(docs, left, right, authorized=True,
                                   scene_id="absent")


def test_cli_and_typed_jeeves_comparison_parity(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, left, right = _histories()
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    request = {
        "schema": DIALOGUE_COMPARE_REQUEST_SCHEMA,
        "project_id": PROJECT, "expected_source_digest": digest,
        "actions": left, "compare_actions": right,
    }
    typed = execute_dialogue_compare_tool(request, authorized=True)
    assert main([
        "--project", PROJECT, "--dialogue-stage",
        "--dialogue-actions", json.dumps(left),
        "--dialogue-compare-actions", json.dumps(right),
        "--dialogue-expected-digest", digest,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_dialogue_compare_tool({**request, "unknown": 1},
                                      authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-compare-actions", "[]"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-compare-actions", '{"x":1,"x":2}'])
