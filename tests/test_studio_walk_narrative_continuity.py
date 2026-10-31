"""Source-bound played narrative, ending and CLI continuity contracts."""
from dataclasses import replace
from types import SimpleNamespace
import json

import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_replay as walk
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def _fixture():
    stage_a = SimpleNamespace(key="prologue", prerequisites=(),
                              alternatives=("investigate", "depart"), reward="clue")
    stage_b = SimpleNamespace(key="aftermath", prerequisites=("prologue",),
                              alternatives=("accept",), reward="alliance")
    program = SimpleNamespace(project_id="continuity-test", source_digest="f" * 64,
                              stages=(stage_a, stage_b),
                              endings=(("quiet", ("clue",)),
                                       ("accord", ("alliance", "prologue")),
                                       ("unresolved", ("external_witness",))))
    world = {"project_id": program.project_id, "source_digest": program.source_digest,
             "width": 6, "height": 6, "spawn": [1, 1], "target": [4, 4],
             "maps": [["######", "#...##", "###..#", "#....#", "#....#", "######"]] * 2,
             "stages": [
                 {"id": "prologue", "scene_id": "scene_0", "reward": "clue",
                  "alternatives": ["investigate", "depart"], "prerequisites": []},
                 {"id": "aftermath", "scene_id": "scene_1", "reward": "alliance",
                  "alternatives": ["accept"], "prerequisites": ["prologue"]},
             ]}
    return {"world": world, "program": program}


@pytest.fixture
def docs(monkeypatch):
    from skeleton.ai.game_builder import studio_ecosystem_quest as quest
    data = _fixture()
    monkeypatch.setattr(walk, "playable_world_source", lambda source: source["world"])
    monkeypatch.setattr(quest, "compile_quest_program", lambda source: source["program"])
    return data


def _commit(docs, depth=2):
    start = walk.start_walk(docs, authorized=True)
    return walk.commit_walk_forecast_branch(start, docs, branch_index=0,
                                            depth=depth, authorized=True)[0]


def test_start_has_no_unearned_rewards_and_stable_receipt(docs):
    start = walk.start_walk(docs, authorized=True)
    before = start.receipt()
    first = walk.walk_narrative_continuity(start, docs, authorized=True)
    assert first == walk.walk_narrative_continuity(start, docs, authorized=True)
    assert first["played_trail"] == []
    assert first["completed_stages"] == 0
    assert first["next_scene_id"] == "scene_0"
    assert first["next_route_status"] == "ready"
    assert all(not ending["sandbox_eligible"] for ending in first["sandbox_endings"])
    assert start.receipt() == before
    assert first["release_certified"] is False


def test_partial_play_rewards_only_completed_stage(docs):
    partial = _commit(docs, depth=1)
    report = walk.walk_narrative_continuity(partial, docs, authorized=True)
    assert report["played_trail"] == [
        {"stage_id": "prologue", "scene_id": "scene_0",
         "alternative": "investigate", "sandbox_reward": "clue"}]
    assert report["next_stage_id"] == "aftermath"
    assert report["sandbox_story_complete"] is False
    eligible = {e["ending_id"]: e["sandbox_eligible"] for e in report["sandbox_endings"]}
    assert eligible == {"quiet": True, "accord": False, "unresolved": False}
    assert report["sandbox_endings"][2]["unmet_predicates"] == ["external_witness"]


def test_full_play_reports_only_source_authored_endings(docs):
    complete = _commit(docs)
    report = walk.walk_narrative_continuity(complete, docs, authorized=True)
    assert report["sandbox_story_complete"] is True
    assert report["completed_stages"] == report["authored_stage_count"] == 2
    assert report["next_route_status"] == "completed"
    assert report["next_stage_id"] is None
    assert [e["sandbox_eligible"] for e in report["sandbox_endings"]] == [True, True, False]
    assert report["external_evidence_verified"] is False
    assert report["native_genre_runtime_verified"] is False


def test_choice_alternative_changes_digest_not_ending_facts(docs):
    first = _commit(docs, depth=1)
    start = walk.start_walk(docs, authorized=True)
    second = walk.commit_walk_forecast_branch(start, docs, branch_index=1,
                                               depth=1, authorized=True)[0]
    a = walk.walk_narrative_continuity(first, docs, authorized=True)
    b = walk.walk_narrative_continuity(second, docs, authorized=True)
    assert a["continuity_digest"] != b["continuity_digest"]
    assert a["sandbox_endings"] == b["sandbox_endings"]


def test_auth_required_before_source_reads(docs, monkeypatch):
    monkeypatch.setattr(walk, "playable_world_source", lambda _: pytest.fail("source read"))
    with pytest.raises(PermissionError):
        walk.walk_narrative_continuity(None, docs, authorized=False)


@pytest.mark.parametrize("field,value", [
    ("position", (4, 4)), ("scene_index", 1), ("source_digest", "0" * 64),
    ("digest", "forged"),
])
def test_forged_sessions_fail_closed(docs, field, value):
    session = walk.start_walk(docs, authorized=True)
    with pytest.raises(StudioQuestError):
        walk.walk_narrative_continuity(replace(session, **{field: value}), docs,
                                       authorized=True)


@pytest.mark.parametrize("variant", [
    "source_digest", "stage_count", "stage_order", "stage_reward",
    "stage_alternatives", "scene_id", "prerequisite",
])
def test_quest_scene_drift_rejected(docs, variant):
    session = walk.start_walk(docs, authorized=True)
    if variant == "source_digest":
        docs["program"].source_digest = "0" * 64
    elif variant == "stage_count":
        docs["world"]["stages"].pop()
    elif variant == "stage_order":
        docs["world"]["stages"].reverse()
    elif variant == "stage_reward":
        docs["world"]["stages"][0]["reward"] = "forged"
    elif variant == "stage_alternatives":
        docs["world"]["stages"][0]["alternatives"] = ["unwritten"]
    elif variant == "scene_id":
        docs["world"]["stages"][0]["scene_id"] = ""
    elif variant == "prerequisite":
        docs["world"]["stages"][1]["prerequisites"] = ["missing"]
    with pytest.raises(StudioQuestError, match="source|contract|scene"):
        walk.walk_narrative_continuity(session, docs, authorized=True)


def test_cli_start_save_restore_and_continuity(docs, monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    assert cli.main(["--project", "continuity-test", "--play-walk",
                     "--walk-continuity"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["narrative_continuity"]["completed_stages"] == 0
    receipt = json.dumps(first["receipt"])
    assert cli.main(["--project", "continuity-test", "--play-walk",
                     "--walk-receipt", receipt, "--walk-continuity"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["narrative_continuity"] == first["narrative_continuity"]


def test_cli_rejects_mode_confusion(docs, monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    for args in (["--walk-continuity"],
                 ["--play-walk", "--walk-continuity", "--walk-route"],
                 ["--play-walk", "--walk-continuity", "--walk-forecast"],
                 ["--play-walk", "--walk-continuity", "--walk-commit-forecast-branch", "0"]):
        with pytest.raises(SystemExit) as exc:
            cli.main(["--project", "continuity-test", *args])
        assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err
