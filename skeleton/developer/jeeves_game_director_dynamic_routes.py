"""Multi-layer, dynamically gated route solver for living Director worlds.

Unifies foot travel, ferries, shuttles, rail, portals, faction thresholds,
ticket consumption and world-state effects. Unlike graph-only navigation, a
route is a *series of legal actual Director transitions*, including changes
to reputation, flags, inventory and time. Results are never auto-executed.

Search budgets bound ONE request, never the number of worlds, moves or
training cycles. It explicitly records partial proofs and search exhaustion.
"""
from __future__ import annotations

from collections import Counter, deque
import heapq
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, available_director_actions, director_step,
)
from skeleton.developer.jeeves_game_director_session import _hash, _load, _read_doc
from skeleton.developer.jeeves_game_director_labyrinth import (
    PROFILES, _active_sites, _score,
)
from skeleton.ai.game_builder.quest_world_dynamics import WorldState

SCHEMA = "skeleton.jeeves.director_dynamic_routes.v1"
MAX_EXPANSIONS = 60000
MAX_FRONTIER = 120000
MAX_PATH_STEPS = 512


def _state_identity(world: Any, state: Any) -> tuple[Any, ...]:
    """State-space key includes all future social access permissions.

    Only discard absolute time after normalizing schedule phase and
    conversation cooldowns. Otherwise the planner could use an NPC who is
    away or speak twice in one calendar cycle. Transaction *counters* do not
    affect legality, but shop stock, balance, possessions and trust do.
    """
    status: WorldState = state.world_state
    if status is None:
        raise ValueError("dynamic search requires a canonical living-world state")
    social: tuple[Any, ...] = ()
    if status.society is not None:
        from skeleton.ai.game_builder.quest_society import phase
        society = world.dynamics.society
        clock = phase(society, state.turn)
        recent_talk = tuple(sorted(
            person for person, cycle in status.society.last_talk_cycle
            if cycle == clock["cycle"]
        ))
        social = (
            status.society.balance, status.society.relationships,
            status.society.shop_stock, status.society.owned,
            clock["phase_index"], state.turn % society.phase_turns,
            recent_talk,
        )
    return (
        state.scene, state.acquired, state.complete, state.narrative_flags,
        status.standings, status.world_flags, social,
    )


def _transport_details(world: Any, state: Any, action: DirectorAction) -> dict:
    if action.kind in {"speak", "discuss", "rest", "buy", "sell"}:
        rules = world.dynamics.society
        duration = rules.phase_turns if action.kind == "rest" else (
            2 if action.kind in {"buy", "sell"} else 1
        )
        return {
            "kind": action.kind, "transport_key": None,
            "mode": "market" if action.kind in {"buy", "sell"} else "social",
            "from": state.scene, "to": state.scene, "turns": duration,
            "resident_or_item": action.key,
            "consumes": None,
            "canonical_npc_or_economy_action": True,
        }
    if action.kind == "travel":
        return {"kind": "walk", "transport_key": None, "mode": "foot",
                "from": state.scene, "to": action.key, "turns": 1,
                "consumes": None}
    if world.dynamics is None:
        raise ValueError("world lacks transport rules")
    passage = next((x for x in world.dynamics.passages
                    if x.key == action.key), None)
    if passage is None:
        raise ValueError("requested passage is unknown")
    dest = passage.destination if passage.source == state.scene else passage.source
    return {
        "kind": "transit", "transport_key": passage.key,
        "mode": passage.mode, "name": passage.name,
        "from": state.scene, "to": dest,
        "turns": passage.cost_turns,
        "consumes": passage.consume_item,
        "reputation_delta": [list(x) for x in passage.reputation_change],
        "grants_world_flag": passage.grant_world_flag,
    }


def _step_cost(scene: Any, action: DirectorAction, details: dict,
               profile: str, visited: Counter[str],
               sites: set[str]) -> int:
    duration = int(details["turns"])
    penalty = _score(scene, profile, visited, sites)
    mode = details["mode"]
    if profile == "fastest":
        return duration
    if profile == "scenic":
        return duration * 10 + penalty
    if profile == "quiet":
        return duration * 10 + penalty + (
            80 if mode in {"plane", "airship", "rail"} else 0
        )
    if profile == "novel":
        return duration * 8 + penalty
    if profile == "quest":
        return duration * 15 + penalty
    raise ValueError("unknown travel profile")


