"""Original NPC conditional missions with player-acquired evidence, not omniscience.

Bounded AND / OR / NOT gates evaluate only original player-accessible facts:
the player's own harvested events, directly heard firsthand testimony,
material support actually paid, verified quest resolution, own finite
inventory and actual world turn. Goals execute through the existing
source-replaying physical waypoint engine; discarded alternatives never
become game actions or model training.
"""
from __future__ import annotations

from copy import deepcopy

from .advanced_chunked_npc_world import (
    ChunkWorldError, _hash, run_chunked_npc_world, verify_chunked_npc_world,
)
from .advanced_npc_waypoint_mission import (
    OriginalMissionError, run_original_npc_waypoint_mission,
)

SCHEMA = "skeleton.game_builder.original_conditional_npc_mission.v1"
MAX_NODES = 12
MAX_GOALS = 12
MAX_GUARD_NODES = 31
MAX_GUARD_DEPTH = 5

ACTOR_PREDICATES = {"firsthand_testimony", "paid_support"}
SITE_PREDICATES = {"own_harvest_at_site", "site_quest_resolved"}
AMOUNT_PREDICATES = {
    "supplies_at_least": "supplies",
    "stamina_at_least": "stamina",
    "influence_at_least": "influence",
}
OTHER_PREDICATES = {"turn_at_most", "earned_quests_at_least"}


class OriginalConditionalMissionError(OriginalMissionError):
    """A proposed condition, real action or source replay was invalid."""


def _int(value, highest, label):
    if type(value) is not int or not 0 <= value <= highest:
        raise OriginalConditionalMissionError(
            "strict bounded original conditional mission " + label
        )
    return value


def _guard(node, game, *, depth=0, counter=None):
    """Produce a reproducible Boolean answer and inspectable player-knowledge proof."""
    if counter is None:
        counter = [0]
    counter[0] += 1
    if (counter[0] > MAX_GUARD_NODES or depth > MAX_GUARD_DEPTH or
        type(node) is not dict or len(node) != 1):
        raise OriginalConditionalMissionError(
            "bounded exact Boolean guard tree required"
        )
    kind, arg = next(iter(node.items()))
    if kind in ("all", "any"):
        if type(arg) is not list or not 1 <= len(arg) <= 6:
            raise OriginalConditionalMissionError(
                "Boolean guard must have one to six authentic branches"
            )
        children = [
            _guard(child, game, depth=depth+1, counter=counter)
            for child in arg
        ]
        # Explicitly evaluate every guard: evidence never depends on
        # language/runtime short-circuit, side effects or hidden ordering.
        values = [item["satisfied"] for item in children]
        result = all(values) if kind == "all" else any(values)
        return {"operator":kind, "satisfied":result, "evidence":children}
    if kind == "not":
        child = _guard(arg, game, depth=depth+1, counter=counter)
        return {"operator":"not", "satisfied":not child["satisfied"],
                "evidence":child}
    if kind != "fact" or type(arg) is not dict:
        raise OriginalConditionalMissionError("non-player-knowledge guard operator")
    predicate = arg.get("predicate")
    s = game["state"]
    detail = {}
    if predicate in ACTOR_PREDICATES:
        if set(arg) != {"predicate", "actor"}:
            raise OriginalConditionalMissionError("exact original NPC fact requires actor ID")
        index = _int(arg["actor"],len(s["actors"])-1,"actor ID")
        actor_id = "original_chunk_npc:%03d" % index
        if predicate == "firsthand_testimony":
            matches = [
                d for d in s["dialogues"]
                if d["actor"] == actor_id and
                   d["source"] == "firsthand_physical_witness" and
                   d["event_id"] is not None
            ]
            detail = {"actor":index, "directly_heard_event_ids":
                      [d["event_id"] for d in matches]}
        else:
            matches = [c for c in s["choices"] if c["actor"] == actor_id]
            detail = {"actor":index, "actual_paid_choice_count":len(matches)}
        result = bool(matches)
    elif predicate in SITE_PREDICATES:
        if set(arg) != {"predicate", "site"}:
            raise OriginalConditionalMissionError("exact original site evidence required")
        index = _int(arg["site"],len(s["sites"])-1,"source site")
        if predicate == "own_harvest_at_site":
            facts = [
                e["id"] for e in s["events"]
                if e["kind"] == "harvest" and e["site"] == index
            ]
            detail = {"site":index, "actual_player_harvest_events":facts}
            result = bool(facts)
        else:
            facts = [
                q["id"] for q in s["quests"]
                if q["site"] == index and q["status"] == "resolved"
            ]
            detail = {"site":index, "actually_resolved_quest_ids":facts}
            result = bool(facts)
    elif predicate in AMOUNT_PREDICATES:
        if set(arg) != {"predicate", "amount"}:
            raise OriginalConditionalMissionError("exact player inventory threshold required")
        threshold = _int(arg["amount"],65535,"finite inventory threshold")
        resource = AMOUNT_PREDICATES[predicate]
        actual = s["inventory"][resource]
        detail = {"resource":resource,"actual_amount":actual,
                  "required_amount":threshold}
        result = actual >= threshold
    elif predicate in OTHER_PREDICATES:
        if set(arg) != {"predicate", "amount"}:
            raise OriginalConditionalMissionError("exact clock or earned-quest threshold required")
        threshold = _int(arg["amount"],128,"actual world time or quest limit")
        actual = s["tick"] if predicate == "turn_at_most" else s["completed"]
        detail = {"actual":actual,"threshold":threshold}
        result = actual <= threshold if predicate == "turn_at_most" else actual >= threshold
    else:
        raise OriginalConditionalMissionError("unguarded external or unseen NPC knowledge is forbidden")
    return {"operator":"fact", "predicate":predicate, "satisfied":result,
            "evidence":detail, "original_world_head":game["head_digest"]}


