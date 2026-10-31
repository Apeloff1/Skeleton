"""Bounded authoritative checkpoint timeline and operator restore contracts."""
from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_replay as walk
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


@pytest.fixture
def docs(monkeypatch):
    stages = [
        {"id": "oath", "scene_id": "oath_scene", "reward": "seal",
         "alternatives": ["promise", "refuse"], "prerequisites": []},
        {"id": "return", "scene_id": "return_scene", "reward": "compass",
         "alternatives": ["accept", "leave"], "prerequisites": ["oath"]},
    ]
    world = {
        "project_id": "timeline-world", "source_digest": "c" * 64,
        "width": 5, "height": 4, "spawn": [1, 1], "target": [2, 1],
        "maps": [["#####", "#...#", "#...#", "#####"]] * len(stages),
        "stages": stages,
    }
    monkeypatch.setattr(walk, "playable_world_source", lambda source: source["world"])
    return {"world": world}


def played(docs):
    return walk.replay_walk(docs, [
        ("move", "right"), ("choose", "promise"),
        ("move", "right"), ("choose", "accept"),
    ], authorized=True)


def test_timeline_reconstructs_genesis_and_authored_choices(docs):
    session = played(docs)
    original = session.receipt()
    timeline = walk.walk_checkpoint_timeline(session, docs, authorized=True)
    assert timeline["schema"].endswith("studio_walk_timeline.v1")
    assert timeline["total_choice_count"] == 2
    assert timeline["checkpoint_count"] == 3
    assert timeline["omitted_checkpoint_count"] == 0
    assert [c["checkpoint_index"] for c in timeline["checkpoints"]] == [0, 1, 2]
    assert [c["event_count"] for c in timeline["checkpoints"]] == [0, 2, 4]
    assert [c["completed_stage_id"] for c in timeline["checkpoints"]] == [None, "oath", "return"]
    assert timeline["checkpoints"][-1]["session_digest"] == session.digest
    assert timeline == walk.walk_checkpoint_timeline(session, docs, authorized=True)
    assert session.receipt() == original
    assert timeline["release_certified"] is False


def test_checkpoint_restore_can_continue_with_new_authored_choice(docs):
    session = played(docs)
    restored, receipt = walk.restore_walk_checkpoint(
        session, docs, checkpoint_index=1, authorized=True,
    )
    assert restored.events == (("move", "right"), ("choose", "promise"))
    assert restored.scene_index == 1
    assert receipt["discarded_event_count"] == 2
    assert receipt["checkpoint_digest"] == walk.walk_checkpoint_timeline(
        session, docs, authorized=True)["checkpoints"][1]["checkpoint_digest"]
    next_state = walk.replay_walk(docs, restored.events + (
        ("move", "right"), ("choose", "leave")), authorized=True)
    assert next_state.chosen[-1] == ("return", "leave")
    assert session.chosen[-1] == ("return", "accept")
    encoded = walk.export_walk_receipt(restored, docs, authorized=True)
    assert walk.restore_walk_receipt(docs, encoded, authorized=True) == restored


def test_restore_genesis_and_completed_checkpoint(docs):
    session = played(docs)
    for index in (0, 2):
        restored, audit = walk.restore_walk_checkpoint(
            session, docs, checkpoint_index=index, authorized=True)
        assert restored.scene_index == index
        assert audit["after_session_digest"] == restored.digest
        assert audit["restore_digest"] == walk.restore_walk_checkpoint(
            session, docs, checkpoint_index=index, authorized=True)[1]["restore_digest"]


@pytest.mark.parametrize("index", [-1, 3, True, False, None, "1", 1.0])
def test_invalid_checkpoint_index_fails_closed(docs, index):
    with pytest.raises(StudioQuestError):
        walk.restore_walk_checkpoint(played(docs), docs,
                                     checkpoint_index=index, authorized=True)