def _expand(world: Any, state: Any, goal: set[str], *,
            profile: str, visited: Counter[str],
            sites: set[str], alternatives: int,
            optimize_hops: bool = False) -> tuple[list[dict], int, bool]:
    scenes = {s.key: s for s in world.scenes}
    # Each heap entry is a projected exact Director state and a journal-free
    # action witness; no model-generated text is ever accepted as permission.
    heap: list[tuple[int, int, int, Any, tuple[dict, ...], tuple[str, ...]]] = [
        (0, 0, 0, state, (), (state.scene,))
    ]
    serial = 0
    expansions = 0
    found: list[dict] = []
    best: dict[tuple[Any, ...], int] = {}
    exhausted = False
    while heap and len(found) < alternatives:
        if expansions >= MAX_EXPANSIONS or len(heap) > MAX_FRONTIER:
            exhausted = True
            break
        price, hops, _, at, steps, places = heapq.heappop(heap)
        expansions += 1
        signature = _state_identity(world, at)
        # Multiple independent paths to the *same goal* may be retained, but
        # prune dominated intermediate states so cyclic worlds cannot explode.
        previous = best.get(signature)
        if previous is not None and price > previous and at.scene not in goal:
            continue
        if at.scene in goal:
            outcome = {
                "places": list(places),
                "steps": list(steps),
                "actions": [x["choice"] for x in steps],
                "destination": at.scene,
                "hops": hops,
                "travel_hops": sum(x["kind"] in {"walk", "transit"} for x in steps),
                "social_and_market_actions": [
                    x["choice"] for x in steps
                    if x["kind"] in {"speak", "discuss", "rest", "buy", "sell"}
                ],
                "turn_cost": at.turn - state.turn,
                "policy_cost": price,
                "expected_arrival_state_sha256": at.digest,
                "reputation_after": [list(x) for x in at.world_state.standings],
                "world_flags_after": list(at.world_state.world_flags),
                "inventory_after": list(at.acquired),
                "society_after": at.world_state.society.payload()
                                 if at.world_state.society else None,
                "transport_modes": sorted({x["mode"] for x in steps}),
                "gate_rules_actually_evaluated": True,
                "canonical_actions_replayed": True,
            }
            if not any(x["actions"] == outcome["actions"] for x in found):
                found.append(outcome)
            continue
        if len(steps) >= MAX_PATH_STEPS:
            exhausted = True
            continue
        if previous is not None and price > previous:
            continue
        best[signature] = price
        for action in available_director_actions(world, at):
            if action.kind not in {
                    "travel", "transit", "speak", "discuss", "buy", "sell", "rest"}:
                continue
            details = _transport_details(world, at, action)
            next_state = director_step(world, at, action)
            next_signature = _state_identity(world, next_state)
            extra = (1 if optimize_hops else _step_cost(
                scenes[next_state.scene], action, details,
                profile, visited, sites,
            ))
            new_price = price + extra
            if (next_signature == signature
                    or (next_signature in best and
                        new_price > best[next_signature])):
                continue
            serial += 1
            step = {"choice": action.kind + ":" + action.key, **details,
                    "prior_state_sha256": at.digest,
                    "after_state_sha256": next_state.digest}
            if at.world_state.society is not None:
                before_society = at.world_state.society
                after_society = next_state.world_state.society
                step["wallet_change"] = (
                    after_society.balance - before_society.balance)
                step["trust_changes"] = [{
                    "resident": npc, "before": score,
                    "after": dict(after_society.relationships)[npc],
                } for npc, score in before_society.relationships
                    if dict(after_society.relationships)[npc] != score]
            heapq.heappush(
                heap, (new_price, hops + 1, serial, next_state,
                       steps + (step,), places + (next_state.scene,)),
            )
    return found, expansions, exhausted


