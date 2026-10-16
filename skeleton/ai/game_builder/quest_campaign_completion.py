"""Deterministic full-quest campaign witnesses in the original Director runtime.

This is an executable game-logic test, not a native Godot/exported game.
Planning never grants progress directly: every move/choice is admitted by
available_director_actions and executed by director_step. All input worlds
remain governed by the existing approved Director blueprint compiler.
"""
from __future__ import annotations

from collections import deque, defaultdict
from dataclasses import dataclass
from typing import Any

from .quest_scene_engine import (
    MAX_EVENTS, DirectorAction, DirectorError, DirectorWorld, DirectorState,
    director_initial, director_step, available_director_actions,
)
from .quest_playthrough_journal import replay_director_segments

SCHEMA = "skeleton.game_builder.campaign_completion.v1"


class CampaignCompletionError(ValueError):
    """The approved original campaign cannot satisfy its playable contract."""


@dataclass(frozen=True, slots=True)
class CampaignWitness:
    report: dict[str, Any]
    replay: dict[str, Any]


def _path(world: DirectorWorld, current: str, destination: str) -> tuple[DirectorAction, ...]:
    graph = {scene.key: scene.links for scene in world.scenes}
    q = deque([(current, ())])
    visited = {current}
    while q:
        scene, moves = q.popleft()
        if scene == destination:
            return moves
        for neighbor in graph[scene]:
            if neighbor not in visited:
                visited.add(neighbor)
                q.append((neighbor, moves + (DirectorAction("travel", neighbor, scene),)))
    raise CampaignCompletionError("approved authored quest scene is unreachable")


def _candidate(world: DirectorWorld, state: DirectorState, stage: Any,
               parameter: Any) -> tuple[str, Any] | None:
    """Choose a reachable legal affordance, never assume a missing resource."""
    candidates = []
    for scene in world.scenes:
        if scene.key not in stage.scene_ids:
            continue
        for affordance in scene.affordances:
            if ((affordance.kind, affordance.target) == (parameter.kind, parameter.target)
                    and (affordance.consumes is None or affordance.consumes in state.acquired)):
                candidates.append((len(_path(world, state.scene, scene.key)), scene.key,
                                   affordance.key, affordance))
    if not candidates:
        return None
    _, site, _, affordance = min(candidates, key=lambda row: row[:3])
    return site, affordance


def _complete_stage(world: DirectorWorld, state: DirectorState, quest: Any,
                    stage: Any, preference: int, include_optional: bool,
                    actions: list[DirectorAction], checkpoints: list[DirectorState]) -> DirectorState:
    current_stage = dict(state.stage_index)[quest.key]
    solution_candidates = stage.solutions[preference % len(stage.solutions):] + (
        stage.solutions[:preference % len(stage.solutions)]
    )
    solution = next((candidate for candidate in solution_candidates
                     if all(_candidate(world, state, stage, p) is not None
                            for p in candidate.required)), None)
    if solution is None:
        raise CampaignCompletionError("no feasible approved solution for " + quest.key + "/" + stage.key)

    def apply(action: DirectorAction) -> None:
        nonlocal state
        if action not in available_director_actions(world, state):
            raise CampaignCompletionError("planner chose unavailable original action")
        state = director_step(world, state, action)
        actions.append(action)
        checkpoints.append(state)

    def satisfy(parameter: Any) -> None:
        nonlocal state
        for _ in range(parameter.count):
            picked = _candidate(world, state, stage, parameter)
            if picked is None:
                raise CampaignCompletionError("missing original scene resource for quest objective")
            site, affordance = picked
            for step in _path(world, state.scene, site):
                apply(step)
            apply(DirectorAction("use", affordance.key, site))

    if include_optional:
        for optional in stage.optional:
            satisfy(optional)
    for requirement in solution.required:
        if dict(state.stage_index)[quest.key] != current_stage:
            raise CampaignCompletionError("quest stage advanced before all planned objectives")
        satisfy(requirement)
    if dict(state.stage_index)[quest.key] != current_stage + 1:
        raise CampaignCompletionError("quest stage failed to complete in original Director runtime")
    matched = [r for r in state.results if r.quest == quest.key and r.stage == stage.key]
    if len(matched) != 1 or matched[0].approach != solution.key:
        raise CampaignCompletionError("runtime result differs from planned authored solution")
    return state


