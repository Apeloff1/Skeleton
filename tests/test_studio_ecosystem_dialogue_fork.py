"""End-to-end canonical NPC checkpoint branching and abuse regression."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_choice_preview import (
    preview_dialogue_choices,
)
from skeleton.ai.game_builder.studio_ecosystem_dialogue_fork import (
    FORK_SCHEMA, fork_dialogue_history,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_FORK_REQUEST_SCHEMA, execute_dialogue_fork_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def _fixture():
    docs = read_blueprint(PROJECT)
    choices = preview_dialogue_choices(docs, [], authorized=True)["previews"]
    assert len(choices) >= 2
    original = [[choices[0]["quest_stage"], choices[0]["alternative"]]]
    replacement = choices[1]["alternative"]
    assert choices[1]["quest_stage"] == choices[0]["quest_stage"]
    assert replacement != original[0][1]
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    lease = replay_quest(docs, original, authorized=True).digest
    return docs, original, replacement, source, lease


def test_fork_replays_alternative_without_modifying_original_history():
    docs, original, alternative, source, lease = _fixture()
    snapshot = json.dumps(original)
    result = fork_dialogue_history(
        docs, original, checkpoint_index=0, alternative=alternative,
        expected_session_digest=lease, expected_source_digest=source,
        authorized=True)
    assert result["schema"] == FORK_SCHEMA
    assert result["original_session_digest"] == lease
    assert result["forked_receipt"]["choices"] == [[original[0][0], alternative]]
    assert result["comparison"]["first_divergence_index"] == 0
    assert result["staging_after"]["session_digest"] == result["session_digest"]
    assert result["progress"]["session_digest"] == result["session_digest"]
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    assert json.dumps(original) == snapshot
    assert result == fork_dialogue_history(
        docs, original, checkpoint_index=0, alternative=alternative,
        expected_session_digest=lease, expected_source_digest=source,
        authorized=True)


def test_suffix_is_explicitly_discarded_or_replayed_without_partial_mutation():
    docs, original, alternative, source, _ = _fixture()
    next_choices = preview_dialogue_choices(
        docs, original, authorized=True)["previews"]
    assert next_choices
    original.append([next_choices[0]["quest_stage"], next_choices[0]["alternative"]])
    lease = replay_quest(docs, original, authorized=True).digest
    dropped = fork_dialogue_history(
        docs, original, checkpoint_index=0, alternative=alternative,
        expected_session_digest=lease, expected_source_digest=source,
        authorized=True)
    assert dropped["discarded_suffix"] == original[1:]
    assert len(dropped["forked_receipt"]["choices"]) == 1
    kept = fork_dialogue_history(
        docs, original, checkpoint_index=0, alternative=alternative,
        expected_session_digest=lease, expected_source_digest=source,
        preserve_suffix=True, authorized=True)
    assert kept["preserved_suffix"] == original[1:]
    assert kept["discarded_suffix"] == []
    assert len(kept["forked_receipt"]["choices"]) == 2
    assert original[0][1] != kept["forked_receipt"]["choices"][0][1]


@pytest.mark.parametrize("overrides", [
    {"checkpoint_index": -1}, {"checkpoint_index": True},
    {"checkpoint_index": 1}, {"alternative": "forged"},
    {"expected_session_digest": "0" * 64},
    {"expected_source_digest": "0" * 64},
    {"preserve_suffix": 1},
])
def test_invalid_checkpoint_or_forged_lease_is_rejected(overrides):
    docs, original, alternative, source, lease = _fixture()
    kwargs = dict(checkpoint_index=0, alternative=alternative,
                  expected_session_digest=lease, expected_source_digest=source,
                  preserve_suffix=False, authorized=True)
    kwargs.update(overrides)
    with pytest.raises(StudioQuestError):
        fork_dialogue_history(docs, original, **kwargs)


def test_noop_and_unauthorized_fork_fail_closed():
    docs, original, alternative, source, lease = _fixture()
    with pytest.raises(StudioQuestError):
        fork_dialogue_history(
            docs, original, checkpoint_index=0, alternative=original[0][1],
            expected_session_digest=lease, authorized=True)
    with pytest.raises(PermissionError):
        fork_dialogue_history(
            docs, original, checkpoint_index=0, alternative=alternative,
            expected_session_digest=lease, authorized=False)


def test_cli_and_typed_jeeves_fork_have_identical_canonical_detail(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, original, alternative, source, lease = _fixture()
    request = {
        "schema": DIALOGUE_FORK_REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "expected_session_digest": lease,
        "actions": original, "checkpoint_index": 0,
        "alternative": alternative,
    }
    typed = execute_dialogue_fork_tool(request, authorized=True)
    assert main([
        "--project", PROJECT, "--dialogue-stage",
        "--dialogue-actions", json.dumps(original),
        "--dialogue-fork-index", "0",
        "--dialogue-fork-alternative", alternative,
        "--dialogue-fork-expected-session", lease,
        "--dialogue-expected-digest", source,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(PermissionError):
        execute_dialogue_fork_tool(request, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_dialogue_fork_tool({**request, "unknown": True}, authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-fork-index", "0"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-fork-index", "0"])
