"""Source-backed original canon journal, paging and drift regressions."""
from copy import deepcopy
from dataclasses import replace

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import (
    start_walk, follow_walk_route, walk_action, export_walk_receipt,
)
from skeleton.ai.game_builder.studio_ecosystem_walkable import playable_world_source
from skeleton.ai.game_builder.studio_ecosystem_walk_canon_journal import walk_canon_journal

PROJECT = "studio_arena_fighting_glacial_fjord"


def play_two(docs):
    session = start_walk(docs, authorized=True)
    for _ in range(2):
        session, _ = follow_walk_route(session, docs, authorized=True)
        stage = playable_world_source(docs)["stages"][session.scene_index]
        session = walk_action(session, docs, action="choose",
                              value=stage["alternatives"][0], authorized=True)
    return session


def test_canon_journal_source_and_played_choice_survive_save():
    docs = read_blueprint(PROJECT)
    session = play_two(docs)
    saved = export_walk_receipt(session, docs, authorized=True)
    journal = walk_canon_journal(session, docs, authorized=True, limit=1)
    assert journal["era"] == docs["narrative"]["foundation"]["era"]
    assert journal["protagonist"] == docs["cast"]["protagonist"]["name"]
    assert journal["scenes"][0]["site"] == docs["scene"]["episode_plan"][0]["site"]
    assert journal["scenes"][0]["selected_alternative"] == session.chosen[0][1]
    assert journal["authored_context_not_observed_consequence"] is True
    assert journal["next_offset"] == 1
    assert journal["release_certified"] is False
    page = walk_canon_journal(
        session, docs, authorized=True, offset=1, limit=1,
        expected_session_digest=journal["continuation_session_digest"],
        expected_source_digest=journal["continuation_source_digest"],
    )
    assert page["scenes"][0]["index"] == 1
    assert page["next_offset"] is None
    assert saved == export_walk_receipt(session, docs, authorized=True)
    assert journal == walk_canon_journal(session, docs, authorized=True, limit=1)


def test_canon_journal_rejects_forged_state_and_source_drift():
    docs = read_blueprint(PROJECT)
    session = play_two(docs)
    first = walk_canon_journal(session, docs, authorized=True, limit=1)
    with pytest.raises(PermissionError):
        walk_canon_journal(session, docs, authorized=False)
    with pytest.raises(StudioQuestError):
        walk_canon_journal(replace(session, scene_index=1), docs, authorized=True)
    with pytest.raises(StudioQuestError):
        walk_canon_journal(session, docs, authorized=True, offset=1, limit=1)
    changed = deepcopy(docs)
    changed["scene"]["episode_plan"][1]["site"] = "a different authored site"
    with pytest.raises(StudioQuestError):
        walk_canon_journal(
            session, changed, authorized=True, offset=1, limit=1,
            expected_session_digest=session.digest,
            expected_source_digest=first["journal_source_digest"],
        )
    changed = deepcopy(docs)
    changed["scene"]["episode_plan"][0]["dialogue_hook"] = "missing_cast_id"
    with pytest.raises(StudioQuestError):
        walk_canon_journal(session, changed, authorized=True)


@pytest.mark.parametrize("limit", [True, False, 0, 9, -1, "3", None])
def test_canon_journal_rejects_invalid_limits(limit):
    docs = read_blueprint(PROJECT)
    with pytest.raises(StudioQuestError):
        walk_canon_journal(start_walk(docs, authorized=True), docs,
                           authorized=True, limit=limit)
