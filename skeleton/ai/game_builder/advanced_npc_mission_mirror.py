"""Adversarial, replay-authenticated comparisons of actual original NPC missions.

Compares a bounded collection of human/AI-authored waypoint itineraries against
one exact original source world. Every accepted result executes the real game,
NPC schedules, witness interactions and material actions. Rejected routes are
recorded as rejected, NEVER counted as completed or used for weight promotion.
"""
from __future__ import annotations

from hashlib import sha256

from .advanced_chunked_npc_world import ChunkWorldError, _hash, verify_chunked_npc_world
from .advanced_npc_waypoint_mission import (
    MAX_WAYPOINTS, OriginalMissionError,
    run_original_npc_waypoint_mission, verify_original_npc_waypoint_mission,
)

SCHEMA = "skeleton.game_builder.original_npc_mission_mirror.v1"
MAX_CANDIDATES = 8
MAX_ID_LENGTH = 32


class OriginalMissionMirrorError(OriginalMissionError):
    """A candidate set, evidence, ranking or source-history claim is invalid."""


def _candidates(value):
    if type(value) not in (list, tuple) or not 1 <= len(value) <= MAX_CANDIDATES:
        raise OriginalMissionMirrorError("compare one to eight original mission itineraries")
    names = set()
    result = []
    for candidate in value:
        if type(candidate) is not dict or set(candidate) != {
            "id", "waypoints", "max_steps_per_leg",
        }:
            raise OriginalMissionMirrorError("each actual plan needs exact ID, waypoints and budget")
        ident = candidate["id"]
        stops = candidate["waypoints"]
        budget = candidate["max_steps_per_leg"]
        if (type(ident) is not str or not 1 <= len(ident) <= MAX_ID_LENGTH
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in ident)
            or ident in names):
            raise OriginalMissionMirrorError("mission comparison IDs must be unique safe lowercase tokens")
        if (type(stops) not in (list, tuple) or not 1 <= len(stops) <= MAX_WAYPOINTS
            or any(type(x) is not dict or set(x) != {"kind", "index", "action"}
                   or type(x["kind"]) is not str or type(x["index"]) is not int
                   or type(x["action"]) is not str for x in stops)):
            raise OriginalMissionMirrorError("each original plan must declare one to twelve typed waypoints")
        if type(budget) is not int or not 1 <= budget <= 72:
            raise OriginalMissionMirrorError("mission per-leg physical move budget must be 1..72")
        names.add(ident)
        result.append({
            "id": ident,
            "waypoints": [{**w} for w in stops],
            "max_steps_per_leg": budget,
        })
    return result


def _outcome(mission, origin):
    summary = mission["final_world_summary"]
    before = origin["state"]
    after = summary
    return {
        "completed_legs": mission["completed_waypoint_count"],
        "real_quest_milestones": after["real_quest_milestones"],
        "new_earned_quests": (
            after["real_quest_milestones"] - before["completed"]
        ),
        "real_firsthand_physical_events": after["real_physical_events"],
        "new_physical_events": (
            after["real_physical_events"] - len(before["events"])
        ),
        "actual_paid_choices": after["paid_social_choices"],
        "new_paid_choices": (
            after["paid_social_choices"] - len(before["choices"])
        ),
        "actual_dialogue_lines": after["firsthand_dialogues"],
        "new_dialogue_lines": (
            after["firsthand_dialogues"] - len(before["dialogues"])
        ),
        "actual_steps": mission["total_real_actions"],
        "total_replans": mission["total_replans"],
        "blocked_waits": mission["total_blocked_waits"],
        "remaining_supplies": after["remaining_supplies"],
        "supplies_delta": (
            after["remaining_supplies"] - before["inventory"]["supplies"]
        ),
        "remaining_stamina": after["remaining_stamina"],
        "physical_npc_moves": after["actual_npc_movements"],
        "detailed_npc_updates": after["detailed_actor_updates"],
        "deferred_npc_turns": after["deferred_actor_turns"],
        "world_tick": after["world_tick"],
        "end_cell": after["player_cell"],
        "physical_population": after["physical_npcs"],
        "earned_material_quest": (
            after["real_quest_milestones"] > before["completed"]
        ),
        "result_digest": mission["final_world_digest"],
        "source_head": mission["final_source_head"],
        "per_leg_source_receipt_heads": [
            item["result_head"] for item in mission["legs"]
        ],
        "per_leg_causal_proof_digests": [
            item["digest"] for item in mission["legs"]
        ],
    }


