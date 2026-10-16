"""Directed labyrinth routing for verified interactive Director campaigns.

Computes useful, differentiated paths (fast, atmospheric, quiet, unvisited,
quest-oriented), but never invents teleporters, gates or unavailable actions.
All suggestions are replayed through the real Director transition function
and bound to the *exact* journal head. Does not modify user saves.
"""
from __future__ import annotations

from collections import Counter, deque
import heapq
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, available_director_actions, director_step,
)
from skeleton.developer.jeeves_game_director_session import (
    _hash, _load, _read_doc,
)

SCHEMA = "skeleton.jeeves.director_labyrinth.v1"
PROFILES = ("fastest", "scenic", "quiet", "novel", "quest")
MAX_EXPANSIONS = 40000


def _graph(world: Any) -> dict[str, tuple[str, ...]]:
    names = {scene.key for scene in world.scenes}
    result = {scene.key: tuple(sorted(scene.links)) for scene in world.scenes}
    if any(destination not in names for edges in result.values() for destination in edges):
        raise ValueError("labyrinth contains broken authored links")
    return result


def _visits(folder: Path, count: int) -> Counter[str]:
    visits: Counter[str] = Counter()
    for index in range(1, count + 1):
        item = _read_doc(folder / f"{index:08d}.json")
        if item["action"]["kind"] == "travel":
            visits[item["action"]["key"]] += 1
    return visits


def _score(scene: Any, profile: str, visits: Counter[str],
           active_quest_sites: set[str]) -> int:
    """Strictly positive additive penalties for deterministic bounded search."""
    weather = scene.weather.lower()
    if profile == "fastest":
        return 100
    if profile == "scenic":
        return max(24, 95 - min(45, 9 * len(scene.cast)
                               + 5 * len(scene.props) + 4 * len(scene.cutscenes)))
    if profile == "quiet":
        return 100 + (155 if any(x in weather for x in ("storm", "rain", "wind"))
                      else 12 if "snow" in weather else 0)
    if profile == "novel":
        return 60 + min(220, visits[scene.key] * 45)
    if profile == "quest":
        return 54 if scene.key in active_quest_sites else 130
    raise ValueError("unknown labyrinth travel profile")


def _search(graph: dict[str, tuple[str, ...]], lookup: dict[str, Any],
            start: str, destinations: set[str], profile: str,
            visits: Counter[str], active_sites: set[str],
            limit: int) -> tuple[list[tuple[int, tuple[str, ...]]], int, bool]:
    # The heap holds *simple* paths; this can be exponential in a dense world.
    # The bounded per-query search is an honest resource guard, never a
    # lifetime/world-generation limit. Incomplete searches are labeled.
    queue: list[tuple[int, int, tuple[str, ...]]] = [(0, 0, (start,))]
    winners: list[tuple[int, tuple[str, ...]]] = []
    expanded = 0
    while queue and expanded < MAX_EXPANSIONS and len(winners) < limit:
        cost, hops, path = heapq.heappop(queue)
        expanded += 1
        here = path[-1]
        if here in destinations:
            winners.append((cost, path))
            continue
        for next_scene in graph[here]:
            if next_scene in path:
                continue
            edge_cost = _score(lookup[next_scene], profile, visits, active_sites)
            heapq.heappush(queue, (cost + edge_cost, hops + 1, path + (next_scene,)))
    return winners, expanded, bool(queue and expanded >= MAX_EXPANSIONS)


def _active_sites(world: Any, state: Any) -> tuple[set[str], list[dict[str, str]]]:
    resolved = set(state.complete)
    positions = dict(state.stage_index)
    sites: set[str] = set()
    goals = []
    for quest in world.quests:
        index = positions[quest.key]
        if index >= len(quest.stages) or not set(quest.requires_quests).issubset(resolved):
            continue
        stage = quest.stages[index]
        sites.update(stage.scene_ids)
        goals.append({"quest": quest.key, "stage": stage.key,
                      "title": stage.title})
    return sites, goals


