"""Instrumental living-world end-to-end story proof without native claims.

Runs several complete, genuinely legal Director campaigns with actual
inventory/faction/gate/transit state, then INDEPENDENTLY checks the actions
and narrative endings. Reports failed or incomplete paths as counterexamples.
This is not a Godot renderer test, a human playtest or a trained LLM.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, available_director_actions, director_initial, director_step,
)
from skeleton.ai.game_builder.quest_campaign_completion import (
    CampaignCompletionError, play_campaign,
)
from skeleton.developer.jeeves_game_production_board import _load_world
from skeleton.developer.jeeves_game_director_session import _hash

SCHEMA = "skeleton.jeeves.dynamic_campaign_proof.v1"


def _independent_trace(world: Any, witness: Any,
                       max_details: int = 40) -> dict[str, Any]:
    """Replay every action without borrowing any planned intermediate state."""
    state = director_initial(world)
    start_digest = state.digest
    action_count = 0
    journey = []
    effect_count: Counter[str] = Counter()
    mode_count: Counter[str] = Counter()
    opening_reputation = dict(state.world_state.standings)
    visited = Counter({state.scene: 1})
    stage_results = Counter()
    earned_flags = Counter()
    consumed = Counter()
    earned = Counter()
    passage_by_key = {p.key: p for p in world.dynamics.passages}
    total_transport_turns = 0
    stage_checkpoints = []
    noteworthy_total = 0

    for segment in witness.replay["segments"]:
        if segment["start_digest"] != state.digest:
            raise ValueError("campaign segment does not start from replayed dynamic state")
        for raw in segment["actions"]:
            before = state
            action = DirectorAction(**raw)
            if action not in available_director_actions(world, state):
                raise ValueError("campaign journal contains a gated or otherwise illegal action")
            state = director_step(world, state, action)
            action_count += 1
            current = state.world_state
            old = before.world_state
            if current is None or old is None:
                raise ValueError("dynamic campaign lost its faction/world-state history")
            if action.kind == "travel":
                mode_count["foot"] += 1
                visited[state.scene] += 1
            elif action.kind == "transit":
                route = passage_by_key.get(action.key)
                if route is None:
                    raise ValueError("unknown transport in campaign proof")
                mode_count[route.mode] += 1
                total_transport_turns += state.turn - before.turn
                visited[state.scene] += 1
                effect_count["transport_route"] += 1
            elif action.kind == "use":
                effect_count["legal_scene_interaction"] += 1
            else:
                effect_count["wait"] += 1
            if not set(old.world_flags).issubset(current.world_flags):
                raise ValueError("dynamic campaign erased a permanent authored world event")
            if not set(before.complete).issubset(state.complete):
                raise ValueError("dynamic campaign erased a completed quest")
            for flag in set(current.world_flags) - set(old.world_flags):
                earned_flags[flag] += 1
                if earned_flags[flag] > 1:
                    raise ValueError("permanent event granted more than once")
            for resource in set(before.acquired) - set(state.acquired):
                consumed[resource] += 1
            for resource in set(state.acquired) - set(before.acquired):
                earned[resource] += 1
            for result in state.results[len(before.results):]:
                stage_results[result.quest] += 1
                effect_count["authored_quest_stage_completed"] += 1
                stage_checkpoints.append({
                    "at_action": action_count,
                    "quest": result.quest,
                    "stage": result.stage,
                    "approach": result.approach,
                    "outcome": result.consequence,
                    "after_sha256": state.digest,
                    "standing": dict(current.standings),
                    "world_flags": list(current.world_flags),
                })
            if (action.kind == "transit"
                    or len(state.results) != len(before.results)
                    or current.world_flags != old.world_flags
                    or current.standings != old.standings):
                noteworthy_total += 1
                if len(journey) < max_details:
                    journey.append({
                    "sequence": action_count, "action": action.payload(),
                    "scene_before": before.scene,
                    "scene_after": state.scene, "turns": state.turn - before.turn,
                    "before_state_sha256": before.digest,
                    "after_state_sha256": state.digest,
                    "new_flags": sorted(set(current.world_flags) - set(old.world_flags)),
                })
        if segment["end_digest"] != state.digest:
            raise ValueError("campaign segment terminal digest disagrees with real transitions")
    if state.digest != witness.report["final_director_state_sha256"]:
        raise ValueError("campaign ending differs from independently replayed state")
    if action_count != witness.report["action_count"]:
        raise ValueError("campaign action count differs from witnessed report")
    if len(state.complete) != len(world.quests):
        raise ValueError("dynamic campaign claims completion with unfinished authored quests")
    if len(state.results) != sum(len(q.stages) for q in world.quests):
        raise ValueError("authored stage completion record count differs")
    return {
        "action_count": action_count,
        "initial_state_sha256": start_digest,
        "final_state_sha256": state.digest,
        "final_scene": state.scene,
        "final_turn": state.turn,
        "completed_quests": list(state.complete),
        "stage_result_count": len(state.results),
        "stage_result_checkpoints": stage_checkpoints[:96],
        "stage_result_checkpoint_count": len(stage_checkpoints),
        "story_ending_flags": list(state.narrative_flags),
        "world_flags": list(state.world_state.world_flags),
        "reputation_initial": opening_reputation,
        "reputation_final": dict(state.world_state.standings),
        "mode_counts": dict(sorted(mode_count.items())),
        "transport_turns": total_transport_turns,
        "transport_counts_by_key": dict(state.world_state.passage_uses),
        "scene_entrance_counts": dict(sorted(visited.items())),
        "permanent_world_events": dict(sorted(earned_flags.items())),
        "consumed_items": dict(sorted(consumed.items())),
        "acquired_items": dict(sorted(earned.items())),
        "causal_event_counts": dict(sorted(effect_count.items())),
        "verified_noteworthy_event_sample": journey,
        "noteworthy_event_count": noteworthy_total,
        "noteworthy_event_sample_covers_all": noteworthy_total <= max_details,
        "all_quest_actions_executed_in_canonical_engine": True,
        "godot_binary_launched": False,
        "real_installed_game_tested": False,
    }


def prove(root: Path, *, source: str, routes: int = 3,
          optional: bool = False) -> dict[str, Any]:
    if type(routes) is not int or not 1 <= routes <= 8:
        raise ValueError("dynamic campaign proof supports 1..8 complete strategy profiles")
    if type(optional) is not bool:
        raise ValueError("include optional quest objectives must be a strict boolean")
    from skeleton.developer.jeeves_game_quality import _read
    world, source_sha = _load_world(root, source)
    if world.dynamics is None:
        raise ValueError("only a reviewed dynamic-world source can run this proof")
    reports = []
    failed = []
    outcomes = {}
    for route in range(routes):
        try:
            witness = play_campaign(
                world, preference=route,
                include_optional=optional, segment_size=256,
            )
            report = _independent_trace(world, witness)
            signature = _hash({
                "story_flags": report["story_ending_flags"],
                "world_flags": report["world_flags"],
                "standing": report["reputation_final"],
                "stage_outcomes": [
                    (r["quest"], r["stage"], r["approach"])
                    for r in witness.report["results"]
                ],
            })
            report["strategy"] = route
            report["narrative_outcome_sha256"] = signature
            report["original_game_source_sha256"] = source_sha
            reports.append(report)
            outcomes.setdefault(signature, []).append(route)
        except (CampaignCompletionError, ValueError, KeyError, TypeError) as exc:
            failed.append({
                "strategy": route,
                "failure_type": type(exc).__name__,
                "reason": str(exc)[:350],
                "no_game_completion_claimed": True,
            })
    if _read(root, source, 16 * 1024 * 1024)[1] != source_sha:
        raise ValueError("authored dynamic campaign changed during proof")
    return {
        "ok": not failed and len(reports) == routes,
        "schema": SCHEMA,
        "action": "director-dynamics-playthrough",
        "source_sha256": source_sha,
        "director_world_sha256": world.digest,
        "strategy_count_requested": routes,
        "complete_playthroughs_verified": len(reports),
        "failed_or_unproven_strategies": failed,
        "outcome_class_count": len(outcomes),
        "outcome_groups": [
            {"outcome_sha256": key, "strategies": strategies}
            for key, strategies in sorted(outcomes.items())
        ],
        "reports": reports,
        "no_automatic_source_or_gameplay_saves_created": True,
        "python_authoritative_logic_playthrough_proved": not failed,
        "no_global_ci_job_created": True,
        "native_godot_full_campaign_verified": False,
        "native_transit_rendering_verified": False,
        "human_emotional_narrative_quality_verified": False,
        "production_model_weights_trained": False,
        "qualified_for_game_release": False,
    }
