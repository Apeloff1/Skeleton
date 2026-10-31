"""Source-bound read-only divergence receipts for authored walk histories."""
from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_replay as walk
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


WORLD = {
    "project_id": "divergence-test", "source_digest": "d" * 64,
    "width": 6, "height": 5, "spawn": [2, 2], "target": [4, 2],
    "maps": [["######", "#....#", "#....#", "#....#", "######"]] * 2,
    "stages": [
        {"id": "arrival", "alternatives": ["investigate", "depart"], "prerequisites": []},
        {"id": "aftermath", "alternatives": ["accept"], "prerequisites": ["arrival"]},
    ],
}


@pytest.fixture
def docs(monkeypatch):
    monkeypatch.setattr(walk, "playable_world_source", lambda _: WORLD)
    return {"world": WORLD}


def _play(docs, *events):
    return walk.replay_walk(docs, list(events), authorized=True)


def _compare(docs, current, alternative):
    return walk.compare_walk_sessions(current, alternative, docs, authorized=True)


def test_identical_sessions_have_stable_digest_and_no_divergence(docs):
    current = _play(docs, ("move", "right"))
    before = current.receipt()
    report = _compare(docs, current, current)
    assert report == _compare(docs, current, current)
    assert report["relation"] == "identical"
    assert report["shared_event_count"] == 1
    assert report["first_difference_index"] is None
    assert report["current_next_event"] is None
    assert report["alternative_next_event"] is None
    assert report["same_authored_choices"] is True
    assert report["comparison_digest"] == walk._sha({
        k: v for k, v in report.items() if k != "comparison_digest"})
    assert current.receipt() == before
    assert report["release_certified"] is False


def test_current_prefix_and_reverse_extension(docs):
    start = _play(docs)
    moved = _play(docs, ("move", "right"))
    forward = _compare(docs, start, moved)
    reverse = _compare(docs, moved, start)
    assert forward["relation"] == "current_prefix"
    assert reverse["relation"] == "alternative_prefix"
    assert forward["first_difference_index"] == 0
    assert forward["current_next_event"] is None
    assert forward["alternative_next_event"] == ["move", "right"]
    assert reverse["current_next_event"] == ["move", "right"]
    assert reverse["alternative_next_event"] is None
    assert forward["same_authored_choices"] is True


def test_movement_fork_does_not_claim_story_choice_fork(docs):
    left = _play(docs, ("move", "left"))
    right = _play(docs, ("move", "right"))
    report = _compare(docs, left, right)
    assert report["relation"] == "fork"
    assert report["shared_event_count"] == 0
    assert report["current_next_event"] == ["move", "left"]
    assert report["alternative_next_event"] == ["move", "right"]
    assert report["same_authored_choices"] is True
    assert report["choice_fork"] is False
    assert report["current_position"] != report["alternative_position"]


def test_authored_choice_fork_is_explicit_and_deterministic(docs):
    first = _play(docs, ("move", "right"), ("choose", "investigate"))
    second = _play(docs, ("move", "right"), ("choose", "depart"))
    report = _compare(docs, first, second)
    assert report["relation"] == "fork"
    assert report["shared_event_count"] == 1
    assert report["shared_choice_count"] == 0
    assert report["choice_fork"] is True
    assert report["same_authored_choices"] is False
    assert report["current_completed_stages"] == 1
    assert report["alternative_completed_stages"] == 1
    assert first.digest != second.digest
    assert first.events == (("move", "right"), ("choose", "investigate"))


def test_shared_choice_prefix_not_misclassified_as_choice_fork(docs):
    first = _play(docs, ("move", "right"), ("choose", "investigate"))
    second = _play(docs, ("move", "right"), ("choose", "investigate"),
                   ("move", "right"), ("choose", "accept"))
    report = _compare(docs, first, second)
    assert report["relation"] == "current_prefix"
    assert report["shared_choice_count"] == 1
    assert report["choice_fork"] is False
    assert report["same_authored_choices"] is False
    assert report["alternative_completed_stages"] == 2


def test_authorization_denied_before_source_access(monkeypatch, docs):
    monkeypatch.setattr(walk, "playable_world_source", lambda _: pytest.fail("source read"))
    with pytest.raises(PermissionError):
        walk.compare_walk_sessions(None, None, docs, authorized=False)


@pytest.mark.parametrize("field,value", [
    ("position", (4, 4)), ("scene_index", 1),
    ("source_digest", "0" * 64), ("digest", "forged"),
])
def test_forged_current_or_alternative_rejected(docs, field, value):
    valid = _play(docs)
    forged = replace(valid, **{field: value})
    for a, b in ((forged, valid), (valid, forged)):
        with pytest.raises(StudioQuestError):
            _compare(docs, a, b)


def test_source_drift_rejected_without_false_receipt(docs):
    first = _play(docs)
    WORLD["source_digest"] = "e" * 64
    try:
        with pytest.raises(StudioQuestError):
            _compare(docs, first, first)
    finally:
        WORLD["source_digest"] = "d" * 64


def test_cli_compare_is_nonmutating_and_can_resume(capsys, monkeypatch, docs):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    args = ["--project", "divergence-test", "--play-walk"]
    assert cli.main([*args, "--walk-events", '[["move","right"]]']) == 0
    current = json.loads(capsys.readouterr().out)
    assert cli.main([*args, "--walk-receipt", json.dumps(current),
                     "--walk-compare-events", '[["move","left"]]']) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["receipt"] == current
    assert output["comparison"]["relation"] == "fork"
    assert output["comparison"]["current_session_digest"] == current["session_digest"]
    assert output["comparison"]["release_certified"] is False


def test_cli_invalid_comparison_rejected_before_source_read(monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: pytest.fail("source read"))
    args = ["--project", "divergence-test", "--play-walk", "--walk-compare-events"]
    for invalid in ('[["move",NaN]]', '[["move",true]]', '{"move":"right"}',
                    '[["move","right"]] ' * (walk.MAX_WALK_RECEIPT_BYTES // 20)):
        with pytest.raises(SystemExit) as exc:
            cli.main([*args, invalid])
        assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_rejects_ambiguous_modes_and_orphan_flag(capsys):
    from scripts import studio_ecosystem_cli as cli
    for flags in (
        ["--walk-compare-events", "[]"],
        ["--play-walk", "--walk-compare-events", "[]", "--walk-route"],
        ["--play-walk", "--walk-compare-events", "[]", "--walk-continuity"],
        ["--play-walk", "--walk-compare-events", "[]", "--walk-follow-route"],
    ):
        with pytest.raises(SystemExit) as exc:
            cli.main(["--project", "divergence-test", *flags])
        assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err
