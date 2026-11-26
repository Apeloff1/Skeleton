"""Regression tests for bounded authoritative walk-event verification."""

from dataclasses import replace

import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_replay as replay
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


WORLD = {
    "project_id": "original-test-world",
    "source_digest": "a" * 64,
    "width": 4,
    "height": 4,
    "spawn": [1, 1],
    "target": [2, 1],
    "maps": [["####", "#..#", "#..#", "####"]],
    "stages": [{"id": "scene-one", "alternatives": ["inspect"],
                "prerequisites": []}],
}


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr(replay, "playable_world_source", lambda _: WORLD)
    return {}


def test_real_move_choice_and_replay_still_work(world):
    session = replay.start_walk(world, authorized=True)
    session = replay.walk_action(session, world, action="move",
                                 value="right", authorized=True)
    session = replay.walk_action(session, world, action="choose",
                                 value="inspect", authorized=True)
    assert session.scene_index == 1
    assert session.position == (1, 1)
    assert session.chosen == (("scene-one", "inspect"),)
    replay.verify_walk(session, world)
    assert replay.replay_walk(world, list(session.events), authorized=True) == session
    with pytest.raises(StudioQuestError, match="after authored game completion"):
        replay.walk_action(session, world, action="move", value="left", authorized=True)


def test_event_count_rejected_before_world_generation(monkeypatch):
    monkeypatch.setattr(replay, "playable_world_source",
                        lambda _: pytest.fail("untrusted oversized replay reached world builder"))
    events = [("move", "right")] * (replay.MAX_WALK_EVENTS + 1)
    with pytest.raises(StudioQuestError, match="event budget"):
        replay.replay_walk({}, events, authorized=True)


def test_per_event_bytes_and_invalid_unicode_fail_before_world(monkeypatch):
    monkeypatch.setattr(replay, "playable_world_source",
                        lambda _: pytest.fail("untrusted oversized replay reached world builder"))
    for event, message in [
        (("choose", "é" * (replay.MAX_WALK_EVENT_BYTES // 2 + 1)), "byte budget"),
        (("choose", "\ud800"), "noncanonical"),
        (("move", 1), "invalid walk event"),
    ]:
        with pytest.raises(StudioQuestError, match=message):
            replay.replay_walk({}, [event], authorized=True)


def test_aggregate_history_byte_limit_rejected_before_world(monkeypatch):
    monkeypatch.setattr(replay, "playable_world_source",
                        lambda _: pytest.fail("untrusted oversized replay reached world builder"))
    events = [("choose", "x" * replay.MAX_WALK_EVENT_BYTES)] * 257
    with pytest.raises(StudioQuestError, match="history byte budget"):
        replay.replay_walk({}, events, authorized=True)


def test_verify_and_action_share_admission_boundary(world):
    session = replay.start_walk(world, authorized=True)
    forged = replace(session, events=tuple([("move", "right")] * (replay.MAX_WALK_EVENTS + 1)))
    with pytest.raises(StudioQuestError, match="event budget"):
        replay.verify_walk(forged, world)
    with pytest.raises(StudioQuestError, match="event budget"):
        replay.walk_action(forged, world, action="move", value="right", authorized=True)
    with pytest.raises(PermissionError):
        replay.replay_walk(world, [("move", "right")] * (replay.MAX_WALK_EVENTS + 1),
                           authorized=False)
