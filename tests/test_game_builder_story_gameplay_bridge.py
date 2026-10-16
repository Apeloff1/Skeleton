"""Signed literary scene ↔ actual multi-outcome Director gameplay evidence tests."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.quest_scene_engine import DirectorAction
from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.story_canon_fabric import BIBLE, sign
from skeleton.ai.game_builder.story_gameplay_bridge import (
    StoryGameBridgeError, review_story_gameplay,
)
from skeleton.developer.game_cli import run_game_cli
from tests.test_game_builder_story_canon_fabric import canonical_bible, scene_source


def fixture(project="story_player_game"):
    bible = canonical_bible()
    bible["project"] = project
    bible = sign(bible, BIBLE)
    scene = scene_source(bible)
    world = forge_director(
        project, seed=10817,
        regions=("lantern_city", "river", "ridge", "forest"),
        quest_types=("main_story",), stages=2, placement="story",
    )
    q = world.quests[0]
    stage = q.stages[0]
    site = stage.scene_ids[0]
    place = next(s for s in world.scenes if s.key == site)
    runs = []
    bindings = []
    for index in range(2):
        solution = stage.solutions[index]
        objective = solution.required[0]
        affordance = next(
            a for a in place.affordances
            if (a.kind, a.target) == (objective.kind, objective.target)
        )
        actions = [{"kind": "use", "key": affordance.key, "scene": site}]
        # Story placement: stage zero is in the starting scene, so this is
        # genuine available gameplay rather than a fake destination click.
        assert site == world.starting_scene
        runs.append({"name": "original_route_" + str(index), "actions": actions})
        bindings.append({
            "scene_sequence": 1, "source_anchor": "visit_1",
            "replay": runs[-1]["name"],
            "quest": q.key, "stage": stage.key,
            "approach": solution.key,
            "consequence": q.key + "_" + solution.outcome_flag,
        })
    return bible, [scene], world, runs, bindings


def test_executed_quest_actions_prove_two_actual_distinct_player_consequences():
    bible, scenes, world, runs, bindings = fixture()
    report = review_story_gameplay(
        bible, scenes, world, runs, bindings, require_distinct_choices=True,
    )
    assert report["ok"], report
    assert report["replay_count"] == 2
    assert report["real_actions_executed"] == 2
    assert report["source_scenes_bound"] == 1
    assert report["distinct_replayed_consequence_pairs"] == 2
    assert report["binding_evidence"][0]["executed_in_canonical_director"]
    assert report["binding_evidence"][0]["director_replay_sha256"]
    assert not report["actual_full_game_playthrough_verified"]
    assert not report["commercial_game_install_or_native_export_verified"]
    assert not report["model_training_performed"]
    assert len(report["unexecuted_quest_stages"]) == 1


@pytest.mark.parametrize("field,value,error", [
    ("scene_sequence", 9, "unsigned or absent"),
    ("source_anchor", "missing_beat", "exact signed"),
    ("replay", "fabricated", "missing replay"),
    ("quest", "fictional_quest", "nonexistent playable"),
    ("stage", "fictional_stage", "nonexistent playable"),
    ("approach", "method_2", "does not match"),
    ("consequence", "fabricated_ending", "does not match"),
])
def test_source_to_gameplay_false_claims_are_rejected(field, value, error):
    bible, scenes, world, runs, bindings = fixture()
    bindings[0][field] = value
    with pytest.raises(StoryGameBridgeError, match=error):
        review_story_gameplay(bible, scenes, world, runs, bindings)


def test_source_canon_tamper_and_nonexistent_action_cannot_generate_evidence():
    bible, scenes, world, runs, bindings = fixture()
    invalid = deepcopy(scenes)
    invalid[0]["dialogue"][0]["text"] = "Altered unauthorised dialogue"
    with pytest.raises(ValueError):
        review_story_gameplay(bible, invalid, world, runs, bindings)
    forged = deepcopy(runs)
    forged[0]["actions"][0]["key"] = "not_an_executable_action"
    with pytest.raises(ValueError):
        review_story_gameplay(bible, scenes, world, forged, bindings)


def test_duplicate_replay_or_same_consequence_does_not_inflate_branch_qualification():
    bible, scenes, world, runs, bindings = fixture()
    duplicate = deepcopy(runs)
    duplicate[1]["name"] = duplicate[0]["name"]
    with pytest.raises(StoryGameBridgeError, match="duplicate named"):
        review_story_gameplay(bible, scenes, world, duplicate, bindings)
    repeated = [runs[0], {"name": "alternative", "actions": deepcopy(runs[0]["actions"])}]
    binding = [bindings[0], dict(bindings[0], replay="alternative")]
    with pytest.raises(StoryGameBridgeError, match="genuinely distinct"):
        review_story_gameplay(bible, scenes, world, repeated, binding,
                              require_distinct_choices=True)


def test_cross_project_game_is_not_confused_with_signed_book():
    bible, scenes, world, runs, bindings = fixture()
    another = forge_director(
        "foreign_story", seed=10817,
        regions=("lantern_city", "river", "ridge", "forest"),
        quest_types=("main_story",), stages=2, placement="story",
    )
    with pytest.raises(StoryGameBridgeError, match="project identities disagree"):
        review_story_gameplay(bible, scenes, another, runs, bindings)


def test_zero_stage_results_cannot_be_claimed_as_completed_story():
    bible, scenes, world, runs, bindings = fixture()
    runs[0]["actions"] = []
    with pytest.raises(StoryGameBridgeError, match="not actually been played"):
        review_story_gameplay(bible, scenes, world, runs, bindings)


def test_direction_gameplay_cli_replays_canon_without_claiming_full_game(tmp_path):
    created = run_game_cli(["init", "story-player-game", "--dir", str(tmp_path)])
    assert created["ok"], created
    root = tmp_path / "story-player-game"
    bible, scenes, world, replays, bindings = fixture("story_player_game")
    doc = {
        "schema": "skeleton.jeeves.story_gameplay_dossier.v1",
        "bible": bible, "scenes": scenes,
        "director_world": world.payload(), "author_review_acknowledged": True,
        "replays": replays, "bindings": bindings,
        "require_distinct_choices": True,
    }
    path = root / "design" / "story_gameplay_dossier.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    cmd = ["jeeves", "direction-gameplay", "--project", str(root),
           "--source", "design/story_gameplay_dossier.json", "--passes", "3"]
    result = run_game_cli(cmd)
    assert result["ok"], result
    assert len(result["scrutiny_passes"]) == 3
    assert result["real_actions_executed"] == 2
    assert result["distinct_replayed_consequence_pairs"] == 2
    assert result["creator_approval_externally_verified"] is False
    assert result["actual_full_game_playthrough_verified"] is False
    assert path.read_text(encoding="utf-8") == json.dumps(doc)
    doc["author_review_acknowledged"] = False
    path.write_text(json.dumps(doc), encoding="utf-8")
    denied = run_game_cli(cmd)
    assert not denied["ok"]
    assert "acknowledgement" in denied["error"]


def test_direction_gameplay_cli_forbids_unrelated_flags(tmp_path):
    created = run_game_cli(["init", "story-player-game", "--dir", str(tmp_path)])
    assert created["ok"]
    root = tmp_path / "story-player-game"
    result = run_game_cli([
        "jeeves", "direction-gameplay", "--project", str(root),
        "--source", "design/does-not-exist.json", "--target", "ps5",
    ])
    assert not result["ok"]
    assert "accepts --source and --passes only" in result["error"]