def plan(root: Path, *, session: str, destination: str | None = None,
         profile: str = "fastest", alternatives: int = 3
         ) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError("unknown living-world navigation profile")
    if type(alternatives) is not int or not 1 <= alternatives <= 8:
        raise ValueError("living-world route preview supports 1..8 alternatives")
    folder, world, state, source, head, count = _load(root, name=session)
    if world.dynamics is None or state.world_state is None:
        raise ValueError("living-world route planner requires approved dynamic-world data")
    scenes = {scene.key: scene for scene in world.scenes}
    sites, goals = _active_sites(world, state)
    if destination is None:
        destinations = sites
    else:
        if not isinstance(destination, str) or destination not in scenes:
            raise ValueError("target scene does not belong to this approved world")
        destinations = {destination}
    if not destinations:
        raise ValueError("no open authored quest objective")
    visited = Counter({world.starting_scene: 1})
    for i in range(1, count + 1):
        entry = _read_doc(folder / f"{i:08d}.json")
        if entry["action"]["kind"] == "travel":
            visited[entry["action"]["key"]] += 1
        elif entry["action"]["kind"] == "transit":
            # The previous leg's exact scene is replayed by _load; count
            # transit journeys separately in the world-state report.
            continue
    routes, scanned, exhausted = _expand(
        world, state, destinations, profile=profile, visited=visited,
        sites=sites, alternatives=alternatives,
    )
    if not routes:
        # Even negative/incomplete results are tied to the EXACT journal head
        # and source. Never serve a stale locked-passage claim to the client.
        _, current_world, current_state, current_source, current_head, current_count = _load(
            root, name=session)
        if (current_world.digest != world.digest
                or current_state.digest != state.digest or current_head != head
                or current_count != count
                or current_source["source_sha256"] != source["source_sha256"]):
            raise ValueError("living game changed during negative route search")
        # No route found under the bounded search is not proof of topological
        # impossibility; future factions, keys or quests could unlock one.
        status = "search_exhausted" if exhausted else "unreachable_with_current_permissions"
        return {
            "ok": True, "action": "director-route", "schema": SCHEMA,
            "session": session, "world_sha256": world.digest,
            "source_sha256": source["source_sha256"],
            "session_head_sha256": head, "session_sequence": count,
            "state_sha256": state.digest, "from_scene": state.scene,
            "requested_destination": destination, "profile": profile,
            "routes": [], "route_count": 0, "status": status,
            "blocked_by_current_rules": True,
            "search_expansions": scanned, "search_budget_exhausted": exhausted,
            "all_possible_labyrinth_paths_enumerated": False,
            "gameplay_actions_executed": False,
        }
    # Compute a reference fastest-HOP permitted route, which may use
    # item-consuming, reputation-changing transit. It is not the same
    # as the shortest static graph or guaranteed optimal turn-count.
    reference, ref_scanned, ref_exhausted = _expand(
        world, state, destinations, profile="fastest", visited=visited,
        sites=sites, alternatives=1, optimize_hops=True,
    )
    baseline = reference[0]["hops"] if reference else None
    for candidate in routes:
        candidate["shortest_reference_hops"] = baseline
        candidate["hops_above_reference"] = (
            candidate["hops"] - baseline if baseline is not None else None
        )
        candidate["distinct_regions"] = sorted({
            scenes[k].region for k in candidate["places"]
        })
        candidate["scenes_not_previously_visited"] = sorted({
            key for key in candidate["places"][1:] if not visited[key]
        })
        candidate["route_sha256"] = _hash({
            "world": world.digest, "source": source["source_sha256"],
            "session_head": head, "state": state.digest,
            "profile": profile, "steps": candidate,
        })
    _, check_world, check_state, check_source, check_head, check_count = _load(
        root, name=session)
    if (check_world.digest != world.digest or check_source["source_sha256"] != source["source_sha256"]
            or check_state.digest != state.digest or check_head != head
            or check_count != count):
        raise ValueError("living game advanced during route proof; recompute before moving")
    return {
        "ok": True, "action": "director-route", "schema": SCHEMA,
        "session": session, "world_sha256": world.digest,
        "source_sha256": source["source_sha256"], "session_sequence": count,
        "session_head_sha256": head, "state_sha256": state.digest,
        "from_scene": state.scene, "profile": profile,
        "requested_destination": destination,
        "targeted_active_quests": goals if destination is None else [],
        "routes": routes, "route_count": len(routes),
        "status": "sampled_routes", "search_expansions": scanned,
        "reference_search_expansions": ref_scanned,
        "reference_search_incomplete": ref_exhausted,
        "search_budget_exhausted": exhausted,
        "faction_and_resource_states_simulated": True,
        "transit_modes_replayed": sorted({m for r in routes for m in r["transport_modes"]}),
        "all_possible_labyrinth_paths_enumerated": False,
        "gameplay_actions_executed": False, "native_engine_pathfinding_verified": False,
    }
