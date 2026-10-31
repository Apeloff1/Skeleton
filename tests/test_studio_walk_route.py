"""Deterministic, bounded, source-verified authored marker navigation."""
from dataclasses import replace
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


def test_route_is_shortest_deterministic_and_playable(docs):
    start = replay.start_walk(docs, authorized=True)
    first = replay.walk_route_hint(start, docs, authorized=True)
    assert first["status"] == "ready"
    assert first["distance"] == len(first["moves"])
    assert first["distance"] == 5
    assert first == replay.walk_route_hint(start, docs, authorized=True)
    session = start
    for move in first["moves"]:
        session = replay.walk_action(session, docs, action="move", value=move,
                                     authorized=True)
    near = replay.walk_route_hint(session, docs, authorized=True)
    assert near["status"] == "already_near" and near["moves"] == []
    session = replay.walk_action(session, docs, action="choose", value="inspect",
                                 authorized=True)
    done = replay.walk_route_hint(session, docs, authorized=True)
    assert done["status"] == "completed" and done["scene_id"] is None
    assert done["release_certified"] is False


def test_route_denies_unauthorized_and_forged_session(docs):
    session = replay.start_walk(docs, authorized=True)
    with pytest.raises(PermissionError):
        replay.walk_route_hint(session, docs, authorized=False)
    with pytest.raises(StudioQuestError, match="authoritative replay"):
        replay.walk_route_hint(replace(session, position=(4, 4)), docs, authorized=True)


def test_locked_stage_does_not_expose_false_interaction_route(docs, monkeypatch):
    locked = dict(WORLD, stages=[dict(WORLD["stages"][0], prerequisites=["missing-stage"])])
    monkeypatch.setattr(replay, "playable_world_source", lambda _: locked)
    hint = replay.walk_route_hint(replay.start_walk(docs, authorized=True), docs,
                                  authorized=True)
    assert hint["status"] == "locked" and hint["moves"] == []
    assert hint["distance"] is None


def test_unreachable_route_is_explicit(docs, monkeypatch):
    isolated = dict(WORLD, maps=[["######", "#.####", "######", "#....#", "#....#", "######"]])
    monkeypatch.setattr(replay, "playable_world_source", lambda _: isolated)
    hint = replay.walk_route_hint(replay.start_walk(docs, authorized=True), docs,
                                  authorized=True)
    assert hint["status"] == "unreachable" and hint["moves"] == []


def test_route_grid_budget_and_malformed_map_fail_closed(docs, monkeypatch):
    huge = dict(WORLD, width=5000, height=5000)
    monkeypatch.setattr(replay, "playable_world_source", lambda _: huge)
    with pytest.raises(StudioQuestError, match="grid budget"):
        replay.walk_route_hint(replay.start_walk(docs, authorized=True), docs,
                               authorized=True)
    bad = dict(WORLD, maps=[["short"]])
    monkeypatch.setattr(replay, "playable_world_source", lambda _: bad)
    with pytest.raises(StudioQuestError, match="map"):
        replay.walk_route_hint(replay.start_walk(docs, authorized=True), docs,
                               authorized=True)


def test_canonical_cli_route_and_receipt_roundtrip(capsys):
    import json
    from scripts.studio_ecosystem_cli import main
    args = ["--project", "original-test-world", "--play-walk", "--walk-route"]
    assert main(args) == 0
    start = json.loads(capsys.readouterr().out)
    assert start["route"]["moves"] == ["right"]
    assert start["route"]["session_digest"] == start["receipt"]["session_digest"]
    assert start["route"]["release_certified"] is False
    assert main(args + ["--walk-receipt", json.dumps(start["receipt"]),
                        "--walk-events", '[["move","right"]]']) == 0
    next_state = json.loads(capsys.readouterr().out)
    assert next_state["route"]["status"] == "already_near"
    assert next_state["receipt"]["events"] == [["move", "right"]]


def test_cli_rejects_orphan_route_flag(capsys):
    from scripts.studio_ecosystem_cli import main
    with pytest.raises(SystemExit) as exc:
        main(["--project", "original-test-world", "--walk-route"])
    assert exc.value.code == 2
    assert "--play-walk" in capsys.readouterr().err
