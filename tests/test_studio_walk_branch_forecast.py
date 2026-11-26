"""Bounded multi-scene forecasts use real authoritative movement and choices."""
from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_replay as replay
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


WORLD = {
    "project_id": "forecast-test", "source_digest": "f" * 64,
    "width": 6, "height": 6, "spawn": [1, 1], "target": [4, 4],
    "maps": [["######", "#...##", "###..#", "#....#", "#....#", "######"]] * 2,
    "stages": [
        {"id": "prologue", "alternatives": ["investigate", "depart"], "prerequisites": []},
        {"id": "aftermath", "alternatives": ["accept"], "prerequisites": ["prologue"]},
    ],
}


@pytest.fixture
def docs(monkeypatch):
    monkeypatch.setattr(replay, "playable_world_source", lambda _: WORLD)
    return {}


def test_forecast_is_deterministic_and_nonmutating(docs):
    start = replay.start_walk(docs, authorized=True)
    before = start.receipt()
    forecast = replay.walk_branch_forecast(start, docs, authorized=True)
    assert forecast == replay.walk_branch_forecast(start, docs, authorized=True)
    assert start.receipt() == before
    assert forecast["complete_enumeration"] is True
    assert forecast["nodes_examined"] == 5
    assert len(forecast["branches"]) == 2
    assert all(b["status"] == "sandbox_complete" for b in forecast["branches"])
    assert all(len(b["steps"]) == 2 for b in forecast["branches"])
    assert forecast["native_genre_runtime_verified"] is False
    assert forecast["release_certified"] is False
    for branch in forecast["branches"]:
        current = start
        for step in branch["steps"]:
            assert step["before_session_digest"] == current.digest
            for direction in step["route_moves"]:
                current = replay.walk_action(current, docs, action="move",
                                             value=direction, authorized=True)
            current = replay.walk_action(current, docs, action="choose",
                                         value=step["alternative"], authorized=True)
            assert step["after_session_digest"] == current.digest
        assert current.digest == branch["session_digest"]


def test_depth_one_is_explicitly_partial_without_false_completion(docs):
    start = replay.start_walk(docs, authorized=True)
    forecast = replay.walk_branch_forecast(start, docs, depth=1, authorized=True)
    assert forecast["complete_enumeration"] is True
    assert len(forecast["branches"]) == 2
    assert {b["status"] for b in forecast["branches"]} == {"depth_limit"}
    assert all(b["scene_index"] == 1 for b in forecast["branches"])


def test_denies_unauthorized_forged_and_invalid_depth(docs):
    start = replay.start_walk(docs, authorized=True)
    with pytest.raises(PermissionError):
        replay.walk_branch_forecast(start, docs, authorized=False)
    with pytest.raises(StudioQuestError, match="authoritative replay"):
        replay.walk_branch_forecast(replace(start, position=(4, 4)), docs,
                                    authorized=True)
    for depth in (True, 0, 4, -1, 1.5, "2"):
        with pytest.raises(StudioQuestError, match="depth"):
            replay.walk_branch_forecast(start, docs, depth=depth, authorized=True)


def test_locked_unreachable_and_event_exhaustion_are_explicit(docs, monkeypatch):
    start = replay.start_walk(docs, authorized=True)
    locked = dict(WORLD, stages=[dict(WORLD["stages"][0], prerequisites=["unknown"]),
                                 WORLD["stages"][1]])
    monkeypatch.setattr(replay, "playable_world_source", lambda _: locked)
    assert replay.walk_branch_forecast(start, docs, authorized=True)["branches"][0]["status"] == "locked"
    isolated = dict(WORLD, maps=[["######", "#.####", "######", "#....#", "#....#", "######"]] * 2)
    monkeypatch.setattr(replay, "playable_world_source", lambda _: isolated)
    assert replay.walk_branch_forecast(start, docs, authorized=True)["branches"][0]["status"] == "unreachable"
    monkeypatch.setattr(replay, "playable_world_source", lambda _: WORLD)
    monkeypatch.setattr(replay, "MAX_WALK_EVENTS", 1)
    assert replay.walk_branch_forecast(start, docs, authorized=True)["branches"][0]["status"] == "budget_exhausted"


def test_branch_budget_discloses_truncation(docs, monkeypatch):
    wide = dict(WORLD, stages=[dict(s, alternatives=[f"option-{i}" for i in range(8)])
                                for s in WORLD["stages"]])
    monkeypatch.setattr(replay, "playable_world_source", lambda _: wide)
    start = replay.start_walk(docs, authorized=True)
    forecast = replay.walk_branch_forecast(start, docs, authorized=True)
    assert forecast["complete_enumeration"] is False
    assert forecast["nodes_examined"] == replay.MAX_WALK_FORECAST_NODES
    assert len(forecast["branches"]) <= replay.MAX_WALK_FORECAST_NODES
    assert forecast == replay.walk_branch_forecast(start, docs, authorized=True)


def test_source_drift_during_branch_simulation_fails_closed(docs, monkeypatch):
    start = replay.start_walk(docs, authorized=True)
    original = replay.playable_world_source
    count = 0
    def switching(source):
        nonlocal count
        count += 1
        world = original(source)
        return dict(world, source_digest="0" * 64) if count >= 4 else world
    monkeypatch.setattr(replay, "playable_world_source", switching)
    with pytest.raises(StudioQuestError, match="changed authoritative source|authoritative replay"):
        replay.walk_branch_forecast(start, docs, authorized=True)


def test_cli_forecast_preserves_receipt_and_rejects_mode_confusion(docs, monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    start = replay.start_walk(docs, authorized=True)
    assert cli.main(["--project", "forecast-test", "--play-walk", "--walk-forecast",
                     "--walk-forecast-depth", "1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["receipt"] == start.receipt()
    assert result["branch_forecast"]["depth"] == 1
    for flags in (["--walk-forecast"],
                  ["--play-walk", "--walk-forecast-depth", "3"],
                  ["--play-walk", "--walk-forecast-depth", "2"],
                  ["--play-walk", "--walk-forecast", "--walk-route"],
                  ["--play-walk", "--walk-forecast", "--walk-forecast-depth", "4"]):
        with pytest.raises(SystemExit) as exc:
            cli.main(["--project", "forecast-test", *flags])
        assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err
