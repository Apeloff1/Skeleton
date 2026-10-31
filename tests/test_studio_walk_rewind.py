"""Source-bound rewind branches and CLI save continuation."""
from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_replay as walk
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


@pytest.fixture
def docs(monkeypatch):
    world = {
        "project_id": "rewind-authored-test", "source_digest": "b" * 64,
        "width": 6, "height": 5, "spawn": [1, 1], "target": [2, 1],
        "maps": [["######", "#....#", "#....#", "#....#", "######"]] * 2,
        "stages": [
            {"id": "origin", "scene_id": "scene_origin", "reward": "map",
             "alternatives": ["north", "south"], "prerequisites": []},
            {"id": "return", "scene_id": "scene_return", "reward": "key",
             "alternatives": ["finish", "wait"], "prerequisites": ["origin"]},
        ],
    }
    monkeypatch.setattr(walk, "playable_world_source", lambda source: source["world"])
    return {"world": world}


def played(docs):
    events = [("move", "right"), ("choose", "north"),
              ("move", "down"), ("move", "right"), ("choose", "finish")]
    return walk.replay_walk(docs, events, authorized=True)


def test_reopen_last_choice_preserves_position_and_allows_alternative(docs):
    original = played(docs)
    unchanged = original.receipt()
    reopened, audit = walk.rewind_walk_choices(original, docs, count=1, authorized=True)
    assert reopened.events == original.events[:4]
    assert reopened.position == (2, 2)
    assert reopened.scene_index == 1
    assert reopened.chosen == (("origin", "north"),)
    assert audit["removed_event_count"] == 1
    assert audit["reopened_stage_id"] == "return"
    assert audit["after_session_digest"] == reopened.digest
    assert audit["rewind_digest"] == walk.rewind_walk_choices(original, docs, count=1, authorized=True)[1]["rewind_digest"]
    alternate = walk.walk_action(reopened, docs, action="choose", value="wait", authorized=True)
    assert alternate.chosen[-1] == ("return", "wait")
    assert original.receipt() == unchanged
    assert audit["release_certified"] is False


def test_rewind_two_choices_retains_pre_choice_movement(docs):
    original = played(docs)
    reopened, audit = walk.rewind_walk_choices(original, docs, count=2, authorized=True)
    assert reopened.events == (("move", "right"),)
    assert reopened.position == (2, 1)
    assert reopened.scene_index == 0
    assert audit["removed_event_count"] == 4
    assert audit["removed_choices"] == [["origin", "north"], ["return", "finish"]]
    next_branch = walk.walk_action(reopened, docs, action="choose", value="south", authorized=True)
    assert next_branch.chosen == (("origin", "south"),)


@pytest.mark.parametrize("count", [True, 0, -1, 33, 1.5, "1", None, 3])
def test_invalid_counts_fail_closed(docs, count):
    with pytest.raises(StudioQuestError):
        walk.rewind_walk_choices(played(docs), docs, count=count, authorized=True)


def test_authorization_denied_before_source_access(docs, monkeypatch):
    session = played(docs)
    monkeypatch.setattr(walk, "playable_world_source", lambda _: pytest.fail("source access"))
    with pytest.raises(PermissionError):
        walk.rewind_walk_choices(session, docs, count=1, authorized=False)


@pytest.mark.parametrize("field,value", [
    ("position", (2, 1)), ("scene_index", 0), ("source_digest", "0" * 64),
    ("digest", "forged"),
])
def test_forged_save_rejected(docs, field, value):
    session = played(docs)
    with pytest.raises(StudioQuestError):
        walk.rewind_walk_choices(replace(session, **{field: value}), docs,
                                 count=1, authorized=True)


def test_source_drift_during_rewind_rejected(docs, monkeypatch):
    session = played(docs)
    calls = 0
    def shifting(source):
        nonlocal calls
        calls += 1
        if calls > 1:
            return {**source["world"], "source_digest": "0" * 64}
        return source["world"]
    monkeypatch.setattr(walk, "playable_world_source", shifting)
    with pytest.raises(StudioQuestError):
        walk.rewind_walk_choices(session, docs, count=1, authorized=True)


def test_cli_rewind_receipt_can_be_restored_and_replayed(docs, monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda project: docs)
    original = played(docs)
    raw = walk.export_walk_receipt(original, docs, authorized=True).decode("ascii")
    assert cli.main(["--project", "rewind-authored-test", "--play-walk",
                     "--walk-receipt", raw, "--walk-rewind-choices", "1"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["choice_rewind"]["reopened_stage_id"] == "return"
    assert output["receipt"]["scene_index"] == 1
    restored = walk.restore_walk_receipt(docs, json.dumps(output["receipt"]).encode(),
                                         authorized=True)
    assert restored.position == (2, 2)
    assert cli.main(["--project", "rewind-authored-test", "--play-walk",
                     "--walk-receipt", json.dumps(output["receipt"]),
                     "--walk-events", '[["choose","wait"]]']) == 0
    assert json.loads(capsys.readouterr().out)["choices"][-1] == ["return", "wait"]


@pytest.mark.parametrize("flags", [
    ["--walk-rewind-choices", "1"],
    ["--walk-rewind-choices", "0", "--walk-receipt", "{}"],
    ["--walk-rewind-choices", "1", "--walk-receipt", "{}", "--walk-events", "[]"],
    ["--walk-rewind-choices", "1", "--walk-receipt", "{}", "--walk-route"],
])
def test_cli_invalid_modes_fail_before_source_read(monkeypatch, flags):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: pytest.fail("source read"))
    with pytest.raises(SystemExit):
        cli.main(["--project", "rewind-authored-test", "--play-walk", *flags])
