"""Source-backed authored transcript and forged-save regressions."""
from dataclasses import replace
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import (
    start_walk, follow_walk_route, walk_action,
    export_walk_receipt, restore_walk_receipt,
)
from skeleton.ai.game_builder.studio_ecosystem_walk_story_transcript import (
    walk_story_transcript,
)
from skeleton.ai.game_builder.studio_ecosystem_walkable import playable_world_source

PROJECT = "studio_arena_fighting_glacial_fjord"


def test_original_scene_transcript_survives_source_bound_save_restore():
    docs = read_blueprint(PROJECT)
    original = start_walk(docs, authorized=True)
    before = walk_story_transcript(original, docs, authorized=True)
    assert before["completed_scene_count"] == 0
    approached, route = follow_walk_route(original, docs, authorized=True)
    assert route["after_session_digest"] == approached.digest
    choice = playable_world_source(docs)["stages"][0]["alternatives"][0]
    played = walk_action(approached, docs, action="choose",
                         value=choice, authorized=True)
    restored = restore_walk_receipt(
        docs, export_walk_receipt(played, docs, authorized=True),
        authorized=True,
    )
    transcript = walk_story_transcript(restored, docs, authorized=True)
    assert transcript == walk_story_transcript(played, docs, authorized=True)
    assert transcript["completed_scenes"][0]["selected_alternative"] == choice
    assert transcript["completed_scene_count"] == 1
    assert transcript["session_digest"] == played.digest
    assert transcript["transcript_digest"] != before["transcript_digest"]
    assert transcript["release_certified"] is False
    assert original.events == ()


def test_transcript_rejects_unauthorized_and_forged_history():
    docs = read_blueprint(PROJECT)
    original = start_walk(docs, authorized=True)
    with pytest.raises(PermissionError):
        walk_story_transcript(original, docs, authorized=False)
    with pytest.raises(StudioQuestError):
        walk_story_transcript(replace(original, scene_index=1), docs, authorized=True)
    with pytest.raises(StudioQuestError):
        walk_story_transcript(replace(original, source_digest="0" * 64),
                              docs, authorized=True)


@pytest.mark.parametrize("limit", [True, False, 0, 33, -1, "2", None])
def test_transcript_rejects_invalid_scene_limits(limit):
    docs = read_blueprint(PROJECT)
    with pytest.raises(StudioQuestError):
        walk_story_transcript(start_walk(docs, authorized=True), docs,
                              authorized=True, max_scenes=limit)
