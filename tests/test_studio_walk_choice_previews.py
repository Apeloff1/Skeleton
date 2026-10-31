"""Non-mutating source-verified choice forecasts across authored walk scenes."""
from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_replay as replay
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


WORLD = {
    "project_id": "preview-test", "source_digest": "a" * 64,
    "width": 6, "height": 6, "spawn": [1, 1], "target": [4, 4],
    "maps": [["######", "#...##", "###..#", "#....#", "#....#", "######"]] * 2,
    "stages": [
        {"id": "marker", "alternatives": ["inspect", "leave"], "prerequisites": []},
        {"id": "aftermath", "alternatives": ["continue"], "prerequisites": ["marker"]},
    ],
}


@pytest.fixture
def docs(monkeypatch):
    monkeypatch.setattr(replay, "playable_world_source", lambda _: WORLD)
    return {}


def _near(docs):
    return replay.follow_walk_route(replay.start_walk(docs, authorized=True),
                                    docs, authorized=True)[0]


def test_preview_requires_authorization_and_unforged_session(docs):
    session = replay.start_walk(docs, authorized=True)
    with pytest.raises(PermissionError):
        replay.walk_choice_previews(session, docs, authorized=False)
    with pytest.raises(StudioQuestError, match="authoritative replay"):
        replay.walk_choice_previews(replace(session, position=(4, 4)), docs, authorized=True)


def test_preview_is_nonmutating_deterministic_and_matches_real_choices(docs):
    session = _near(docs)
    original = session.receipt()
    preview = replay.walk_choice_previews(session, docs, authorized=True)
    assert preview == replay.walk_choice_previews(session, docs, authorized=True)
    assert session.receipt() == original
    assert preview["status"] == "ready"
    assert [p["alternative"] for p in preview["alternatives"]] == ["inspect", "leave"]
    assert preview["session_digest"] == session.digest
    assert preview["release_certified"] is False
    for item in preview["alternatives"]:
        after = replay.walk_action(session, docs, action="choose",
                                   value=item["alternative"], authorized=True)
        assert item["result_session_digest"] == after.digest
        assert item["next_scene_id"] == "aftermath"
        assert item["next_scene_index"] == 1
        assert item["sandbox_stages_complete"] is False


def test_distant_locked_completed_are_nonexecutable(docs, monkeypatch):
    session = replay.start_walk(docs, authorized=True)
    assert replay.walk_choice_previews(session, docs, authorized=True)["status"] == "distant"
    locked = dict(WORLD, stages=[dict(WORLD["stages"][0], prerequisites=["unearned"]),
                                 WORLD["stages"][1]])
    monkeypatch.setattr(replay, "playable_world_source", lambda _: locked)
    locked_session = replay.start_walk(docs, authorized=True)
    assert replay.walk_choice_previews(locked_session, docs, authorized=True)["status"] == "locked"
    assert replay.walk_choice_previews(locked_session, docs, authorized=True)["alternatives"] == []
    monkeypatch.setattr(replay, "playable_world_source", lambda _: WORLD)
    near = _near(docs)
    first = replay.walk_action(near, docs, action="choose", value="inspect", authorized=True)
    second = replay.follow_walk_route(first, docs, authorized=True)[0]
    completed = replay.walk_action(second, docs, action="choose", value="continue", authorized=True)
    result = replay.walk_choice_previews(completed, docs, authorized=True)
    assert result["status"] == "completed" and result["alternatives"] == []


def test_last_stage_preview_does_not_claim_native_completion(docs):
    first = replay.walk_action(_near(docs), docs, action="choose",
                               value="leave", authorized=True)
    second = replay.follow_walk_route(first, docs, authorized=True)[0]
    result = replay.walk_choice_previews(second, docs, authorized=True)
    assert result["alternatives"][0]["sandbox_stages_complete"] is True
    assert result["alternatives"][0]["next_scene_id"] is None
    assert result["native_genre_runtime_verified"] is False


def test_preview_event_budget_exhaustion_is_explicit(docs, monkeypatch):
    session = _near(docs)
    monkeypatch.setattr(replay, "MAX_WALK_EVENTS", len(session.events))
    result = replay.walk_choice_previews(session, docs, authorized=True)
    assert result["status"] == "budget_exhausted"
    assert result["alternatives"] == []


def test_alternative_budget_rejects_oversized_or_duplicate_authored_branches(docs, monkeypatch):
    for choices in ([str(i) for i in range(9)], ["same", "same"], ["x" * 257]):
        altered = dict(WORLD, stages=[dict(WORLD["stages"][0], alternatives=choices),
                                      WORLD["stages"][1]])
        monkeypatch.setattr(replay, "playable_world_source", lambda _, w=altered: w)
        near = _near(docs)
        with pytest.raises(StudioQuestError, match="alternatives"):
            replay.walk_choice_previews(near, docs, authorized=True)


def test_source_mutation_after_verification_is_rejected(docs, monkeypatch):
    session = _near(docs)
    original = replay.playable_world_source
    calls = 0
    def switch_source(source):
        nonlocal calls
        calls += 1
        world = original(source)
        return dict(world, source_digest="b" * 64) if calls >= 2 else world
    monkeypatch.setattr(replay, "playable_world_source", switch_source)
    with pytest.raises(StudioQuestError, match="changed authoritative source"):
        replay.walk_choice_previews(session, docs, authorized=True)


def test_source_mutation_during_branch_simulation_is_rejected(docs, monkeypatch):
    session = _near(docs)
    original = replay.playable_world_source
    calls = 0
    def switch_source(source):
        nonlocal calls
        calls += 1
        world = original(source)
        return dict(world, source_digest="b" * 64) if calls >= 3 else world
    monkeypatch.setattr(replay, "playable_world_source", switch_source)
    with pytest.raises(StudioQuestError, match="changed authoritative source"):
        replay.walk_choice_previews(session, docs, authorized=True)


def test_cli_choice_preview_roundtrip(monkeypatch, capsys, docs):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    session = _near(docs)
    assert cli.main(["--project", "preview-test", "--play-walk", "--walk-receipt",
                     json.dumps(session.receipt()), "--walk-preview-choices"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["receipt"] == session.receipt()
    assert payload["choice_previews"]["status"] == "ready"
    assert len(payload["choice_previews"]["alternatives"]) == 2


def test_cli_preview_rejects_mode_confusion(capsys):
    from scripts.studio_ecosystem_cli import main
    for args in (["--project", "preview-test", "--walk-preview-choices"],
                 ["--project", "preview-test", "--play-walk", "--walk-route",
                  "--walk-preview-choices"],
                 ["--project", "preview-test", "--play-quest", "--walk-preview-choices"]):
        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err