def _goal(value):
    if type(value) is not dict or set(value) != {"kind","index","action"}:
        raise OriginalConditionalMissionError("only real typed physical waypoint goals")
    if (type(value["kind"]) is not str or
        type(value["index"]) is not int or
        type(value["action"]) is not str):
        raise OriginalConditionalMissionError("physical waypoint fields must be exact types")
    return deepcopy(value)


def _program(program):
    if type(program) is not list or not 1 <= len(program) <= MAX_NODES:
        raise OriginalConditionalMissionError("one to twelve bounded original mission steps required")
    checked = []
    total = 0
    for node in program:
        if type(node) is not dict or len(node) != 1:
            raise OriginalConditionalMissionError("exact conditional or physical goal node")
        if "goal" in node:
            checked.append({"goal":_goal(node["goal"])})
            total += 1
        elif "when" in node:
            spec = node["when"]
            if (type(spec) is not dict or
                set(spec) != {"if","then","otherwise"} or
                type(spec["then"]) is not list or
                type(spec["otherwise"]) is not list or
                len(spec["then"]) > 12 or len(spec["otherwise"]) > 12):
                raise OriginalConditionalMissionError("exact bounded if/then/otherwise goal branch")
            checked.append({"when":{
                "if":deepcopy(spec["if"]),
                "then":[_goal(x) for x in spec["then"]],
                "otherwise":[_goal(x) for x in spec["otherwise"]],
            }})
            total += max(len(spec["then"]),len(spec["otherwise"]))
        else:
            raise OriginalConditionalMissionError("unsupported original conditional node")
        if total > MAX_GOALS:
            raise OriginalConditionalMissionError("possible original itinerary exceeds twelve goals")
    return checked


