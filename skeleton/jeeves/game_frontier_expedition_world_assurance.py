"""Seven executable source-bound game production checks in the canonical Jeeves owner.

The world and session engines remain authoritative. Diagnostic evidence is
neither native execution nor release, copyright, device, or model-weight signoff.
"""
from __future__ import annotations
from collections import Counter, deque
from dataclasses import replace
from math import hypot
from typing import Mapping

from .game_frontier_expedition import (
    ExpeditionError, ExpeditionWorld, Traveler, _digest, find_route, verify_route,
)
from .game_frontier_expedition_narrative import StoryBook
from .game_frontier_expedition_quests import QuestBook

SCHEMA = "skeleton.game.world_assurance.v1"
AXES = ("geometry", "connectivity", "resilience", "capability",
        "playthrough", "canon", "adversarial")


def _graph(world):
    graph = {node.waypoint_id: [] for node in world.waypoints}
    for edge in sorted(world.by_edge.values(), key=lambda e: e.edge_id):
        graph[edge.source].append((edge.target, edge.edge_id))
    return graph


def _reachable(graph, start, *, omit=None, depth_first=False):
    if depth_first:
        stack, seen = [start], set()
        while stack:
            point = stack.pop()
            if point not in seen:
                seen.add(point)
                stack.extend(dest for dest, eid in graph[point] if eid != omit)
        return seen
    queue, seen = deque((start,)), {start}
    while queue:
        for dest, eid in graph[queue.popleft()]:
            if eid != omit and dest not in seen:
                seen.add(dest)
                queue.append(dest)
    return seen


def _seal(world, axis, details):
    record = {"schema": SCHEMA + "." + axis,
              "world_digest": world.digest, **details}
    return {**record, "receipt_digest": _digest(record)}


def _validate(world, player, story, quests):
    if not (isinstance(world, ExpeditionWorld)
            and isinstance(player, Traveler)
            and isinstance(story, StoryBook)
            and isinstance(quests, QuestBook)):
        raise ExpeditionError("world assurance requires canonical typed source")
    if (story.world_digest != world.digest
            or quests.world_digest != world.digest
            or quests.story_digest != story.digest):
        raise ExpeditionError("foreign world, story or quest source rejected")
    if (len(world.waypoints) > 4096 or len(world.by_edge) > 16384
            or len(world.destinations) > 16):
        raise ExpeditionError("world assurance exceeded bounded graph budget")
    story.validate_world(world)
    if any(stage.waypoint not in world.by_id
           for quest in quests.quests for stage in quest.stages):
        raise ExpeditionError("quest stage references nonexistent authored region")


def geometry(world):
    """1: Survey actual virtual coordinates and suspect nonportal shortcuts."""
    points = world.by_id
    edges = sorted(world.by_edge.values(), key=lambda e: e.edge_id)
    suspect, length = [], 0.0
    for edge in edges:
        a, b = points[edge.source], points[edge.target]
        distance = hypot(hypot(a.x_m-b.x_m, a.y_m-b.y_m),
                         a.altitude_m-b.altitude_m)
        length += distance
        if edge.mode != "portal" and edge.length_m < distance * .5:
            suspect.append(edge.edge_id)
    return _seal(world, "geometry", {
        "nodes": len(points), "edges": len(edges),
        "bounds_m": {key: [min(getattr(x, key) for x in points.values()),
                           max(getattr(x, key) for x in points.values())]
                     for key in ("x_m", "y_m", "altitude_m")},
        "region_types": dict(sorted(Counter(x.kind for x in points.values()).items())),
        "travel_modes": dict(sorted(Counter(x.mode for x in edges).items())),
        "euclidean_sum_m": round(length, 3),
        "nonportal_shortcut_review": suspect,
        "physical_gps_used": False, "native_physics_verified": False,
    })


