"""Guided world traversal: actual route execution, authored choices and replay."""
import json

import pytest

from skeleton.ai.agents.jeeves.studio_walk_tool import (
    GUIDED_WALK_REQUEST_SCHEMA, execute_guided_walk_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_guided_walk import (
    GUIDED_WALK_SCHEMA, execute_guided_walk,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import (
    replay_walk, playable_world_source,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    session = replay_walk(docs, [], authorized=True)
    choice = playable_world_source(docs)["stages"][0]["alternatives"][0]
    return docs, session, choice


def test_guided_route_choice_and_full_history_replay():
    docs, initial, choice = fixture()
    unchanged = json.dumps(docs, sort_keys=True)
    final, result = execute_guided_walk(
        docs, [], authored_choices=[choice],
        expected_source_digest=initial.source_digest,
        expected_session_digest=initial.digest, authorized=True)
    assert result["schema"] == GUIDED_WALK_SCHEMA
    assert result["scene_count"] == 1
    assert final.scene_index == initial.scene_index + 1
    assert final.chosen[-1][1] == choice
    assert result["final_receipt"] == final.receipt()
    assert result["final_session_digest"] == final.digest
    assert replay_walk(docs, list(final.events), authorized=True) == final
    assert result["steps"][0]["after_session_digest"] == final.digest
    assert result["steps"][0]["choice_events"] == 1
    assert result["replay_verified"] and not result["release_certified"]
    assert json.dumps(docs, sort_keys=True) == unchanged
    assert (final, result) == execute_guided_walk(
        docs, [], authored_choices=[choice],
        expected_source_digest=initial.source_digest,
        expected_session_digest=initial.digest, authorized=True)


def test_resumed_session_is_leased_and_new_history_appended():
    docs, initial, choice = fixture()
    first, _ = execute_guided_walk(
        docs, [], authored_choices=[choice],
        expected_source_digest=initial.source_digest,
        expected_session_digest=initial.digest, authorized=True)
    next_choice = playable_world_source(docs)["stages"][1]["alternatives"][0]
    second, result = execute_guided_walk(
        docs, [list(event) for event in first.events],
        authored_choices=[next_choice],
        expected_source_digest=first.source_digest,
        expected_session_digest=first.digest, authorized=True)
    assert second.scene_index == first.scene_index + 1
    assert second.events[:len(first.events)] == first.events
    assert result["original_session_digest"] == first.digest


@pytest.mark.parametrize("override", [
    {"authored_choices": []},
    {"authored_choices": ["forged"]},
    {"authored_choices": ["x"] * 4},
    {"authored_choices": [True]},
    {"authored_choices": ["../escape"]},
    {"expected_source_digest": "0" * 64},
    {"expected_session_digest": "0" * 64},
    {"expected_session_digest": True},
    {"events": [["choose", "forged"]]},
])
def test_invalid_guided_walk_fails_closed(override):
    docs, initial, choice = fixture()
    kwargs = dict(authored_choices=[choice],
                  expected_source_digest=initial.source_digest,
                  expected_session_digest=initial.digest, authorized=True)
    kwargs.update(override)
    with pytest.raises(StudioQuestError):
        execute_guided_walk(docs, kwargs.pop("events", []), **kwargs)


def test_guided_walk_requires_operator_authority():
    docs, initial, choice = fixture()
    with pytest.raises(PermissionError):
        execute_guided_walk(
            docs, [], authored_choices=[choice],
            expected_source_digest=initial.source_digest,
            expected_session_digest=initial.digest, authorized=False)


def test_typed_jeeves_cli_parity_and_mode_guards(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, initial, choice = fixture()
    request = {"schema": GUIDED_WALK_REQUEST_SCHEMA,
               "project_id": PROJECT, "events": [],
               "authored_choices": [choice],
               "expected_source_digest": initial.source_digest,
               "expected_session_digest": initial.digest}
    typed = execute_guided_walk_tool(request, authorized=True)
    assert main(["--project", PROJECT, "--play-walk",
                 "--walk-guided-choices", json.dumps([choice]),
                 "--walk-guided-expected-session", initial.digest]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert cli["guided_tour"] == typed["detail"]
    assert cli["receipt"] == typed["detail"]["final_receipt"]
    with pytest.raises(StudioQuestError):
        execute_guided_walk_tool({**request, "forged": True}, authorized=True)
    with pytest.raises(PermissionError):
        execute_guided_walk_tool(request, authorized=False)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--walk-guided-choices", json.dumps([choice])])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--play-walk",
              "--walk-guided-choices", json.dumps([choice])])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--play-walk",
              "--walk-guided-choices", json.dumps([choice]),
              "--walk-guided-expected-session", initial.digest,
              "--walk-follow-route"])
