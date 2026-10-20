"""Seven source-bound world-navigation production milestones for Jeeves.

This is a derived, engine-neutral projection of the canonical ExpeditionWorld.
It does NOT become a second gameplay authority and cannot sign native execution,
GNSS evidence, trained model weights, legal clearance or production release.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot
from typing import Mapping

from .game_frontier_expedition import (
    ExpeditionAction, ExpeditionEpisode, ExpeditionError, ExpeditionWorld,
    Traveler, _digest, _int, assess_travel, find_route, verify_route,
)

AXES = ("atlas", "instruments", "routes", "exploration", "hazards",
        "director", "assurance")
OBJECTIVES = ("fastest", "safest", "energy", "scenic")


@dataclass(frozen=True, slots=True)
class NavigationPolicy:
    """Finite work envelope, not a claim that 8,192-node worlds are qualified."""

    max_waypoints: int = 4096
    max_directed_edges: int = 16384
    max_steps: int = 512
    max_expansions: int = 25000

    def __post_init__(self):
        _int(self.max_waypoints, 2, 8192, "navigation node cap")
        _int(self.max_directed_edges, 1, 65536, "navigation edge cap")
        _int(self.max_steps, 1, 4096, "navigation step cap")
        _int(self.max_expansions, 10, 500000, "navigation search cap")


def _seal(body: dict) -> dict:
    out = dict(body)
    out["receipt_digest"] = _digest(out)
    return out


def _inputs(world: ExpeditionWorld, traveler: Traveler, policy: NavigationPolicy):
    if (not isinstance(world, ExpeditionWorld)
            or not isinstance(traveler, Traveler)
            or not isinstance(policy, NavigationPolicy)):
        raise ExpeditionError("canonical typed game world, traveler and navigation policy required")
    if len(world.waypoints) > policy.max_waypoints or len(world.by_edge) > policy.max_directed_edges:
        raise ExpeditionError("navigation projection exceeds declared source budget")


def world_atlas(world: ExpeditionWorld, *, policy: NavigationPolicy = NavigationPolicy()) -> dict:
    """M1: preserve every authored three-dimensional destination and directed link."""
    if not isinstance(world, ExpeditionWorld) or not isinstance(policy, NavigationPolicy):
        raise ExpeditionError("invalid authored map")
    if len(world.waypoints) > policy.max_waypoints or len(world.by_edge) > policy.max_directed_edges:
        raise ExpeditionError("atlas would silently omit authored topology")
    nodes = []
    for point in sorted(world.waypoints, key=lambda p: p.waypoint_id):
        layer = ("submerged" if point.kind == "underwater"
                 else "aerial" if point.kind in {"sky_island", "airship"}
                 else "interior" if point.kind in {"cavern", "ruins"}
                 else "surface")
        nodes.append({
            "id": point.waypoint_id, "kind": point.kind, "layer": layer,
            "xyz_m": [point.x_m, point.y_m, point.altitude_m],
            "landmark": point.landmark, "safe_rest": point.safe_rest,
            "destination": point.waypoint_id in world.destinations,
        })
    links = [
        {"id": edge.edge_id, "from": edge.source, "to": edge.target,
         "mode": edge.mode, "length_m": edge.length_m,
         "one_way_projection": True, "requires": list(edge.requires)}
        for edge in sorted(world.by_edge.values(), key=lambda e: e.edge_id)
    ]
    xyz = tuple(n["xyz_m"] for n in nodes)
    return _seal({
        "schema": "skeleton.game.world_atlas.v1", "world": world.digest,
        "source": world.source_digest, "realm": world.project_id,
        "coordinates": "authored_fictional_xyz_metres",
        "bounds_m": [[min(p[i] for p in xyz), max(p[i] for p in xyz)]
                     for i in range(3)],
        "nodes": nodes, "links": links,
        "arrival": world.arrival, "destinations": list(world.destinations),
        "external_or_device_location_used": False,
    })


def route_portfolio(world: ExpeditionWorld, traveler: Traveler, *,
                    policy: NavigationPolicy = NavigationPolicy()) -> dict:
    """M2: execute all four optimization policies on actual canonical state."""
    _inputs(world, traveler, policy)
    target = sorted(world.destinations)[0]
    rows = []
    for objective in OBJECTIVES:
        try:
            route = find_route(world, traveler, target, objective=objective,
                               max_expansions=policy.max_expansions)
        except ExpeditionError as error:
            if str(error) != "no traversable route under current abilities and stamina":
                raise
            rows.append({"objective": objective, "blocked": True,
                         "reason": "source_game_traversal_unavailable"})
            continue
        if len(route.edge_ids) > policy.max_steps:
            raise ExpeditionError("route exceeds bounded exploration journal")
        execution = verify_route(world, traveler, route)
        if not execution["verified"] or execution["final_state"]["position"] != target:
            raise ExpeditionError("navigation optimizer disagrees with real gameplay")
        rows.append({
            "objective": objective, "blocked": False,
            "edge_ids": list(route.edge_ids), "waypoints": list(route.waypoints),
            "route_digest": route.digest,
            "seconds": route.seconds, "stamina": route.stamina,
            "damage": route.damage, "scenic": route.scenic_score,
            "gameplay_receipt": execution["receipt_head"],
            "won": execution["final_state"]["won"],
        })
    executed = [row for row in rows if not row["blocked"]]
    if not executed:
        raise ExpeditionError("no executable objective route for authored destination")
    distinct = len({tuple(row["edge_ids"]) for row in executed})
    # Non-dominated set uses three exact comparable game costs.
    frontier = []
    for row in executed:
        dominated = any(
            (other["seconds"] <= row["seconds"]
             and other["stamina"] <= row["stamina"]
             and other["damage"] <= row["damage"]
             and (other["seconds"] < row["seconds"]
                  or other["stamina"] < row["stamina"]
                  or other["damage"] < row["damage"]))
            for other in executed if other is not row
        )
        if not dominated:
            frontier.append(row["objective"])
    return _seal({
        "schema": "skeleton.game.gameplay_route_portfolio.v1",
        "world": world.digest, "destination": target,
        "routes": rows, "executed": len(executed),
        "distinct_edge_sequences": distinct, "non_dominated_objectives": frontier,
        "actual_engine_neutral_gameplay_executed": True,
        "native_game_engine_executed": False,
    })


def virtual_instruments(world: ExpeditionWorld, route: Mapping) -> dict:
    """M3: compass/sextant/altimeter driven by authored geometry, not device GPS."""
    if not isinstance(world, ExpeditionWorld) or not isinstance(route, Mapping):
        raise ExpeditionError("typed virtual-world survey source required")
    edges = route.get("edge_ids")
    if type(edges) is not list or len(edges) > 4096:
        raise ExpeditionError("virtual survey requires finite canonical route")
    position = world.arrival
    readings = []
    for edge_id in edges:
        edge = world.by_edge.get(edge_id)
        if edge is None or edge.source != position:
            raise ExpeditionError("survey route has unconnected or fictional edge")
        start, end = world.by_id[position], world.by_id[edge.target]
        dx, dy = end.x_m - start.x_m, end.y_m - start.y_m
        dz = end.altitude_m - start.altitude_m
        flat = hypot(dx, dy)
        readings.append({
            "edge": edge_id, "from": position, "to": edge.target,
            "compass_bearing_deg": round((degrees(atan2(dx, dy)) + 360) % 360, 6),
            "sextant_elevation_deg": round(degrees(atan2(dz, flat)), 6),
            "slant_range_m": round(hypot(flat, dz), 6),
            "horizontal_range_m": round(flat, 6),
            "trigonometric_altitude_delta_m": round(dz, 6),
            "game_altimeter_m": end.altitude_m,
            "bubble_sextant_reference_deg": 0.0,
            "xyz_fix_m": [end.x_m, end.y_m, end.altitude_m],
            "fix_type": "authored_world_exact_position_not_measured_gnss",
        })
        position = edge.target
    if position != route.get("waypoints", [None])[-1]:
        raise ExpeditionError("virtual instrumentation diverges from authored path")
    return _seal({
        "schema": "skeleton.game.virtual_instrument_trace.v1",
        "world": world.digest, "start": world.arrival,
        "destination": position, "readings": readings,
        "fictional_coordinate_frame": "world_XYZ_not_WGS84",
        "real_gps_or_survey_device_used": False,
        "position_uncertainty_measured": False,
    })


def exploration_journal(world: ExpeditionWorld, traveler: Traveler,
                        route: Mapping) -> dict:
    """M4: fog-of-war from executed movements, hash-linked to engine receipts."""
    if not isinstance(route, Mapping) or type(route.get("edge_ids")) is not list:
        raise ExpeditionError("exploration needs a concrete game route")
    episode = ExpeditionEpisode(world, traveler)
    visited = {world.arrival}
    observations = []
    previous = _digest({"genesis": world.digest, "type": "game_exploration"})
    for index, edge_id in enumerate(route["edge_ids"], start=1):
        if index > 4096:
            raise ExpeditionError("too many exploration steps")
        result = episode.step(ExpeditionAction("travel", edge_id))
        visited.add(episode.position)
        visible = visited | {e.target for e in world.by_edge.values() if e.source in visited}
        record = {
            "step": index, "edge": edge_id, "position": episode.position,
            "visited": sorted(visited), "revealed": sorted(visible),
            "undiscovered": sorted(set(world.by_id) - visible),
            "engine_receipt": result["receipt"], "previous": previous,
        }
        record["receipt_digest"] = _digest(record)
        observations.append(record)
        previous = record["receipt_digest"]
    restored = ExpeditionEpisode.restore(world, traveler, episode.snapshot())
    if restored.snapshot() != episode.snapshot():
        raise ExpeditionError("exploration fails independent game-event replay")
    return _seal({
        "schema": "skeleton.game.authored_exploration_fog.v1",
        "world": world.digest,
        "visited": sorted(visited),
        "revealed": (observations[-1]["revealed"] if observations else [world.arrival]),
        "steps": observations, "receipt_head": previous,
        "gameplay_receipt_head": episode.snapshot()["receipt_head"],
        "restored_game_state_digest": _digest(restored.state()),
        "not_native_renderer_visibility": True,
    })


def environmental_itinerary(world: ExpeditionWorld, traveler: Traveler,
                            route: Mapping) -> dict:
    """M5: actual weather/weight/stamina safety margins per playable edge."""
    if not isinstance(route, Mapping) or type(route.get("edge_ids")) is not list:
        raise ExpeditionError("hazard planning needs executed route")
    episode = ExpeditionEpisode(world, traveler)
    legs = []
    for edge_id in route["edge_ids"]:
        edge = world.by_edge.get(edge_id)
        if edge is None or edge.source != episode.position:
            raise ExpeditionError("hazard itinerary has non-authoritative edge")
        before = episode.stamina
        assessment = assess_travel(
            world, edge, traveler, current_flags=frozenset(episode.flags))
        if not assessment.allowed or before < assessment.stamina:
            raise ExpeditionError("weather itinerary falsely marks locked corridor passable")
        result = episode.step(ExpeditionAction("travel", edge_id))
        legs.append({
            "edge": edge_id, "mode": edge.mode, "stamina_before": before,
            "stamina_after": episode.stamina, "risk": edge.risk,
            "predicted_stamina_cost": assessment.stamina,
            "predicted_damage": assessment.damage,
            "predicted_duration_s": assessment.duration_s,
            "wind_component_mps": assessment.wind_resistance,
            "traction": assessment.traction,
            "safe_rest_at_destination": world.by_id[edge.target].safe_rest,
            "engine_receipt": result["receipt"],
        })
    if legs and episode.position != route["waypoints"][-1]:
        raise ExpeditionError("hazard forecast does not reach selected destination")
    return _seal({
        "schema": "skeleton.game.environmental_route_plan.v1",
        "world": world.digest, "world_weather_digest": _digest(
            {"weather": world.as_dict()["weather"]}),
        "legs": legs, "final_stamina": episode.stamina,
        "final_health": episode.health,
        "stamina_never_below_zero": episode.stamina >= 0,
        "all_hazards_canonical_game_reference": True,
        "physical_forecast_or_native_safety_qualification": False,
    })


def contextual_director(world: ExpeditionWorld, exploration: Mapping) -> dict:
    """M6: deterministic suggestion-only original encounters, never state grants."""
    if not isinstance(world, ExpeditionWorld) or not isinstance(exploration, Mapping):
        raise ExpeditionError("director requires world and witnessed exploration")
    visits = exploration.get("steps")
    if not isinstance(visits, list):
        raise ExpeditionError("director cannot invent exploration observations")
    seen = {world.arrival}
    cues = []
    for row in visits:
        waypoint = row.get("position")
        if waypoint not in world.by_id:
            raise ExpeditionError("director is not allowed to invent game locations")
        if waypoint in seen:
            continue
        seen.add(waypoint)
        node = world.by_id[waypoint]
        prompt = {
            "sky_island": "Observe cloud shear before the next crossing",
            "underwater": "Check air and light before descending",
            "cavern": "Mark a reversible route toward daylight",
            "volcano": "Check heat exposure and retreat corridors",
            "ice": "Probe traction before moving equipment",
            "ruins": "Record the landmark without altering the canon",
            "settlement": "Consider a rest and conversation",
        }.get(node.kind, "Observe the terrain and its alternate exits")
        cues.append({
            "at": waypoint, "kind": node.kind,
            "suggestion": prompt, "original_landmark": node.landmark,
            "quest_flag_observed": node.quest_flag or None,
            "recovery_point": node.safe_rest,
            "grants_inventory_or_quest_state": False,
        })
    return _seal({
        "schema": "skeleton.game.authored_contextual_director.v1",
        "world": world.digest, "source_exploration_receipt":
            exploration.get("receipt_digest"),
        "cues": cues, "authority": "read_only_game_director_suggestions",
        "voice_or_copyright_clearance_issued": False,
    })


def compile_navigation_seven(world: ExpeditionWorld, traveler: Traveler, *,
                             policy: NavigationPolicy = NavigationPolicy()) -> dict:
    """M7: integrate and cross-check seven milestone receipts before game export."""
    _inputs(world, traveler, policy)
    atlas = world_atlas(world, policy=policy)
    routes = route_portfolio(world, traveler, policy=policy)
    preferred = next(row for row in routes["routes"] if not row["blocked"])
    instruments = virtual_instruments(world, preferred)
    exploration = exploration_journal(world, traveler, preferred)
    hazards = environmental_itinerary(world, traveler, preferred)
    director = contextual_director(world, exploration)
    if (len(instruments["readings"]) != len(preferred["edge_ids"])
            or len(exploration["steps"]) != len(preferred["edge_ids"])
            or len(hazards["legs"]) != len(preferred["edge_ids"])
            or not routes["executed"]):
        raise ExpeditionError("independent navigation disciplines disagree on movements")
    pieces = {
        "atlas": atlas, "instruments": instruments,
        "routes": routes, "exploration": exploration,
        "hazards": hazards, "director": director,
    }
    for key, piece in pieces.items():
        if (piece["world"] != world.digest
                or piece["receipt_digest"] != _digest({
                    k: v for k, v in piece.items() if k != "receipt_digest"
                })):
            raise ExpeditionError("navigation receipt invalid for " + key)
    assurance = _seal({
        "schema": "skeleton.game.navigation_seven_assurance.v1",
        "world": world.digest, "source": world.source_digest,
        "axes": list(AXES),
        "receipts": {key: value["receipt_digest"] for key, value in sorted(pieces.items())},
        "executed_reference_gameplay": True,
        "physical_gps_used": False,
        "native_frames_recorded": False,
        "production_release_approved": False,
        "external_rights_review_signed": False,
        "independent_native_hardware_qualification": False,
    })
    return {**pieces, "assurance": assurance}


def verify_navigation_seven(world: ExpeditionWorld, traveler: Traveler,
                            submitted: Mapping, *,
                            policy: NavigationPolicy = NavigationPolicy()) -> dict:
    """Independently re-execute all game routes and regenerate every byte."""
    if not isinstance(submitted, Mapping):
        raise ExpeditionError("navigation verification needs actual candidate record")
    rebuilt = compile_navigation_seven(world, traveler, policy=policy)
    if dict(submitted) != rebuilt:
        raise ExpeditionError("navigation source, geometry, action or receipt forged")
    return {"verified": True, "world": world.digest,
            "receipt_digest": rebuilt["assurance"]["receipt_digest"],
            "native_or_legal_signoff": False}
