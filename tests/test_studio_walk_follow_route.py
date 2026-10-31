"""Source-bound route execution never grants choices, skips budgets or trusts saves."""
from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_replay as replay
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


WORLD = {
    "project_id": "route-test", "source_digest": "a" * 64,
    "width": 6, "height": 6, "spawn": [1, 1], "target": [4, 4],
    "maps": [["######", "#...##", "###..#", "#....#", "#....#", "######"]],
    "stages": [{"id": "marker", "alternatives": ["inspect"], "prerequisites": []}],
}


@pytest.fixture
def docs(monkeypatch):
    monkeypatch.setattr(replay, "playable_world_source", lambda _: WORLD)
    return {}


def test_follow_route_reaches_marker_without_forging_choice(docs):
    start = replay.start_walk(docs, authorized=True)
    after, proof = replay.follow_walk_route(start, docs, authorized=True)
    assert after.scene_index == 0 and after.chosen == ()
    assert proof["steps"] == 5 and proof["choice_executed"] is False
    assert proof["before_session_digest"] == start.digest
    assert proof["after_session_digest"] == after.digest
    assert proof["route_digest"] == replay.walk_route_hint(start, docs, authorized=True)["route_digest"]
    assert replay.walk_route_hint(after, docs, authorized=True)["status"] == "already_near"
    assert proof["release_certified"] is False
    assert (after, proof) == replay.follow_walk_route(start, docs, authorized=True)
    assert replay.restore_walk_receipt(docs, replay.export_walk_receipt(after, docs, authorized=True),
                                       authorized=True) == after
    finished = replay.walk_action(after, docs, action="choose", value="inspect", authorized=True)
    assert finished.scene_index == 1


def test_already_near_is_idempotent_and_carries_zero_moves(docs):
    start = replay.start_walk(docs, authorized=True)
    near, _ = replay.follow_walk_route(start, docs, authorized=True)
    same, proof = replay.follow_walk_route(near, docs, authorized=True)
    assert same == near and proof["steps"] == 0 and proof["moves"] == []


def test_authorization_and_forged_position_rejected(docs):
    start = replay.start_walk(docs, authorized=True)
    with pytest.raises(PermissionError):
        replay.follow_walk_route(start, docs, authorized=False)
    with pytest.raises(StudioQuestError, match="authoritative replay"):
        replay.follow_walk_route(replace(start, position=(4, 4)), docs, authorized=True)


@pytest.mark.parametrize("status", ["locked", "unreachable", "completed"])
def test_nonready_routes_never_return_new_receipts(docs, monkeypatch, status):
    start = replay.start_walk(docs, authorized=True)
    if status == "completed":
        near, _ = replay.follow_walk_route(start, docs, authorized=True)
        start = replay.walk_action(near, docs, action="choose", value="inspect", authorized=True)
    elif status == "locked":
        monkeypatch.setattr(replay, "playable_world_source", lambda _:
                            dict(WORLD, stages=[dict(WORLD["stages"][0], prerequisites=["missing"])]))
        start = replay.start_walk(docs, authorized=True)
    else:
        monkeypatch.setattr(replay, "playable_world_source", lambda _:
                            dict(WORLD, maps=[["######", "#.####", "######", "#....#", "#....#", "######"]]))
        start = replay.start_walk(docs, authorized=True)
    with pytest.raises(StudioQuestError, match="cannot execute"):
        replay.follow_walk_route(start, docs, authorized=True)


def test_route_rejected_when_event_budget_exhausted(docs, monkeypatch):
    start = replay.start_walk(docs, authorized=True)
    monkeypatch.setattr(replay, "MAX_WALK_EVENTS", 4)
    with pytest.raises(StudioQuestError, match="event budget"):
        replay.follow_walk_route(start, docs, authorized=True)


def test_source_mutation_during_replay_fails_closed(docs, monkeypatch):
    start = replay.start_walk(docs, authorized=True)
    original = replay.playable_world_source
    calls = 0
    def mutate_after_hint(source):
        nonlocal calls
        calls += 1
        world = original(source)
        return dict(world, source_digest="b" * 64) if calls >= 3 else world
    monkeypatch.setattr(replay, "playable_world_source", mutate_after_hint)
    with pytest.raises(StudioQuestError, match="changed source"):
        replay.follow_walk_route(start, docs, authorized=True)


def test_cli_follow_route_and_resume_are_source_bound(capsys):
    from scripts.studio_ecosystem_cli import main
    project = "original-test-world"
    assert main(["--project", project, "--play-walk", "--walk-follow-route"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["route_execution"]["steps"] == 1
    assert payload["receipt"]["events"] == [["move", "right"]]
    assert payload["receipt"]["choices"] == []
    assert main(["--project", project, "--play-walk", "--walk-receipt",
                 json.dumps(payload["receipt"]), "--walk-follow-route"]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["route_execution"]["steps"] == 0
    assert resumed["receipt"] == payload["receipt"]


def test_cli_follow_route_rejects_mode_confusion(capsys):
    from scripts.studio_ecosystem_cli import main
    for argv in (["--project", "original-test-world", "--walk-follow-route"],
                 ["--project", "original-test-world", "--play-walk", "--walk-route", "--walk-follow-route"],
                 ["--project", "original-test-world", "--play-quest", "--walk-follow-route"]):
        with pytest.raises(SystemExit) as error:
            main(argv)
        assert error.value.code == 2
    assert "error:" in capsys.readouterr().err