def play_campaign(world: DirectorWorld, *, preference: int = 0,
                  include_optional: bool = True, segment_size: int = 256) -> CampaignWitness:
    """Execute all authored quests and stages, preserving legal state transitions."""
    if not isinstance(world, DirectorWorld):
        raise CampaignCompletionError("typed approved original DirectorWorld required")
    if type(preference) is not int or preference < 0 or preference > 7:
        raise CampaignCompletionError("route preference must be an integer between 0 and 7")
    if type(include_optional) is not bool:
        raise CampaignCompletionError("optional quest policy must be boolean")
    if type(segment_size) is not int or not 1 <= segment_size <= MAX_EVENTS:
        raise CampaignCompletionError("recording slice must be between 1 and 8192 actions")
    state = director_initial(world)
    actions: list[DirectorAction] = []
    states: list[DirectorState] = []
    uncompleted = {q.key for q in world.quests}
    while uncompleted:
        progress = False
        for quest in world.quests:
            if quest.key not in uncompleted or not set(quest.requires_quests).issubset(state.complete):
                continue
            while dict(state.stage_index)[quest.key] < len(quest.stages):
                index = dict(state.stage_index)[quest.key]
                state = _complete_stage(world, state, quest, quest.stages[index],
                                        preference, include_optional, actions, states)
            if quest.key not in state.complete:
                raise CampaignCompletionError("final quest stage failed to close approved quest")
            uncompleted.remove(quest.key)
            progress = True
        if not progress:
            raise CampaignCompletionError("unresolvable original quest dependency cycle")

    if not actions or len(state.results) != sum(len(q.stages) for q in world.quests):
        raise CampaignCompletionError("campaign did not execute every authored quest stage")
    segments = []
    start = director_initial(world)
    for offset in range(0, len(actions), segment_size):
        chunk = actions[offset:offset + segment_size]
        end = states[min(offset + segment_size, len(states)) - 1]
        segments.append({
            "actions": [action.payload() for action in chunk],
            "start_digest": start.digest,
            "end_digest": end.digest,
        })
        start = end
    checked = replay_director_segments(world, segments)
    if checked.final != state or checked.action_count != len(actions):
        raise CampaignCompletionError("campaign and independent segment replay disagree")
    results = [r.payload() for r in checked.final.results]
    return CampaignWitness(
        report={
            "schema": SCHEMA, "project": world.project_id,
            "director_world_digest": world.digest,
            "all_authored_quests_executed": True,
            "all_authored_stages_executed": True,
            "optional_objectives_requested": include_optional,
            "quests_completed": len(checked.final.complete),
            "stages_completed": len(results),
            "action_count": checked.action_count,
            "segments_verified": len(checked.segment_receipts),
            "replay_receipt_sha256": checked.digest,
            "final_director_state_sha256": checked.final.digest,
            "results": results,
            "segment_receipts": list(checked.segment_receipts),
            "native_engine_playthrough_verified": False,
            "actual_save_file_recovery_verified": False,
            "independent_human_playtest_verified": False,
            "licensed_release_binary_verified": False,
            "model_training_performed": False,
        },
        replay={"name": "campaign_route_" + str(preference), "segments": segments},
    )


def compare_campaign_branches(world: DirectorWorld, *, routes: int = 2,
                              include_optional: bool = True) -> dict[str, Any]:
    """Require truly different executed outcomes across entire completed routes."""
    if type(routes) is not int or not 1 <= routes <= 8:
        raise CampaignCompletionError("compare 1..8 fully replayed original routes")
    witnesses = [play_campaign(world, preference=option,
                               include_optional=include_optional)
                 for option in range(routes)]
    variations: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for witness in witnesses:
        for item in witness.report["results"]:
            variations[(item["quest"], item["stage"])].add(
                (item["approach"], item["consequence"])
            )
    divergent = sorted((q, st) for (q, st), outcomes in variations.items()
                       if len(outcomes) >= 2)
    # Multiple routes that differ only in travelling steps are cosmetic.
    qualified = routes == 1 or bool(divergent)
    return {
        "ok": qualified, "schema": SCHEMA, "action": "direction-campaign",
        "project": world.project_id, "director_world_digest": world.digest,
        "route_count": routes,
        "all_routes_completed": all(w.report["all_authored_quests_executed"]
                                    for w in witnesses),
        "distinct_outcome_stage_count": len(divergent),
        "divergent_quest_stages": [{"quest": q, "stage": st} for q, st in divergent],
        "route_reports": [w.report for w in witnesses],
        "replays_for_signed_story_binding": [w.replay for w in witnesses],
        "branch_outcomes_materially_distinct": qualified,
        "canonical_story_binding_verified_by_this_command": False,
        "native_full_game_or_installed_app_certified": False,
        "qualified_for_release": False,
    }
