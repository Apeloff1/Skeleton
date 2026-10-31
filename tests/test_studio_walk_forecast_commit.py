"""Canonical forecast-to-committed-gameplay integration contracts."""
from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_replay as replay
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


WORLD = {
    "project_id": "commit-test", "source_digest": "f" * 64,
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


def test_commits_first_branch_with_replay_and_immutable_original(docs):
    start = replay.start_walk(docs, authorized=True)
    original = start.receipt()
    forecast = replay.walk_branch_forecast(start, docs, authorized=True)
    result, proof = replay.commit_walk_forecast_branch(start, docs, branch_index=0,
                                                       authorized=True)
    assert result.digest == forecast["branches"][0]["session_digest"]
    assert result.scene_index == 2
    assert len(result.chosen) == 2
    assert start.receipt() == original
    assert proof["forecast_digest"] == forecast["forecast_digest"]
    assert proof["committed_scenes"] == 2
    assert proof["committed_events"] == len(result.events)
    assert proof["release_certified"] is False
    assert replay.restore_walk_receipt(
        docs, replay.export_walk_receipt(result, docs, authorized=True),
        authorized=True,
    ) == result


def test_distinct_branches_are_deterministic_and_proven(docs):
    start = replay.start_walk(docs, authorized=True)
    first, proof = replay.commit_walk_forecast_branch(start, docs, branch_index=0,
                                                      authorized=True)
    assert (first, proof) == replay.commit_walk_forecast_branch(
        start, docs, branch_index=0, authorized=True)
    second, other = replay.commit_walk_forecast_branch(start, docs, branch_index=1,
                                                       authorized=True)
    assert first.digest != second.digest
    assert first.chosen != second.chosen
    assert proof["commit_digest"] != other["commit_digest"]
    assert proof["complete_enumeration"] is True


def test_depth_one_commits_partial_scene_not_completion(docs):
    start = replay.start_walk(docs, authorized=True)
    result, proof = replay.commit_walk_forecast_branch(
        start, docs, branch_index=0, depth=1, authorized=True)
    assert result.scene_index == 1
    assert proof["branch_status"] == "depth_limit"
    assert proof["committed_scenes"] == 1
    assert proof["native_genre_runtime_verified"] is False


@pytest.mark.parametrize("index", [-1, True, False, 1.0, "0", None, 999])
def test_invalid_index_fails_closed(docs, index):
    start = replay.start_walk(docs, authorized=True)
    with pytest.raises(StudioQuestError, match="branch index"):
        replay.commit_walk_forecast_branch(start, docs, branch_index=index,
                                           authorized=True)


def test_unauthorized_rejected_before_replay(docs, monkeypatch):
    start = replay.start_walk(docs, authorized=True)
    monkeypatch.setattr(replay, "walk_branch_forecast", lambda *a, **k: pytest.fail("replayed"))
    with pytest.raises(PermissionError):
        replay.commit_walk_forecast_branch(start, docs, branch_index=0,
                                           authorized=False)


def test_stale_or_forged_save_rejected(docs):
    start = replay.start_walk(docs, authorized=True)
    with pytest.raises(StudioQuestError, match="authoritative replay"):
        replay.commit_walk_forecast_branch(replace(start, position=(4, 4)), docs,
                                           branch_index=0, authorized=True)


def test_locked_and_unreachable_branches_have_no_actions(docs, monkeypatch):
    start = replay.start_walk(docs, authorized=True)
    for variant in (
        dict(WORLD, stages=[dict(WORLD["stages"][0], prerequisites=["missing"]),
                            WORLD["stages"][1]]),
        dict(WORLD, maps=[["######", "#.####", "######", "#....#", "#....#", "######"]] * 2),
    ):
        monkeypatch.setattr(replay, "playable_world_source", lambda _, w=variant: w)
        with pytest.raises(StudioQuestError, match="no executable"):
            replay.commit_walk_forecast_branch(start, docs, branch_index=0,
                                               authorized=True)


def test_replay_budget_rejected_atomically(docs, monkeypatch):
    start = replay.start_walk(docs, authorized=True)
    before = start.receipt()
    monkeypatch.setattr(replay, "MAX_WALK_EVENTS", 1)
    with pytest.raises(StudioQuestError, match="no executable"):
        replay.commit_walk_forecast_branch(start, docs, branch_index=0,
                                           authorized=True)
    assert start.receipt() == before


def test_source_changes_during_commit_fail_closed(docs, monkeypatch):
    start = replay.start_walk(docs, authorized=True)
    original = replay.playable_world_source
    count = 0

    def changing(source):
        nonlocal count
        count += 1
        world = original(source)
        return dict(world, source_digest="0" * 64) if count >= 12 else world

    monkeypatch.setattr(replay, "playable_world_source", changing)
    with pytest.raises(StudioQuestError, match="source|replay|proof|route"):
        replay.commit_walk_forecast_branch(start, docs, branch_index=0,
                                           authorized=True)


def test_cli_commit_save_and_resume(docs, monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    assert cli.main(["--project", "commit-test", "--play-walk",
                     "--walk-commit-forecast-branch", "0"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["receipt"]["scene_index"] == 2
    assert result["branch_execution"]["committed_scenes"] == 2
    assert result["branch_execution"]["release_certified"] is False


def test_cli_rejects_mode_confusion(docs, monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    for flags in (
        ["--walk-commit-forecast-branch", "0"],
        ["--play-walk", "--walk-commit-forecast-branch", "-1"],
        ["--play-walk", "--walk-commit-forecast-branch", "100"],
        ["--play-walk", "--walk-commit-forecast-branch", "0", "--walk-route"],
        ["--play-walk", "--walk-commit-forecast-branch", "0", "--walk-forecast-depth", "4"],
    ):
        with pytest.raises(SystemExit) as exc:
            cli.main(["--project", "commit-test", *flags])
        assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err