@pytest.mark.parametrize("field,value", [
    ("position", (2, 1)), ("source_digest", "0" * 64),
    ("digest", "forged"), ("scene_index", 0),
])
def test_timeline_rejects_forged_sessions(docs, field, value):
    forged = replace(played(docs), **{field: value})
    with pytest.raises(StudioQuestError):
        walk.walk_checkpoint_timeline(forged, docs, authorized=True)


def test_authorization_denied_before_source_read(docs, monkeypatch):
    session = played(docs)
    monkeypatch.setattr(walk, "playable_world_source", lambda _: pytest.fail("source read"))
    with pytest.raises(PermissionError):
        walk.walk_checkpoint_timeline(session, docs, authorized=False)
    with pytest.raises(PermissionError):
        walk.restore_walk_checkpoint(session, docs,
                                     checkpoint_index=0, authorized=False)


def test_source_drift_between_replays_fails_closed(docs, monkeypatch):
    session = played(docs)
    calls = 0
    def shifting(source):
        nonlocal calls
        calls += 1
        world = source["world"]
        return world if calls < 3 else {**world, "source_digest": "0" * 64}
    monkeypatch.setattr(walk, "playable_world_source", shifting)
    with pytest.raises(StudioQuestError):
        walk.walk_checkpoint_timeline(session, docs, authorized=True)


def test_bounded_timeline_paginates_without_fabricating_old_checkpoints(docs):
    world = docs["world"]
    world["stages"] = [
        {"id": f"chapter-{i}", "scene_id": f"scene-{i}", "reward": f"reward-{i}",
         "alternatives": ["continue"],
         "prerequisites": [f"chapter-{i-1}"] if i else []}
        for i in range(36)
    ]
    world["maps"] = world["maps"][:1] * 36
    events = [("move", "right"), ("choose", "continue")] * 36
    session = walk.replay_walk(docs, events, authorized=True)
    timeline = walk.walk_checkpoint_timeline(session, docs, authorized=True)
    assert timeline["checkpoint_count"] == 33
    assert timeline["omitted_checkpoint_count"] == 4
    assert timeline["checkpoints"][0]["checkpoint_index"] == 0
    assert timeline["checkpoints"][-1]["checkpoint_index"] == 36
    assert timeline["replay_work_events"] <= walk.MAX_WALK_TIMELINE_REPLAY_EVENTS
    with pytest.raises(StudioQuestError):
        walk.restore_walk_checkpoint(session, docs, checkpoint_index=1, authorized=True)


def test_cli_timeline_and_restore_roundtrip(docs, monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda project: docs)
    session = played(docs)
    raw = walk.export_walk_receipt(session, docs, authorized=True).decode("ascii")
    assert cli.main(["--project", "timeline-world", "--play-walk",
                     "--walk-receipt", raw, "--walk-timeline"]) == 0
    timeline = json.loads(capsys.readouterr().out)
    assert timeline["timeline"]["checkpoint_count"] == 3
    assert cli.main(["--project", "timeline-world", "--play-walk",
                     "--walk-receipt", raw, "--walk-restore-checkpoint", "1"]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["receipt"]["scene_index"] == 1
    assert restored["checkpoint_restore"]["checkpoint_index"] == 1
    assert cli.main(["--project", "timeline-world", "--play-walk",
                     "--walk-receipt", json.dumps(restored["receipt"]),
                     "--walk-events", '[["move","right"],["choose","leave"]]']) == 0
    assert json.loads(capsys.readouterr().out)["choices"][-1] == ["return", "leave"]


@pytest.mark.parametrize("flags", [
    ["--walk-timeline", "--walk-route"],
    ["--walk-restore-checkpoint", "0"],
    ["--walk-restore-checkpoint", "-1", "--walk-receipt", "{}"],
    ["--walk-restore-checkpoint", "1", "--walk-receipt", "{}", "--walk-events", "[]"],
])
def test_cli_invalid_modes_rejected_before_source_read(monkeypatch, flags):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: pytest.fail("source read"))
    with pytest.raises(SystemExit):
        cli.main(["--project", "timeline-world", "--play-walk", *flags])