def run_original_conditional_mission(game, program, *, max_steps_per_goal=24):
    if type(max_steps_per_goal) is not int or not 1 <= max_steps_per_goal <= 72:
        raise OriginalConditionalMissionError("finite per-goal original turn budget 1..72")
    steps = _program(program)
    if type(game) is not dict:
        raise OriginalConditionalMissionError("source-authenticated original world required")
    try:
        if not verify_chunked_npc_world(game):
            raise OriginalConditionalMissionError("original world did not fully replay")
    except (ChunkWorldError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise OriginalConditionalMissionError("untrusted original conditional world") from exc
    current = game
    executed = []
    evaluations = []
    full_actions = []
    for step_index, step in enumerate(steps):
        if "goal" in step:
            selected = [step["goal"]]
            decision = None
        else:
            clause = step["when"]
            verdict = _guard(clause["if"], current)
            selected = clause["then"] if verdict["satisfied"] else clause["otherwise"]
            rejected = clause["otherwise"] if verdict["satisfied"] else clause["then"]
            decision = {
                "source_program_step":step_index,
                "source_head_before_decision":current["head_digest"],
                "original_player_knowledge":verdict,
                "branch_taken":"then" if verdict["satisfied"] else "otherwise",
                "executed_source_goals":deepcopy(selected),
                "discarded_unexecuted_goals":deepcopy(rejected),
                "unselected_goals_never_simulated":True,
            }
            decision["digest"] = _hash(decision)
            evaluations.append(decision)
        for subindex, goal in enumerate(selected):
            before = current
            # Each leg is run by the existing verified game route and quest
            # engine, not a forged command assembly or unrelated world.
            remaining = min(
                max_steps_per_goal,
                before["options"]["max_turns"]-len(before["commands"]),
                128-len(before["commands"]),
            )
            if remaining < 1:
                raise OriginalConditionalMissionError(
                    "original finite world exhausted before selected goal"
                )
            try:
                itinerary = run_original_npc_waypoint_mission(
                    before,[goal],max_steps_per_leg=remaining
                )
                actions = itinerary["generated_actions"]
                after = run_chunked_npc_world(
                    before["commands"]+actions,before["settings"],
                    scenes=before["source_scenes"],seed=before["seed"],
                    options=before["options"],
                )
            except (ChunkWorldError, OriginalMissionError, ValueError,
                    KeyError, TypeError, IndexError) as exc:
                raise OriginalConditionalMissionError(
                    "conditional step %d selected a physically impossible goal" % step_index
                ) from exc
            if (after["digest"] != itinerary["final_world_digest"] or
                after["head_digest"] != itinerary["final_source_head"] or
                len(after["commands"]) != len(before["commands"])+len(actions) or
                not verify_chunked_npc_world(after)):
                raise OriginalConditionalMissionError(
                    "conditional branch diverged from full source replay"
                )
            before_state, final = before["state"], after["state"]
            item = {
                "step":step_index,"branch_goal":subindex,
                "selected_actual_goal":deepcopy(goal),
                "origin_source_head":before["head_digest"],
                "outcome_source_head":after["head_digest"],
                "real_actions":list(actions),
                "mission_leg_digest":itinerary["legs"][0]["digest"],
                "real_source_quest_delta":final["completed"]-before_state["completed"],
                "real_player_inventory_delta":{
                    key:final["inventory"][key]-before_state["inventory"][key]
                    for key in sorted(final["inventory"])
                },
                "new_firsthand_dialogues":len(final["dialogues"])-len(before_state["dialogues"]),
                "new_paid_social_choices":len(final["choices"])-len(before_state["choices"]),
                "new_physical_events":len(final["events"])-len(before_state["events"]),
                "source_game_digest":after["digest"],
                "all_physical_actions_independently_replayed":True,
            }
            item["digest"] = _hash(item)
            executed.append(item)
            full_actions.extend(actions)
            current = after
    final = current["state"]
    # A final independent full-source replay validates all decision choices
    # as executed original commands. Guard decisions are recomputed by
    # the standalone verifier from those authoritative states.
    from_genesis = run_chunked_npc_world(
        game["commands"]+full_actions,game["settings"],
        scenes=game["source_scenes"],seed=game["seed"],
        options=game["options"],
    )
    if from_genesis != current:
        raise OriginalConditionalMissionError("final game receipts differ from actual original source")
    body = {
        "schema":SCHEMA,
        "starting_world":game,
        "starting_world_digest":game["digest"],
        "program":steps,
        "max_steps_per_goal":max_steps_per_goal,
        "evaluated_conditional_nodes":evaluations,
        "actual_goal_executions":executed,
        "physical_actions":full_actions,
        "executed_goal_count":len(executed),
        "decision_count":len(evaluations),
        "final_world_digest":current["digest"],
        "final_source_head":current["head_digest"],
        "result":{
            "world_tick":final["tick"],
            "physical_npcs":len(final["actors"]),
            "real_quest_milestones":final["completed"],
            "real_harvested_events":len(final["events"]),
            "real_firsthand_testimonies":sum(
                x["source"]=="firsthand_physical_witness"
                for x in final["dialogues"]
            ),
            "real_paid_support_actions":len(final["choices"]),
            "player_position":final["player"],
            "inventory":deepcopy(final["inventory"]),
            "detailed_npc_updates":final["scheduler"]["detailed_updates"],
            "deferred_npc_turns":final["scheduler"]["deferred_actor_turns"],
        },
        "only_player_acquired_knowledge_controls_branches":True,
        "discarded_branches_not_simulated":True,
        "model_weights_promoted":False,
        "original_project_mutated":False,
        "native_hardware_certified":False,
    }
    return {**body,"digest":_hash(body)}


def verify_original_conditional_mission(record):
    if type(record) is not dict or record.get("schema") != SCHEMA:
        raise OriginalConditionalMissionError("exact original conditional mission receipt required")
    try:
        expected = run_original_conditional_mission(
            record["starting_world"],record["program"],
            max_steps_per_goal=record["max_steps_per_goal"],
        )
    except (KeyError,IndexError,TypeError,ValueError,RecursionError) as exc:
        raise OriginalConditionalMissionError("invalid source evidence or conditional mission input") from exc
    if record != expected:
        raise OriginalConditionalMissionError("conditional witness, branch, resources or quest proof forged")
    return True


__all__ = [
    "SCHEMA","OriginalConditionalMissionError",
    "run_original_conditional_mission","verify_original_conditional_mission",
]
