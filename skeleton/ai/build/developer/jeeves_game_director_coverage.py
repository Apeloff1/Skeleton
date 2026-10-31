"""Campaign path coverage and authoring gaps grounded in replayed Director state.

Picks different route policies and optional-objective settings, then reports
which authored solution methods the verified actions actually exercised.
This is an exhaustive inventory of the SELECTED replay strategies, never an
exhaustive proof of all possible player worlds or a rendered game test.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from skeleton.developer.jeeves_game_production_board import _load_world
from skeleton.ai.game_builder.quest_campaign_completion import (
    compare_campaign_branches,
)

SCHEMA = "skeleton.jeeves.director_coverage_atlas.v1"


def coverage(root: Path, *, source: str, routes: int = 3) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_quality import _read
    if type(routes) is not int or not 2 <= routes <= 8:
        raise ValueError("coverage needs 2..8 deterministic route strategies")
    world, source_sha = _load_world(root, source)
    observed: dict[tuple[str, str], set[str]] = defaultdict(set)
    coverage_reports = []
    receipts = []
    for optional in (False, True):
        checked = compare_campaign_branches(
            world, routes=routes, include_optional=optional
        )
        if not checked["ok"] or not checked["all_routes_completed"]:
            raise ValueError("Director route did not complete all game logic quests")
        coverage_reports.append({
            "optional_objectives_requested": optional,
            "replays": checked["route_count"],
            "divergent_stages": len(checked["divergent_quest_stages"]),
        })
        for row in checked["route_reports"]:
            receipts.append(row["replay_receipt_sha256"])
            for step in row["results"]:
                observed[(step["quest"], step["stage"])].add(step["approach"])
    stages = []
    gaps = []
    for quest in world.quests:
        for stage in quest.stages:
            methods = {s.key for s in stage.solutions}
            seen = observed[(quest.key, stage.key)]
            unvisited = sorted(methods - seen)
            stage_view = {
                "quest": quest.key, "stage": stage.key,
                "authored_method_count": len(methods),
                "observed_solution_keys": sorted(seen),
                "unobserved_solution_keys": unvisited,
                "optional_objective_count": len(stage.optional),
                "referenced_scene_ids": list(stage.scene_ids),
                "cutscene_on_complete": stage.cutscene_on_complete,
                "every_declared_solution_strategy_replayed": not unvisited,
            }
            stages.append(stage_view)
            for method in unvisited:
                gaps.append({
                    "priority": "P1", "kind": "unreplayed_quest_method",
                    "quest": quest.key, "stage": stage.key, "method": method,
                    "needs_native_gameplay": True,
                })
    all_cinematics = {(scene.key, cut.key) for scene in world.scenes
                      for cut in scene.cutscenes}
    linked_cinematics = {
        (sid, cut)
        for q in world.quests for stage in q.stages for sid in stage.scene_ids
        for cut in (stage.cutscene_on_start, stage.cutscene_on_complete)
        if cut is not None and (sid, cut) in all_cinematics
    }
    orphaned = sorted(all_cinematics - linked_cinematics)
    for sid, cid in orphaned:
        gaps.append({
            "priority": "P2", "kind": "unlinked_cinematic_timeline",
            "scene": sid, "cutscene": cid, "needs_native_gameplay": True,
        })
    audio_cues = sorted({scene.music for scene in world.scenes})
    cast = sorted({actor for scene in world.scenes for actor in scene.cast})
    outcomes = sorted({s.outcome_flag for q in world.quests
                       for stage in q.stages for s in stage.solutions})
    if _read(root, source, 16 * 1024 * 1024)[1] != source_sha:
        raise ValueError("Director campaign source changed during coverage study")
    return {
        "ok": True, "schema": SCHEMA, "action": "director-coverage",
        "project": world.project_id, "source": source,
        "source_sha256": source_sha, "world_sha256": world.digest,
        "selected_replay_strategies": routes * 2,
        "optional_replay_variants": coverage_reports,
        "sampled_replay_receipts": receipts,
        "stage_approach_coverage": stages,
        "authored_story_outcome_flags": outcomes,
        "unique_cast_identities": cast,
        "authored_audio_cues": audio_cues,
        "all_authored_cinematic_timelines": len(all_cinematics),
        "orphan_cinematic_timelines": [
            {"scene": sid, "cutscene": cid} for sid, cid in orphaned
        ],
        "review_workorders": gaps,
        "all_declared_methods_exercised_by_sample": not any(
            s["unobserved_solution_keys"] for s in stages
        ),
        "native_scene_playthrough_verified": False,
        "actual_audio_assets_present_verified": False,
        "all_possible_gameplay_paths_exhaustively_proven": False,
        "independent_story_and_quality_signoff": False,
    }
