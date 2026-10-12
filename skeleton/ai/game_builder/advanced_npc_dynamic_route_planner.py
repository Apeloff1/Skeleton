"""Original dynamic NPC-world path planning with independently replayed actions.

This planner does not edit coordinates or teleport characters. Each proposed
move is actually executed with the source game's physical movement, full NPC
schedule, finite stamina and original witness rules. Occupancy is refreshed
after every real turn, and only fully replayable plans are accepted.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy

from .advanced_chunked_npc_world import (
    ChunkWorldError, DIRECTIONS, MAX_STEPS, PHASES, _act, _chunk,
    _dist, _hash, _lod_receipt, _neighbors, _schedule, _visible,
    verify_chunked_npc_world, run_chunked_npc_world,
)

SCHEMA = "skeleton.game_builder.original_dynamic_npc_route.v1"
MAX_PLANNED_STEPS = 72
MAX_STALE_TURNS = 5
OBJECTIVES = ("site", "npc", "cell")
EXTRA_ACTIONS = {
    "site": ("approach", "harvest", "repair", "claim"),
    "npc": ("approach", "speak", "observe", "support"),
    "cell": ("approach",),
}


class OriginalRouteError(ChunkWorldError):
    """No legal source-verified original route or source action exists."""


def _objective(spec, state):
    if type(spec) is not dict or set(spec) != {"kind", "index", "action"}:
        raise OriginalRouteError("goal requires exact kind, index and desired original action")
    kind, idx, action = spec["kind"], spec["index"], spec["action"]
    if (type(kind) is not str or kind not in OBJECTIVES
        or type(idx) is not int or idx < 0
        or type(action) is not str or action not in EXTRA_ACTIONS[kind]):
        raise OriginalRouteError("invalid source-bound physical objective")
    if kind == "site" and idx >= len(state["sites"]):
        raise OriginalRouteError("authored site does not exist")
    if kind == "npc" and idx >= len(state["actors"]):
        raise OriginalRouteError("original target citizen does not exist")
    if kind == "cell" and idx >= state["side"] ** 2:
        raise OriginalRouteError("original target tile exceeds actual world map")
    return dict(spec)


def _targets(state, objective):
    kind, index = objective["kind"], objective["index"]
    if kind == "site":
        target = state["sites"][index]["cell"]
    elif kind == "npc":
        target = state["actors"][index]["position"]
    else:
        target = index
    side = state["side"]
    blocked = set(state["obstacles"])
    occupied = {a["position"] for a in state["actors"]}
    if kind == "cell":
        return [target] if target not in blocked else []
    return [
        cell for cell in [target, *_neighbors(target, side)]
        if cell not in blocked and cell not in occupied
        and _dist(cell, target, side) <= 1
    ]


def _first_move(state, targets):
    """Shortest *current-frame* tile path; recalculate on every next frame."""
    side, start = state["side"], state["player"]
    available = set(targets)
    if start in available:
        return None
    blocked = (set(state["obstacles"]) |
               {a["position"] for a in state["actors"]})
    q = deque([start])
    parent = {start: None}
    reached = None
    while q:
        cell = q.popleft()
        for nxt in _neighbors(cell, side):
            if nxt in parent or nxt in blocked:
                continue
            parent[nxt] = cell
            if nxt in available:
                reached = nxt
                q.clear()
                break
            q.append(nxt)
        if reached is not None:
            break
    if reached is None:
        return False
    child = reached
    while parent[child] != start:
        child = parent[child]
    ax, ay = start % side, start // side
    bx, by = child % side, child // side
    vector = (bx - ax, by - ay)
    for name, offset in DIRECTIONS.items():
        if vector == offset:
            return "move:" + name
    raise OriginalRouteError("unphysical path step produced by original route search")


def _source(game):
    if type(game) is not dict:
        raise OriginalRouteError("full original reviewed game source required")
    try:
        if not verify_chunked_npc_world(game):
            raise OriginalRouteError("unverified original world action source")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise OriginalRouteError("forged original game source") from exc
    return game


def plan_original_dynamic_route(game, objective, *, max_steps=40):
    """Plan, execute on authentic simulation rules, then certify full replay."""
    original = _source(game)
    if type(max_steps) is not int or not 1 <= max_steps <= MAX_PLANNED_STEPS:
        raise OriginalRouteError("original route budget must be one to seventy-two")
    state = deepcopy(original["state"])
    opts = original["options"]
    rules = original["settings"]
    goal = _objective(objective, state)
    if state["finished"]:
        raise OriginalRouteError("ended original game has no playable world route")
    if state["tick"] + max_steps > min(MAX_STEPS, opts["max_turns"]):
        raise OriginalRouteError("route budget would exceed original world's finite turn cap")
    if (goal["kind"] == "cell"
        and goal["index"] in set(state["obstacles"])):
        raise OriginalRouteError("cannot navigate to impassable source-authored tile")
    previous = original["head_digest"]
    start_position = state["player"]
    planned = []
    proofs = []
    waits = 0
    replans = 0
    destination_reached = False
    interaction_performed = False

    for _ in range(max_steps):
        targets = _targets(state, goal)
        here = state["player"] in targets
        if here and goal["action"] == "approach":
            destination_reached = True
            break
        if here:
            if goal["kind"] == "site":
                command = goal["action"] + ":" + str(goal["index"])
            elif goal["kind"] == "npc":
                command = goal["action"] + ":" + str(goal["index"])
            else:
                raise OriginalRouteError("cell arrival requires no synthetic action")
        else:
            replans += 1
            command = _first_move(state, targets)
            if command is False:
                if waits >= MAX_STALE_TURNS:
                    raise OriginalRouteError("no physical route after bounded moving-body rechecks")
                waits += 1
                command = "wait"
            elif command is None:
                raise OriginalRouteError("route search produced a nonphysical arrival")
            elif state["inventory"]["stamina"] < rules["quest_director"]["movement_stamina"]:
                if (rules["quest_director"]["rest_stamina"] < 1 or
                    rules["quest_director"]["stamina"] <
                    rules["quest_director"]["movement_stamina"]):
                    raise OriginalRouteError("movement stamina cannot be restored to a legal amount")
                command = "rest"
        position_before = state["player"]
        before = _hash(state)
        scheduler_before = dict(state["scheduler"])
        detailed, _ = _visible(state, opts)
        try:
            events = _act(state, rules, opts, command, detailed)
            moves = _schedule(state, rules, opts)
        except (KeyError, TypeError, ValueError, ChunkWorldError) as exc:
            raise OriginalRouteError("planned physical action rejected by actual source mechanics") from exc
        state["last_events"] = events + (
            ["bounded_streamed_schedules_advanced"] if moves else [])
        index = len(original["commands"]) + len(planned)
        frame = {
            "step": index, "command": command, "tick": state["tick"],
            "previous": previous, "before": before,
            "causal_events": events, "physical_moves": moves,
            "lod_fidelity": _lod_receipt(state, scheduler_before),
            "after": _hash(state), "ordered_phases": list(PHASES),
        }
        frame["digest"] = _hash(frame)
        previous = frame["digest"]
        planned.append(command)
        proofs.append({
            "command":command,"turn":state["tick"],
            "from":position_before,"to":state["player"],
            "from_chunk":list(_chunk(position_before,state["side"])),
            "to_chunk":list(_chunk(state["player"],state["side"])),
            "source_frame":frame["digest"],
            "source_events":events,
            "npc_moves_count":len(moves),
            "actual_detailed_npcs":frame["lod_fidelity"]["actually_detailed"],
        })
        if here:
            interaction_performed = True
            destination_reached = True
            break
    if not destination_reached:
        destination_reached = state["player"] in _targets(state,goal)
    if not destination_reached:
        raise OriginalRouteError("bounded real source movement did not arrive")
    if goal["action"] != "approach" and not interaction_performed:
        raise OriginalRouteError("physical original objective was not actually performed")
    try:
        result = run_chunked_npc_world(
            original["commands"] + planned, rules,
            scenes=original["source_scenes"], seed=original["seed"],
            options=opts,
        )
    except (KeyError, TypeError, ValueError, ChunkWorldError) as exc:
        raise OriginalRouteError("independent original-world replay rejected planned actions") from exc
    if (result["state"] != state or result["head_digest"] != previous or
        len(result["trace"]) != len(original["trace"]) + len(planned) or
        result["trace"][:len(original["trace"])] != original["trace"] or
        any(a["source_frame"] != b["digest"] for a,b in zip(
            proofs, result["trace"][len(original["trace"]):]))
    ):
        raise OriginalRouteError("route execution diverged from canonical source gameplay")
    summary = {
        "player": state["player"], "tick": state["tick"],
        "inventory": deepcopy(state["inventory"]),
        "physically_embodied_npcs": len(state["actors"]),
        "quest_count":len(state["quests"]),
        "source_events":len(state["events"]),
        "physical_npc_moves":state["scheduler"]["physical_moves"],
        "earned_quests":state["completed"],
    }
    body = {
        "schema":SCHEMA, "source_game":original, "objective":goal,
        "max_steps":max_steps, "original_source_digest":original["digest"],
        "source_head":original["head_digest"],
        "generated_actions":planned, "actual_action_receipts":proofs,
        "replanning_attempts":replans, "blocked_waits":waits,
        "starting_player_cell":start_position,
        "arrived_at_source_objective":destination_reached,
        "performed_optional_real_interaction":interaction_performed,
        "result_world_digest":result["digest"],
        "result_head":result["head_digest"],
        "result_summary":summary,
        "entire_result_independently_replayed":True,
        "replanning_is_optimal_global_time_path":False,
        "source_project_mutated":False,
        "hardware_performance_certified":False,
        "model_weights_promoted":False,
    }
    return {**body,"digest":_hash(body)}


def verify_original_dynamic_route(record):
    if type(record) is not dict or record.get("schema") != SCHEMA:
        raise OriginalRouteError("source-authenticated original dynamic route record required")
    try:
        expected = plan_original_dynamic_route(
            record["source_game"], record["objective"],
            max_steps=record["max_steps"],
        )
    except (TypeError, KeyError, IndexError, ValueError, RecursionError) as exc:
        raise OriginalRouteError("malformed or forged original dynamic route input") from exc
    if record != expected:
        raise OriginalRouteError("original route, moving NPC or physical action proof was forged")
    return True


__all__ = [
    "SCHEMA","MAX_PLANNED_STEPS","OriginalRouteError",
    "plan_original_dynamic_route","verify_original_dynamic_route",
]
