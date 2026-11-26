"""GF-P1-19 and GF-P1-45: world-family admission and multimodal routes."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from skeleton.frontier_worldgraph import (
    AdmittedTransition,
    ClimateBounds,
    ClimateEnvelope,
    Constraint,
    FictionalPosition,
    MapLayer,
    Route,
    RouteRefusal,
    TransitionRefusal,
    Traveler,
    WorldFamilyGraph,
    WorldGraphError,
    canon_digest_of,
    follow,
    synthesize_route,
)
from skeleton.jeeves.game_frontier_worlds import WorldFamily
from skeleton.world import WorldState

IDENTITY = "lineage"
WIDE = ClimateEnvelope(-20, 45, 0.0, 1.0)
ISLAND_RULES = ("gravity.down", "medium.air")
CAVE_RULES = ("gravity.down", "medium.stone")
ETHEREAL_RULES = ("gravity.signed", "medium.aether")
MAP_RULES = ("gravity.none", "medium.map")
INVERSE_RULES = ("gravity.up", "medium.aether")
ISLAND_AT = FictionalPosition(MapLayer.ISLAND, 1200, 800, 40)
CAVE_AT = FictionalPosition(MapLayer.CAVE, 1200, 800, -120)
ETHEREAL_AT = FictionalPosition(MapLayer.ETHEREAL, 1200, 1400, 600)
MAP_AT = FictionalPosition(MapLayer.MAP_2D, 250, 480, None)
INVERSE_AT = FictionalPosition(MapLayer.INVERSE, 250, 480, -30)


def _bounds(biome: str, low: float, high: float, humid_low: float, humid_high: float) -> ClimateBounds:
    return ClimateBounds(biome, low, high, humid_low, humid_high)


def _build(
    *,
    ethereal_document: str = "canon:ethereal:v1",
    ethereal_expects: str | None = None,
    cave_document: str = "canon:cave:v1",
    declare_cave_ethereal: bool = True,
    shortcut: bool = False,
) -> tuple[WorldFamilyGraph, Traveler, dict[str, str]]:
    digests = {
        "genesis": canon_digest_of("canon:genesis"),
        "island": canon_digest_of("canon:island:v1"),
        "cave": canon_digest_of(cave_document),
        "ethereal": canon_digest_of(ethereal_document),
        "map2d": canon_digest_of("canon:map2d:v1"),
        "inverse": canon_digest_of("canon:inverse:v1"),
    }
    graph = WorldFamilyGraph()
    graph.add_world(
        "island",
        identity=IDENTITY,
        canon_digest=digests["island"],
        expected_predecessor=digests["genesis"],
        climate=_bounds("woodland", 10, 30, 0.25, 0.75),
        rule_ids=ISLAND_RULES,
        position=ISLAND_AT,
    )
    graph.add_world(
        "cave",
        identity=IDENTITY,
        canon_digest=digests["cave"],
        expected_predecessor=digests["island"],
        climate=_bounds("stone", 8, 18, 0.5, 1.0),
        rule_ids=CAVE_RULES,
        position=CAVE_AT,
    )
    graph.add_world(
        "ethereal",
        identity=IDENTITY,
        canon_digest=digests["ethereal"],
        expected_predecessor=ethereal_expects or digests["cave"],
        climate=_bounds("aether", -5, 12, 0.0, 0.5),
        rule_ids=ETHEREAL_RULES,
        position=ETHEREAL_AT,
    )
    graph.add_world(
        "map2d",
        identity=IDENTITY,
        canon_digest=digests["map2d"],
        expected_predecessor=digests["island"],
        climate=_bounds("chart", 10, 28, 0.25, 0.75),
        rule_ids=MAP_RULES,
        position=MAP_AT,
    )
    graph.add_world(
        "inverse",
        identity=IDENTITY,
        canon_digest=digests["inverse"],
        expected_predecessor=digests["map2d"],
        climate=_bounds("void", -2, 20, 0.25, 0.75),
        rule_ids=INVERSE_RULES,
        position=INVERSE_AT,
    )
    graph.declare_compatible(ISLAND_RULES, CAVE_RULES)
    graph.declare_compatible(ISLAND_RULES, MAP_RULES)
    graph.declare_compatible(MAP_RULES, INVERSE_RULES)
    if declare_cave_ethereal:
        graph.declare_compatible(CAVE_RULES, ETHEREAL_RULES)
    graph.link("island", "cave")
    graph.link("cave", "ethereal")
    graph.link("island", "map2d")
    graph.link("map2d", "inverse")
    if shortcut:
        graph.link("island", "ethereal")
    graph.declare_compatible(ISLAND_RULES, CAVE_RULES)
    traveler = Traveler(
        identity=IDENTITY,
        world_id="island",
        canon_digest=digests["island"],
        envelope=WIDE,
        rule_ids=ISLAND_RULES,
        position=ISLAND_AT,
    )
    return graph, traveler, digests


def test_island_cave_ethereal_route_is_deterministic():
    graph, traveler, digests = _build(shortcut=True)
    other, _, _ = _build(shortcut=True)
    revision = graph.scene.revision
    route = graph.synthesize(traveler, "ethereal")
    again = synthesize_route(graph, traveler, "ethereal")
    rebuilt = synthesize_route(other, traveler, "ethereal")

    assert isinstance(route, Route)
    assert isinstance(again, Route)
    assert isinstance(rebuilt, Route)
    assert route.world_ids == ("island", "cave", "ethereal")
    assert route.hop_count == 2
    assert route.addresses == again.addresses == rebuilt.addresses
    assert route.addresses == (
        graph.edge_address("island", "cave"),
        graph.edge_address("cave", "ethereal"),
    )
    assert route.transitions[0].constraints_satisfied == (
        "identity",
        "canon",
        "climate",
        "physics",
    )
    for hop in route.transitions:
        assert hop.address == sha256(hop.edge.canonical_json.encode("utf-8")).hexdigest()
        assert "latitude" not in hop.edge.canonical_json
        assert "longitude" not in hop.edge.canonical_json
    assert route.transitions[1].traveler.canon_digest == digests["ethereal"]
    assert route.transitions[1].traveler.rule_ids == ETHEREAL_RULES
    assert route.transitions[1].traveler.position == ETHEREAL_AT
    assert route.transitions[1].traveler.identity == IDENTITY
    assert traveler.world_id == "island"
    assert graph.scene.revision == revision

    arrived = follow(graph, traveler, route)
    assert isinstance(arrived, Traveler)
    assert arrived.world_id == "ethereal"
    assert arrived.position.z_m == 600
    assert traveler.world_id == "island"
    assert graph.world("ethereal").family is WorldFamily.ETHEREAL
    assert graph.world("island").family is WorldFamily.ORIGINAL
    assert isinstance(graph.scene, WorldState)


def test_broken_shortcut_does_not_replace_an_admitted_route():
    graph, traveler, _ = _build(shortcut=True)
    direct = graph.cross(traveler, "ethereal")
    assert isinstance(direct, TransitionRefusal)
    assert direct.constraint is Constraint.CANON
    assert direct.traveler is traveler
    route = synthesize_route(graph, traveler, "ethereal")
    assert isinstance(route, Route)
    assert route.world_ids == ("island", "cave", "ethereal")


def test_canon_disagreement_is_a_typed_refusal():
    graph, traveler, digests = _build(
        ethereal_expects=canon_digest_of("canon:unrelated"),
        declare_cave_ethereal=False,
    )
    revision = graph.scene.revision
    refused = graph.synthesize(traveler, "ethereal")
    assert isinstance(refused, RouteRefusal)
    assert not isinstance(refused, Route)
    assert refused.constraint is Constraint.CANON
    assert refused.broken_source_id == "cave"
    assert refused.broken_destination_id == "ethereal"
    assert refused.traveler is traveler
    assert refused.traveler.world_id == "island"
    assert graph.scene.revision == revision

    at_cave = Traveler(
        identity=IDENTITY,
        world_id="cave",
        canon_digest=digests["cave"],
        envelope=WIDE,
        rule_ids=CAVE_RULES,
        position=CAVE_AT,
    )
    hop = graph.cross(at_cave, "ethereal")
    assert isinstance(hop, TransitionRefusal)
    assert hop.constraint is Constraint.CANON
    assert hop.traveler is at_cave
    assert hop.traveler.world_id == "cave"


def test_physics_disagreement_is_a_typed_refusal():
    graph, traveler, digests = _build(declare_cave_ethereal=False)
    refused = synthesize_route(graph, traveler, "ethereal")
    assert isinstance(refused, RouteRefusal)
    assert refused.constraint is Constraint.PHYSICS
    assert refused.broken_source_id == "cave"
    assert refused.broken_destination_id == "ethereal"
    assert refused.detail == "physical-rule set is not declared compatible"
    assert refused.traveler is traveler
    assert refused.traveler.world_id == "island"

    at_cave = Traveler(
        identity=IDENTITY,
        world_id="cave",
        canon_digest=digests["cave"],
        envelope=WIDE,
        rule_ids=CAVE_RULES,
        position=CAVE_AT,
    )
    revision = graph.scene.revision
    hop = graph.cross(at_cave, "ethereal")
    assert isinstance(hop, TransitionRefusal)
    assert hop.constraint is Constraint.PHYSICS
    assert hop.traveler is at_cave
    assert graph.scene.revision == revision
    assert not hasattr(hop, "transitions")


def test_rejected_transition_leaves_traveler_in_source():
    graph, traveler, _ = _build(
        ethereal_expects=canon_digest_of("canon:unrelated"),
        shortcut=True,
    )
    revision = graph.scene.revision
    moved = graph.cross(traveler, "cave")
    assert isinstance(moved, AdmittedTransition)
    assert moved.traveler.world_id == "cave"
    assert traveler.world_id == "island"
    blocked = graph.cross(traveler, "ethereal")
    assert isinstance(blocked, TransitionRefusal)
    assert blocked.constraint is Constraint.CANON
    assert blocked.source_id == "island"
    assert blocked.traveler is traveler
    assert blocked.traveler.position == ISLAND_AT
    assert graph.scene.revision == revision


def test_identity_is_the_first_broken_constraint():
    graph, traveler, _ = _build(ethereal_expects=canon_digest_of("canon:unrelated"))
    foreign = Traveler(
        identity="otherline",
        world_id="island",
        canon_digest=canon_digest_of("canon:forged"),
        envelope=WIDE,
        rule_ids=ISLAND_RULES,
        position=ISLAND_AT,
    )
    refused = graph.cross(foreign, "cave")
    assert isinstance(refused, TransitionRefusal)
    assert refused.constraint is Constraint.IDENTITY
    assert refused.traveler is foreign
    assert traveler.identity == IDENTITY


def test_climate_mismatch_refuses_before_travel():
    graph, _, digests = _build()
    narrow = Traveler(
        identity=IDENTITY,
        world_id="island",
        canon_digest=digests["island"],
        envelope=ClimateEnvelope(100, 110, 0.0, 1.0),
        rule_ids=ISLAND_RULES,
        position=ISLAND_AT,
    )
    refused = graph.cross(narrow, "cave")
    assert isinstance(refused, TransitionRefusal)
    assert refused.constraint is Constraint.CLIMATE
    assert refused.traveler is narrow
    assert refused.traveler.world_id == "island"


def test_map2d_and_inverse_route_uses_fictional_metres():
    graph, traveler, _ = _build()
    route = synthesize_route(graph, traveler, "inverse")
    assert isinstance(route, Route)
    assert route.world_ids == ("island", "map2d", "inverse")
    assert route.hop_count == 2
    map_hop = route.transitions[0]
    inverse_hop = route.transitions[1]
    assert map_hop.traveler.position.layer is MapLayer.MAP_2D
    assert map_hop.traveler.position.z_m is None
    assert map_hop.traveler.position.x_m == 250
    assert map_hop.traveler.position.y_m == 480
    assert inverse_hop.traveler.position == INVERSE_AT
    assert graph.world("inverse").family is WorldFamily.INVERSE
    assert graph.world("map2d").family is WorldFamily.ORIGINAL
    payload = inverse_hop.edge.payload()
    assert payload["destination"]["z_m"] == -30
    assert payload["source"]["z_m"] is None
    assert payload["source"]["layer"] == "map2d"
    assert "latitude" not in payload["destination"]
    assert "longitude" not in payload["source"]
    stored = graph.scene.require("map2d")
    assert stored.kind == "world"
    assert stored.transform.translation == (250.0, 480.0, 0.0)
    assert stored.attributes["planar"] == 1


def test_equal_length_routes_follow_sorted_world_ids():
    shared = canon_digest_of("canon:shared-middle")
    goal_canon = canon_digest_of("canon:goal")
    start_canon = canon_digest_of("canon:start")
    rules_start = ("medium.air",)
    rules_middle = ("medium.stone",)
    rules_goal = ("medium.aether",)
    graph = WorldFamilyGraph()
    start_at = FictionalPosition(MapLayer.ISLAND, 0, 0, 0)
    alpha_at = FictionalPosition(MapLayer.CAVE, 10, 0, -5)
    beta_at = FictionalPosition(MapLayer.CAVE, 20, 0, -5)
    goal_at = FictionalPosition(MapLayer.ETHEREAL, 30, 0, 15)
    for world_id, canon, expects, rules, position in (
        ("start", start_canon, canon_digest_of("canon:genesis"), rules_start, start_at),
        ("alpha", shared, start_canon, rules_middle, alpha_at),
        ("beta", shared, start_canon, rules_middle, beta_at),
        ("goal", goal_canon, shared, rules_goal, goal_at),
    ):
        graph.add_world(
            world_id,
            identity=IDENTITY,
            canon_digest=canon,
            expected_predecessor=expects,
            climate=_bounds("woodland", 0, 20, 0.25, 0.75),
            rule_ids=rules,
            position=position,
        )
    graph.declare_compatible(rules_start, rules_middle)
    graph.declare_compatible(rules_middle, rules_goal)
    graph.link("start", "beta")
    graph.link("start", "alpha")
    graph.link("beta", "goal")
    graph.link("alpha", "goal")
    traveler = Traveler(
        identity=IDENTITY,
        world_id="start",
        canon_digest=start_canon,
        envelope=WIDE,
        rule_ids=rules_start,
        position=start_at,
    )
    route = synthesize_route(graph, traveler, "goal")
    repeat = graph.synthesize(traveler, "goal")
    assert isinstance(route, Route)
    assert isinstance(repeat, Route)
    assert route.world_ids == ("start", "alpha", "goal")
    assert route.addresses == repeat.addresses


def test_coordinates_reject_geographic_degrees_and_wrong_axes():
    with pytest.raises(WorldGraphError, match="latitude"):
        FictionalPosition.from_record(
            {"layer": "map2d", "x_m": 1, "y_m": 2, "latitude": 51.5, "longitude": -0.1}
        )
    with pytest.raises(WorldGraphError, match="latitude"):
        FictionalPosition.from_record(
            {"layer": "island", "x_m": 1, "y_m": 2, "z_m": 3, "lng": 4}
        )
    with pytest.raises(WorldGraphError, match="vertical"):
        FictionalPosition(MapLayer.MAP_2D, 1, 2, 3)
    with pytest.raises(WorldGraphError, match="vertical"):
        FictionalPosition(MapLayer.CAVE, 1, 2, None)
    record = FictionalPosition(MapLayer.MAP_2D, 4, 5).as_record()
    assert record == {"layer": "map2d", "x_m": 4.0, "y_m": 5.0, "z_m": None}
    assert "latitude" not in record


def test_unreachable_goal_is_not_an_empty_route():
    graph, traveler, digests = _build()
    graph.add_world(
        "pocket",
        identity=IDENTITY,
        canon_digest=canon_digest_of("canon:pocket"),
        expected_predecessor=digests["island"],
        climate=_bounds("woodland", 10, 20, 0.25, 0.5),
        rule_ids=ISLAND_RULES,
        position=FictionalPosition(MapLayer.ISLAND, 9, 9, 9),
    )
    refused = synthesize_route(graph, traveler, "pocket")
    assert isinstance(refused, RouteRefusal)
    assert refused.constraint is Constraint.DISCONNECTED
    assert refused.broken_destination_id is None
    assert refused.traveler is traveler
    assert refused.traveler.world_id == "island"
    stayed = synthesize_route(graph, traveler, "island")
    assert isinstance(stayed, Route)
    assert stayed.hop_count == 0
    assert stayed.traveler is traveler


def test_edge_address_changes_when_canon_changes_and_scene_holds_the_node():
    graph, _, digests = _build()
    changed, _, _ = _build(cave_document="canon:cave:revised")
    assert graph.edge_address("island", "cave") != changed.edge_address("island", "cave")
    island = graph.scene.require("island")
    assert island.kind == "world"
    assert island.attributes["canon"] == digests["island"]
    assert island.attributes["identity"] == IDENTITY
    assert island.attributes["rules"] == "gravity.down,medium.air"
    assert island.transform.translation == (1200.0, 800.0, 40.0)
    assert graph.scene.digest() == _build()[0].scene.digest()
    assert graph.link("island", "cave") == graph.edge_address("island", "cave")


def test_implementation_has_no_stubs_clock_or_random_search():
    root = Path(__file__).resolve().parents[1] / "skeleton" / "frontier_worldgraph"
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.glob("*.py")))
    assert "NotImplemented" not in text
    assert "import random" not in text
    assert "import time" not in text
    assert "datetime" not in text
    assert "TODO" not in text