def connectivity(world):
    """2: Directed reachable/stranded nodes and goal-backtracking coverage."""
    graph = _graph(world)
    forward = _reachable(graph, world.arrival)
    reverse = {node: [] for node in graph}
    for src, edges in graph.items():
        for dest, eid in edges:
            reverse[dest].append((src, eid))
    can_finish = set()
    for goal in world.destinations:
        can_finish |= _reachable(reverse, goal)
    return _seal(world, "connectivity", {
        "reachable": sorted(forward),
        "unreachable": sorted(set(graph)-forward),
        "accessible_goals": sorted(forward & set(world.destinations)),
        "cannot_reach_goal": sorted(set(graph)-can_finish),
        "non_goal_dead_ends": sorted(node for node, edges in graph.items()
                                     if not edges and node not in world.destinations),
        "capability_aware": False,
    })


def resilience(world, *, max_probes=192):
    """3: Cut real route edges and find goal-isolating failure points."""
    if type(max_probes) is not int or not 1 <= max_probes <= 512:
        raise ExpeditionError("resilience edge probes must be finite")
    graph = _graph(world)
    edges = sorted(world.by_edge.values(), key=lambda e: e.edge_id)
    stride = max(1, (len(edges)+max_probes-1)//max_probes)
    checked = edges[::stride][:max_probes]
    goals = set(world.destinations) & _reachable(graph, world.arrival)
    cut = []
    for edge in checked:
        lost = sorted(goals-_reachable(graph, world.arrival, omit=edge.edge_id))
        if lost:
            cut.append({"edge": edge.edge_id, "lost_goals": lost})
    return _seal(world, "resilience", {
        "checked_edges": [edge.edge_id for edge in checked],
        "exhaustive": len(checked)==len(edges),
        "goal_isolating_cuts": cut, "structural_only": True,
    })


def capability(world, player):
    """4: Remove each existing ability once and execute remaining win routes."""
    mutations = (
        [("permitted_modes", x) for x in sorted(player.permitted_modes)]
        + [("flags", x) for x in sorted(player.flags)]
        + [("equipment", x) for x in sorted(player.equipment)]
    )
    if len(mutations)>32:
        raise ExpeditionError("capability probe budget exceeded")
    probes = []
    for category, item in mutations:
        variant = replace(player, **{
            category: getattr(player, category)-frozenset((item,))
        })
        reachable = []
        for goal in world.destinations:
            try:
                route = find_route(world, variant, goal)
            except ExpeditionError as exc:
                if str(exc) != "no traversable route under current abilities and stamina":
                    raise
                continue
            evidence = verify_route(world, variant, route)
            if not evidence["verified"] or not evidence["final_state"]["won"]:
                raise ExpeditionError("degraded capability produced invalid gameplay")
            reachable.append({"goal": goal, "receipt": evidence["receipt_head"]})
        probes.append({"removed_from": category, "removed": item,
                       "remaining_winning_routes": reachable})
    return _seal(world, "capability", {
        "one_at_a_time_probes": probes, "combined_cases_executed": False,
        "real_controller_hardware_tested": False,
    })


def playthrough(world, player):
    """5: Play to every win condition on the actual expedition state machine."""
    routes = []
    for goal in world.destinations:
        path = find_route(world, player, goal)
        result = verify_route(world, player, path)
        if (not result["verified"] or not result["final_state"]["won"]
                or result["final_state"]["position"] != goal
                or len(result["step_receipts"]) != len(path.edge_ids)):
            raise ExpeditionError("world QA replay failed to complete destination")
        routes.append({"destination": goal, "edges": list(path.edge_ids),
                       "route_digest": path.digest,
                       "receipt": result["receipt_head"],
                       "steps": result["step_receipts"]})
    return _seal(world, "playthrough", {
        "winning_game_routes": routes,
        "state_machine_executed": True, "native_engine_executed": False,
    })


def canon(world, story, quests):
    """6: Static narrative/quest/ending references and authored producer proof."""
    story_flags = {f for s in story.scenes for c in s.choices for f in c.advances}
    quest_flags = {f for q in quests.quests for s in q.stages for f in s.unlocks}
    errors = []
    for scene in story.scenes:
        for flag in scene.requires_story_flags:
            if flag not in story_flags:
                errors.append("scene:"+scene.scene_id+":"+flag)
    for quest in quests.quests:
        for stage in quest.stages:
            if stage.waypoint not in world.by_id:
                errors.append("quest:"+quest.quest_id+":"+stage.stage_id)
            for flag in stage.requires_story_flags:
                if flag not in story_flags:
                    errors.append("quest-story:"+flag)
    for ending in quests.endings:
        for flag in ending.needs_story_flags:
            if flag not in story_flags:
                errors.append("ending-story:"+flag)
        for flag in ending.needs_quest_flags:
            if flag not in quest_flags:
                errors.append("ending-quest:"+flag)
    return _seal(world, "canon", {
        "story_digest": story.digest, "quest_digest": quests.digest,
        "scene_count": len(story.scenes),
        "dialogue_options": sum(len(s.choices) for s in story.scenes),
        "quest_stages": sum(len(q.stages) for q in quests.quests),
        "available_endings": sorted(x.ending_id for x in quests.endings),
        "orphaned_references": sorted(set(errors)),
        "dynamic_choices_executed_by_this_check": False,
    })


def adversarial(world, reports):
    """7: Independently traverse and reject altered hash-linked source evidence."""
    graph = _graph(world)
    bfs = _reachable(graph, world.arrival)
    dfs = _reachable(graph, world.arrival, depth_first=True)
    if bfs != dfs:
        raise ExpeditionError("independent directed route traversals disagree")
    for report in reports.values():
        if (report.get("world_digest")!=world.digest or
                report.get("receipt_digest")!=_digest({
                    k: v for k, v in report.items() if k!="receipt_digest"})):
            raise ExpeditionError("adversarial reviewer rejected forged evidence")
    changed = dict(reports["connectivity"])
    changed["reachable"] = []
    if changed["receipt_digest"]==_digest({
            k: v for k, v in changed.items() if k!="receipt_digest"}):
        raise ExpeditionError("tamper check failed")
    return _seal(world, "adversarial", {
        "bfs_dfs_agree": True, "reachable": sorted(bfs),
        "upstream_receipts": {k: reports[k]["receipt_digest"] for k in sorted(reports)},
        "edited_claim_rejected": True,
        "hardware_or_rights_review_signed": False,
    })


def compile_world_assurance(world: ExpeditionWorld, player: Traveler,
                            story: StoryBook, quests: QuestBook) -> dict:
    _validate(world, player, story, quests)
    axes = {"geometry": geometry(world), "connectivity": connectivity(world),
            "resilience": resilience(world),
            "capability": capability(world, player),
            "playthrough": playthrough(world, player),
            "canon": canon(world, story, quests)}
    axes["adversarial"] = adversarial(world, axes)
    if (set(axes) != set(AXES)
            or axes["connectivity"]["reachable"] != axes["adversarial"]["reachable"]
            or axes["canon"]["orphaned_references"]):
        raise ExpeditionError("seven world assurance milestones disagree")
    report = {"schema": SCHEMA, "world_digest": world.digest,
              "story_digest": story.digest, "quest_digest": quests.digest,
              "axes": axes, "axes_executed": len(axes),
              "source_assured": True, "native_game_verified": False,
              "production_release_approved": False}
    return {**report, "receipt_digest": _digest(report)}


def verify_world_assurance(world, player, story, quests, report: Mapping):
    """Full reexecution; a resealed but altered stored report is not trusted."""
    if not isinstance(report, Mapping) or dict(report) != compile_world_assurance(
            world, player, story, quests):
        raise ExpeditionError("world assurance differs from independent source replay")
