"""Immutable world indexes preserve source identity and travel authority."""
from copy import deepcopy
from dataclasses import asdict, fields, replace
import pickle

import pytest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionError, TravelEdge, assess_travel, find_route, verify_route,
)
from tests.test_game_frontier_expedition import player, world


def test_reverse_edges_are_constructed_once_per_world_not_per_route(monkeypatch):
    authored = world()
    expected = [edge.edge_id + ".reverse" for edge in authored.edges if not edge.one_way]
    constructed = []
    original_post_init = TravelEdge.__post_init__

    def counted_post_init(edge):
        original_post_init(edge)
        if edge.edge_id.endswith(".reverse"):
            constructed.append(edge.edge_id)

    monkeypatch.setattr(TravelEdge, "__post_init__", counted_post_init)
    indexed = replace(authored)
    assert constructed == expected
    traveler = player(flags=("glider", "pilot", "portal_key"))
    reverse = indexed.by_edge[expected[0]]
    for objective in ("fastest", "safest", "energy", "scenic"):
        route = find_route(indexed, traveler, "exit", objective=objective)
        assert verify_route(indexed, traveler, route)["verified"]
        assert assess_travel(indexed, reverse, traveler).allowed
        assert indexed.by_edge[expected[0]] is reverse
        assert indexed.by_id[indexed.arrival].waypoint_id == indexed.arrival
    assert constructed == expected

    independent = replace(authored)
    assert constructed == expected + expected
    assert independent.by_edge[expected[0]] == reverse
    assert independent.by_edge[expected[0]] is not reverse


def test_public_index_copies_cannot_change_world_source_or_travel():
    authored = world()
    source = authored.as_dict()
    digest = authored.digest
    nodes = authored.by_id
    edges = authored.by_edge
    original_node = nodes[authored.arrival]
    original_edge = edges["spire_road"]
    nodes[authored.arrival] = replace(original_node, x_m=9000.)
    nodes.clear()
    edges["spire_road"] = replace(original_edge, duration_s=.01)
    edges.pop("spire_road.reverse")
    edges.clear()

    assert authored.by_id[authored.arrival] == original_node
    assert authored.by_edge["spire_road"] == original_edge
    assert "spire_road.reverse" in authored.by_edge
    assert authored.as_dict() == source
    assert authored.digest == digest
    route = find_route(authored, player(modes=("walk", "portal"), flags=("portal_key",)), "exit")
    assert route.edge_ids == ("spire_road", "gateway")
    assert verify_route(authored, player(modes=("walk", "portal"), flags=("portal_key",)), route)["verified"]


@pytest.mark.parametrize("forgery", ("canonical_cost", "reverse_cost", "unregistered_reverse"))
def test_indexed_travel_rejects_forged_canonical_and_reverse_edges(forgery):
    authored = world()
    before = authored.as_dict()
    if forgery == "canonical_cost":
        forged = replace(authored.by_edge["spire_road"], duration_s=.01, stamina_cost=0)
    elif forgery == "reverse_cost":
        forged = replace(authored.by_edge["spire_road.reverse"], duration_s=.01, stamina_cost=0)
    else:
        edge = authored.by_edge["launch"]
        forged = replace(edge, edge_id=edge.edge_id + ".reverse", source=edge.target,
                         target=edge.source, one_way=True)
    with pytest.raises(ExpeditionError, match="not part of this authored world"):
        assess_travel(authored, forged, player(flags=("glider",)))
    assert assess_travel(authored, authored.by_edge["spire_road.reverse"], player()).allowed
    assert authored.as_dict() == before


@pytest.mark.parametrize("clone", (deepcopy, lambda value: pickle.loads(pickle.dumps(value)), replace),
                         ids=("deepcopy", "pickle", "dataclass_replace"))
def test_world_roundtrips_preserve_source_fields_and_rebuild_usable_indexes(clone):
    authored = world()
    names = {field.name for field in fields(authored)}
    assert names == {"project_id", "source_digest", "waypoints", "edges", "arrival",
                     "destinations", "weather"}
    serialized = asdict(authored)
    assert set(serialized) == names
    snapshot = authored.as_dict()
    digest = authored.digest
    copied = clone(authored)

    assert copied is not authored
    assert copied == authored
    assert hash(copied) == hash(authored)
    assert asdict(copied) == serialized
    assert copied.as_dict() == snapshot
    assert copied.digest == digest
    assert copied.by_edge == authored.by_edge
    assert copied.by_id == authored.by_id
    traveler = player(flags=("glider",))
    route = find_route(copied, traveler, "exit")
    assert route.edge_ids == ("launch", "bridge", "ridge_path", "goal_path")
    assert verify_route(copied, traveler, route)["verified"]
    assert authored.as_dict() == snapshot


def test_replacing_source_edges_rebuilds_only_the_new_world_index():
    original = world()
    snapshot = original.as_dict()
    changed_edge = replace(original.by_edge["spire_road"], duration_s=90.)
    changed = replace(original, edges=tuple(
        changed_edge if edge.edge_id == changed_edge.edge_id else edge
        for edge in original.edges
    ))

    assert changed != original
    assert changed.digest != original.digest
    assert changed.by_edge["spire_road"].duration_s == 90.
    assert changed.by_edge["spire_road.reverse"].duration_s == 90.
    assert original.by_edge["spire_road"].duration_s == 35.
    assert original.by_edge["spire_road.reverse"].duration_s == 35.
    assert original.as_dict() == snapshot


def test_reused_world_indexes_do_not_reuse_traveler_or_route_permissions():
    authored = world()
    traveler = player(modes=("walk", "portal"), flags=("portal_key",))
    before = authored.as_dict()
    expected = ("spire_road", "gateway")
    assert find_route(authored, traveler, "exit").edge_ids == expected

    blocked_policies = (
        {"forbidden_edges": frozenset(("spire_road",))},
        {"current_flags": frozenset()},
        {"current_stamina": 1},
    )
    for policy in blocked_policies:
        with pytest.raises(ExpeditionError, match="no traversable route"):
            find_route(authored, traveler, "exit", **policy)
        assert find_route(authored, traveler, "exit").edge_ids == expected
    with pytest.raises(ExpeditionError, match="no traversable route"):
        find_route(authored, player(modes=("walk", "portal")), "exit")
    assert find_route(authored, traveler, "exit").edge_ids == expected
    assert authored.as_dict() == before