def plan(root: Path, *, session: str, destination: str | None = None,
         profile: str = "fastest", alternatives: int = 3
         ) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError("route profile must be fastest, scenic, quiet, novel or quest")
    if type(alternatives) is not int or not 1 <= alternatives <= 8:
        raise ValueError("1..8 alternative paths can be displayed per request")
    folder, world, state, source, head, sequence = _load(root, name=session)
    graph = _graph(world)
    lookup = {scene.key: scene for scene in world.scenes}
    active_sites, goals = _active_sites(world, state)
    if destination is not None:
        if not isinstance(destination, str) or destination not in graph:
            raise ValueError("target location absent from approved original-game world")
        destinations = {destination}
    else:
        if not active_sites:
            raise ValueError("no active quest stage to navigate toward")
        destinations = active_sites
    visits = _visits(folder, sequence)
    winners, expanded, exhausted = _search(
        graph, lookup, state.scene, destinations, profile,
        visits, active_sites, alternatives)
    if not winners:
        raise ValueError("no navigable route to requested scene or active quest objective")
    paths = []
    for total, route in winners:
        checked = state
        actions = []
        for next_scene in route[1:]:
            step = DirectorAction("travel", next_scene, checked.scene)
            if step not in available_director_actions(world, checked):
                raise ValueError("planner path contains an unapproved game action")
            checked = director_step(world, checked, step)
            actions.append(step.kind + ":" + step.key)
        # Moving must not secretly modify quests, player inventory or canon.
        if (checked.results != state.results or checked.acquired != state.acquired
                or checked.narrative_flags != state.narrative_flags):
            raise ValueError("route simulation modified canonical quest outcomes")
        detail = {
            "places": list(route), "actions": actions,
            "destination": route[-1], "hops": len(actions),
            "policy_cost": total,
            "expected_arrival_state_sha256": checked.digest,
            "distinct_regions": sorted({lookup[x].region for x in route}),
            "scenes_not_previously_visited": sorted(
                x for x in route[1:] if visits[x] == 0
            ),
            "canonical_actions_replayed": True,
        }
        detail["route_sha256"] = _hash({
            "world": world.digest, "head": head, "from": state.digest,
            "profile": profile, "route": detail,
        })
        paths.append(detail)
    # Any concurrent game turn invalidates every recommendation before return.
    _, _, current, current_source, current_head, current_sequence = _load(
        root, name=session)
    if (current_head != head or current.digest != state.digest
            or current_sequence != sequence or
            current_source["source_sha256"] != source["source_sha256"]):
        raise ValueError("gameplay changed while finding a route; request a new plan")
    return {
        "ok": True, "action": "director-route", "schema": SCHEMA,
        "session": session, "world_sha256": world.digest,
        "source_sha256": source["source_sha256"],
        "session_sequence": sequence, "session_head_sha256": head,
        "state_sha256": state.digest, "from_scene": state.scene,
        "profile": profile, "requested_destination": destination,
        "targeted_active_quests": goals if destination is None else [],
        "routes": paths, "route_count": len(paths),
        "search_expansions": expanded, "search_budget_exhausted": exhausted,
        "all_possible_labyrinth_paths_enumerated": False,
        "gameplay_actions_executed": False,
        "native_engine_camera_or_pathfinding_verified": False,
    }


def topology(root: Path, *, source: str) -> dict[str, Any]:
    """Static directed-graph and quest-placement scrutiny for authored mazes."""
    from skeleton.developer.jeeves_game_production_board import _load_world
    from skeleton.developer.jeeves_game_quality import _read
    world, sha = _load_world(root, source)
    graph = _graph(world)
    scenes = {scene.key: scene for scene in world.scenes}
    incoming: Counter[str] = Counter(
        neighbor for links in graph.values() for neighbor in links)
    out = []
    one_way = []
    non_reaching = []
    for scene_id in sorted(graph):
        seen = {scene_id}
        pending = deque([scene_id])
        while pending:
            at = pending.popleft()
            for neighbor in graph[at]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        if world.starting_scene not in seen:
            non_reaching.append(scene_id)
        for neighbor in graph[scene_id]:
            if scene_id not in graph[neighbor]:
                one_way.append({"from": scene_id, "to": neighbor})
        out.append({
            "scene": scene_id, "region": scenes[scene_id].region,
            "out_degree": len(graph[scene_id]), "in_degree": incoming[scene_id],
            "reachable_scene_count": len(seen),
            "dead_end": not bool(graph[scene_id]),
            "can_return_to_start": world.starting_scene in seen,
        })
    from_start = set()
    q = deque([world.starting_scene])
    while q:
        at = q.popleft()
        if at in from_start:
            continue
        from_start.add(at)
        q.extend(graph[at])
    quest_holes = [
        {"quest": quest.key, "stage": stage.key,
         "unreachable_places": sorted(set(stage.scene_ids) - from_start)}
        for quest in world.quests for stage in quest.stages
        if set(stage.scene_ids) - from_start
    ]
    if _read(root, source, 16 * 1024 * 1024)[1] != sha:
        raise ValueError("authored world changed during topology inspection")
    return {
        "ok": True, "action": "director-topology", "schema": SCHEMA,
        "project": world.project_id, "source_sha256": sha,
        "world_sha256": world.digest,
        "scenes": out, "scene_count": len(out),
        "one_way_links": one_way,
        "unreachable_from_start": sorted(set(graph) - from_start),
        "cannot_return_to_start": sorted(non_reaching),
        "quest_placement_gaps": quest_holes,
        "all_scenes_accessible_from_start": len(from_start) == len(graph),
        "fully_strongly_connected": not non_reaching and len(from_start) == len(graph),
        "labyrinth_design_quality_independently_verified": False,
    }
