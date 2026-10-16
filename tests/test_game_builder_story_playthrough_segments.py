"""Regression tests for multi-stage, resumable original game replays."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.quest_playthrough_journal import (
    DirectorSegmentError, replay_director_segments,
)
from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, director_initial, director_step,
)
from skeleton.ai.game_builder.story_gameplay_bridge import review_story_gameplay
from skeleton.developer.game_cli import run_game_cli
from tests.test_game_builder_story_gameplay_bridge import fixture as story_fixture


def _walk(world, source, target):
    mapping = {scene.key: scene for scene in world.scenes}
    queue = deque([(source, ())])
    seen = {source}
    while queue:
        node, route = queue.popleft()
        if node == target:
            return list(route)
        for neighbor in mapping[node].links:
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, route + (
                    DirectorAction("travel", neighbor, node),
                )))
    raise AssertionError("DirectorWorld must have a navigable second stage")


def _segment(world, original_state, actions):
    state = original_state
    for action in actions:
        state = director_step(world, state, action)
    return {
        "actions": [action.payload() for action in actions],
        "start_digest": original_state.digest,
        "end_digest": state.digest,
    }, state


def _two_stage_route():
    bible, scenes, world, runs, bindings = story_fixture()
    state = director_initial(world)
    first = [DirectorAction(**step) for step in runs[0]["actions"]]
    piece_a, state = _segment(world, state, first)
    q = world.quests[0]
    stage = q.stages[1]
    solution = stage.solutions[0]
    remaining = []
    cursor = state.scene
    for required in solution.required:
        site = next(scene for scene in world.scenes if scene.key in stage.scene_ids
                    and any(a.kind == required.kind and a.target == required.target
                            for a in scene.affordances))
        remaining.extend(_walk(world, cursor, site.key))
        affordance = next(a for a in site.affordances
                          if a.kind == required.kind and a.target == required.target)
        remaining.extend(DirectorAction("use", affordance.key, site.key)
                         for _ in range(required.count))
        cursor = site.key
    piece_b, final = _segment(world, state, remaining)
    assert q.key in final.complete
    assert len(final.results) == len(q.stages)
    runs[0] = {"name": runs[0]["name"], "segments": [piece_a, piece_b]}
    second_result = next(result for result in final.results
                         if result.quest == q.key and result.stage == stage.key)
    bindings.append({
        "scene_sequence": 1, "source_anchor": "visit_1",
        "replay": runs[0]["name"], "quest": q.key, "stage": stage.key,
        "approach": second_result.approach,
        "consequence": second_result.consequence,
    })
    return bible, scenes, world, runs, bindings, final


def test_chained_segments_prove_consecutive_quest_stages_without_resetting_state():
    bible, scenes, world, runs, bindings, final = _two_stage_route()
    evidence = review_story_gameplay(
        bible, scenes, world, runs, bindings, require_distinct_choices=True,
    )
    assert evidence["ok"]
    assert evidence["quest_stages_executed"] == 2
    assert evidence["unexecuted_quest_stages"] == []
    assert evidence["played_stages_not_bound_to_story"] == []
    assert evidence["story_gameplay_coverage_complete"] is True
    assert evidence["real_actions_executed"] == sum(
        len(seg["actions"]) for seg in runs[0]["segments"]
    ) + len(runs[1]["actions"])
    receipts = evidence["replay_segment_receipts"][runs[0]["name"]]
    assert len(receipts) == 2
    assert receipts[0]["end_digest"] == receipts[1]["start_digest"]
    assert receipts[1]["end_digest"] == final.digest
    assert receipts[1]["completed_quests"] == 1
    assert receipts[1]["executed_quest_stages"] == 2
    assert not evidence["actual_full_game_playthrough_verified"]
    assert not evidence["model_training_performed"]


@pytest.mark.parametrize("tamper,match", [
    ("start", "checkpoint"),
    ("end", "checkpoint"),
    ("reorder", "checkpoint"),
    ("drop", "checkpoint"),
    ("empty", "per-slice"),
    ("extra", "checkpoint"),
])
def test_forged_or_missing_segment_is_rejected(tamper, match):
    _, _, world, runs, _, _ = _two_stage_route()
    segments = deepcopy(runs[0]["segments"])
    if tamper == "start":
        segments[1]["start_digest"] = "0" * 64
    elif tamper == "end":
        segments[1]["end_digest"] = "f" * 64
    elif tamper == "reorder":
        segments.reverse()
    elif tamper == "drop":
        segments[1]["start_digest"] = "a" * 64
    elif tamper == "empty":
        segments[1]["actions"] = []
    else:
        segments[1]["actions"].append({"kind": "wait", "key": "wait",
                                      "scene": segments[1]["actions"][-1]["scene"]})
    with pytest.raises(DirectorSegmentError, match=match):
        replay_director_segments(world, segments)


def test_segments_are_deterministic_and_preserve_legacy_replays():
    bible, scenes, world, runs, bindings, _ = _two_stage_route()
    first = replay_director_segments(world, runs[0]["segments"])
    again = replay_director_segments(world, deepcopy(runs[0]["segments"]))
    assert first.digest == again.digest
    assert first.final == again.final
    report = review_story_gameplay(bible, scenes, world, runs, bindings)
    assert set(report["replay_segment_receipts"]) == {runs[0]["name"]}
    assert report["binding_evidence"][1]["director_replay_sha256"]


def test_game_cli_accepts_chunked_story_quest_dossier(tmp_path):
    assert run_game_cli(["init", "story-player-game", "--dir", str(tmp_path)])["ok"]
    root = tmp_path / "story-player-game"
    bible, scenes, world, runs, bindings, _ = _two_stage_route()
    packet = {
        "schema": "skeleton.jeeves.story_gameplay_dossier.v1",
        "bible": bible, "scenes": scenes,
        "director_world": world.payload(), "author_review_acknowledged": True,
        "replays": runs, "bindings": bindings, "require_distinct_choices": True,
    }
    path = root / "design" / "story_gameplay_dossier.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    reviewed = run_game_cli([
        "jeeves", "direction-gameplay", "--project", str(root),
        "--source", "design/story_gameplay_dossier.json", "--passes", "2",
    ])
    assert reviewed["ok"], reviewed
    assert reviewed["story_gameplay_coverage_complete"]
    assert len(reviewed["scrutiny_passes"]) == 2
    assert len(reviewed["replay_segment_receipts"]["original_route_0"]) == 2
    assert reviewed["actual_full_game_playthrough_verified"] is False


def test_large_segment_or_invalid_action_fails_closed():
    _, _, world, runs, _, _ = _two_stage_route()
    segments = deepcopy(runs[0]["segments"])
    segments[0]["actions"] = segments[0]["actions"] * 8193
    with pytest.raises(DirectorSegmentError, match="per-slice"):
        replay_director_segments(world, segments)
    segments = deepcopy(runs[0]["segments"])
    segments[1]["actions"][0]["kind"] = "fabricate"
    with pytest.raises(ValueError, match="invalid action kind"):
        replay_director_segments(world, segments)