def _dominates(a, b):
    """Only *real* achieved goals, finite supplies and time count."""
    a_keys = (
        a["new_earned_quests"], a["new_physical_events"],
        a["remaining_supplies"], -a["actual_steps"],
        -a["blocked_waits"],
    )
    b_keys = (
        b["new_earned_quests"], b["new_physical_events"],
        b["remaining_supplies"], -b["actual_steps"],
        -b["blocked_waits"],
    )
    return all(x >= y for x, y in zip(a_keys, b_keys)) and any(
        x > y for x, y in zip(a_keys, b_keys)
    )


def analyze_original_npc_missions(source_game, candidates):
    if type(source_game) is not dict:
        raise OriginalMissionMirrorError("entire original gameplay source required")
    try:
        if not verify_chunked_npc_world(source_game):
            raise OriginalMissionMirrorError("original source failed independent gameplay replay")
    except (ChunkWorldError, ValueError, KeyError, TypeError, IndexError) as exc:
        raise OriginalMissionMirrorError("forged original game source") from exc
    variants = _candidates(candidates)
    reviewed = []
    for candidate in variants:
        try:
            mission = run_original_npc_waypoint_mission(
                source_game, candidate["waypoints"],
                max_steps_per_leg=candidate["max_steps_per_leg"],
            )
            if not verify_original_npc_waypoint_mission(mission):
                raise OriginalMissionMirrorError("candidate full source replay diverged")
        except (OriginalMissionError, ChunkWorldError) as exc:
            # The route did not execute: no fictional intermediate rewards.
            reviewed.append({
                "id": candidate["id"], "status": "rejected_by_real_gameplay",
                "reason": str(exc)[:180],
                "accepted": False,
                "outcome": None,
            })
            continue
        result = _outcome(mission, source_game)
        if result["physical_population"] != len(source_game["state"]["actors"]):
            raise OriginalMissionMirrorError("accepted branch changed resident identity count")
        reviewed.append({
            "id":candidate["id"],
            "status":"independently_replayed_real_game",
            "reason":None,
            "accepted":True,
            "outcome":result,
        })
    accepted = [x for x in reviewed if x["accepted"]]
    frontier = sorted([
        x["id"] for x in accepted
        if not any(
            other["id"] != x["id"] and _dominates(
                other["outcome"], x["outcome"]
            )
            for other in accepted
        )
    ])
    priority = sorted(
        accepted,
        key=lambda x: (
            -x["outcome"]["new_earned_quests"],
            -x["outcome"]["new_physical_events"],
            x["outcome"]["actual_steps"],
            -x["outcome"]["remaining_supplies"],
            x["id"],
        ),
    )
    # Lexicographic review order is an explanation, not a universal
    # win condition or objective proof that its outcome is 'best'.
    body = {
        "schema": SCHEMA, "original_source_world": source_game,
        "source_world_digest": source_game["digest"],
        "original_source_head": source_game["head_digest"],
        "candidates": variants, "reviews": reviewed,
        "submitted": len(variants),
        "accepted_actual_routes": len(accepted),
        "rejected_actual_routes": len(variants) - len(accepted),
        "pareto_source_verified_ids": frontier,
        "review_order": [item["id"] for item in priority],
        "first_reviewed_candidate": priority[0]["id"] if priority else None,
        "candidate_set_exhaustively_proven_optimal": False,
        "invalid_or_unproven_routes_promoted": False,
        "original_game_files_mutated": False,
        "model_weights_promoted": False,
        "native_hardware_certified": False,
        "all_valid_routes_reexecuted_from_source": True,
    }
    return {**body, "digest":_hash(body)}


def verify_original_npc_mission_mirror(record):
    if type(record) is not dict or record.get("schema") != SCHEMA:
        raise OriginalMissionMirrorError("exact source-verified original mission analysis record required")
    try:
        expected = analyze_original_npc_missions(
            record["original_source_world"], record["candidates"],
        )
    except (KeyError, IndexError, TypeError, ValueError, RecursionError) as exc:
        raise OriginalMissionMirrorError("unverifiable mission analysis source") from exc
    if expected != record:
        raise OriginalMissionMirrorError("source event, route feasibility, Pareto or cost evidence was forged")
    return True


__all__ = [
    "SCHEMA", "MAX_CANDIDATES", "OriginalMissionMirrorError",
    "analyze_original_npc_missions", "verify_original_npc_mission_mirror",
]
