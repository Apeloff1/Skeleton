"""Source-backed original NPC expedition and multi-objective quest planning.

Executes the existing physical dynamic route kernel for EACH explicit waypoint.
The next leg starts from the actual independently replayed previous game's
source state, never an imagined teleport or fabricated quest reward.  Story
progress, eyewitnesses and resources originate solely from gameplay actions.
"""
from __future__ import annotations

from .advanced_chunked_npc_world import (
    ChunkWorldError, _hash, run_chunked_npc_world,
    verify_chunked_npc_world,
)
from .advanced_npc_dynamic_route_planner import (
    OriginalRouteError, plan_original_dynamic_route,
)

SCHEMA = "skeleton.game_builder.original_npc_waypoint_mission.v1"
MAX_WAYPOINTS = 12


class OriginalMissionError(OriginalRouteError):
    """Invalid objective graph or impossible actual-world route/quest."""


def _typed_waypoints(waypoints):
    if type(waypoints) not in (tuple, list) or not 1 <= len(waypoints) <= MAX_WAYPOINTS:
        raise OriginalMissionError("one to twelve bounded source goals required")
    result = []
    for waypoint in waypoints:
        if (type(waypoint) is not dict or
            set(waypoint) != {"kind", "index", "action"} or
            type(waypoint["kind"]) is not str or
            type(waypoint["index"]) is not int or
            type(waypoint["action"]) is not str):
            raise OriginalMissionError("each mission leg requires exact original physical goal fields")
        result.append(dict(waypoint))
    return result


def run_original_npc_waypoint_mission(game, waypoints, *, max_steps_per_leg=24):
    if type(max_steps_per_leg) is not int or not 1<=max_steps_per_leg<=72:
        raise OriginalMissionError("per-objective original movement cap must be 1..72")
    goals = _typed_waypoints(waypoints)
    if type(game) is not dict:
        raise OriginalMissionError("original independently replayable game required")
    try:
        if not verify_chunked_npc_world(game):
            raise OriginalMissionError("original game source could not independently replay")
    except (ChunkWorldError,ValueError,KeyError,TypeError,IndexError) as exc:
        raise OriginalMissionError("unauthenticated original mission source") from exc
    current = game
    legs = []
    commands = []
    total_replans = 0
    total_waits = 0
    for number, goal in enumerate(goals):
        available = min(
            max_steps_per_leg,
            current["options"]["max_turns"] - current["state"]["tick"],
            128 - len(current["commands"]),
        )
        if available < 1:
            raise OriginalMissionError("original source world has no remaining mission turn budget")
        try:
            planned = plan_original_dynamic_route(current, goal, max_steps=available)
        except (ChunkWorldError,ValueError,TypeError,KeyError,IndexError) as exc:
            raise OriginalMissionError(
                "leg %d denied by actual NPC collision, source witness, stamina or world rule" % number
            ) from exc
        actions = list(planned["generated_actions"])
        try:
            result = run_chunked_npc_world(
                current["commands"] + actions, current["settings"],
                scenes=current["source_scenes"], seed=current["seed"],
                options=current["options"],
            )
        except (ChunkWorldError,ValueError,KeyError,TypeError) as exc:
            raise OriginalMissionError("mission leg independently replayed source failed") from exc
        if (result["digest"] != planned["result_world_digest"] or
            result["head_digest"] != planned["result_head"] or
            not verify_chunked_npc_world(result)):
            raise OriginalMissionError("original mission waypoint diverged from real source game")
        before=current["state"]
        after=result["state"]
        leg = {
            "leg":number,
            "objective":goal,
            "start_head":current["head_digest"],
            "start_tick":before["tick"],
            "starting_player_cell":before["player"],
            "actual_actions":actions,
            "source_action_receipts":planned["actual_action_receipts"],
            "route_replans":planned["replanning_attempts"],
            "blocked_waits":planned["blocked_waits"],
            "end_tick":after["tick"],
            "ending_player_cell":after["player"],
            "quest_milestones_before":before["completed"],
            "quest_milestones_after":after["completed"],
            "firsthand_physical_facts_added":len(after["events"])-len(before["events"]),
            "genuine_dialogues_added":len(after["dialogues"])-len(before["dialogues"]),
            "paid_social_choices_added":len(after["choices"])-len(before["choices"]),
            "supplies_delta":after["inventory"]["supplies"]-before["inventory"]["supplies"],
            "stamina_delta":after["inventory"]["stamina"]-before["inventory"]["stamina"],
            "actor_count":len(after["actors"]),
            "arrived":planned["arrived_at_source_objective"],
            "source_interaction_executed":planned["performed_optional_real_interaction"],
            "result_digest":result["digest"],
            "result_head":result["head_digest"],
        }
        leg["digest"] = _hash(leg)
        legs.append(leg)
        commands.extend(actions)
        total_replans += planned["replanning_attempts"]
        total_waits += planned["blocked_waits"]
        current = result
    final=current["state"]
    body = {
        "schema":SCHEMA,
        "starting_world":game,
        "source_world_digest":game["digest"],
        "waypoints":goals,
        "max_steps_per_leg":max_steps_per_leg,
        "total_real_actions":len(commands),
        "generated_actions":commands,
        "legs":legs,
        "completed_waypoint_count":len(legs),
        "total_replans":total_replans,
        "total_blocked_waits":total_waits,
        "final_world_digest":current["digest"],
        "final_source_head":current["head_digest"],
        "final_world_summary":{
            "world_tick":final["tick"],
            "player_cell":final["player"],
            "physical_npcs":len(final["actors"]),
            "real_quest_milestones":final["completed"],
            "real_physical_events":len(final["events"]),
            "firsthand_dialogues":len(final["dialogues"]),
            "paid_social_choices":len(final["choices"]),
            "remaining_supplies":final["inventory"]["supplies"],
            "remaining_stamina":final["inventory"]["stamina"],
            "actual_npc_movements":final["scheduler"]["physical_moves"],
            "detailed_actor_updates":final["scheduler"]["detailed_updates"],
            "deferred_actor_turns":final["scheduler"]["deferred_actor_turns"],
        },
        "all_legs_independently_replayed":True,
        "native_hardware_certified":False,
        "original_project_files_mutated":False,
        "model_weights_promoted":False,
    }
    return {**body,"digest":_hash(body)}


def verify_original_npc_waypoint_mission(receipt):
    if type(receipt) is not dict or receipt.get("schema")!=SCHEMA:
        raise OriginalMissionError("exact original source waypoint mission schema required")
    try:
        expected=run_original_npc_waypoint_mission(
            receipt["starting_world"],receipt["waypoints"],
            max_steps_per_leg=receipt["max_steps_per_leg"],
        )
    except (KeyError,TypeError,ValueError,IndexError,RecursionError) as exc:
        raise OriginalMissionError("unverified source mission inputs or waypoint proof") from exc
    if expected!=receipt:
        raise OriginalMissionError("original mission witnesses, material or route history forged")
    return True


__all__ = [
    "SCHEMA","MAX_WAYPOINTS","OriginalMissionError",
    "run_original_npc_waypoint_mission","verify_original_npc_waypoint_mission",
]
