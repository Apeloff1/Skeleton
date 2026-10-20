"""Seven real game navigation extensions: references, tampering and integration."""
from copy import deepcopy
import json
import pytest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionError, ExpeditionWorld, Traveler, Waypoint, TravelEdge,
)
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile, author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_campaign import (
    original_campaign_player, compile_original_campaign, verify_original_campaign,
)
from skeleton.jeeves.game_frontier_expedition_navigation_advanced import (
    NavigationPolicy, AXES, world_atlas, route_portfolio, virtual_instruments,
    exploration_journal, environmental_itinerary, contextual_director,
    compile_navigation_seven, verify_navigation_seven,
)


@pytest.fixture(scope="module")
def game():
    world = author_archipelago("navigator", "a"*64,
                               ArchipelagoProfile(seed=37, islands=5))
    return world, original_campaign_player()


def test_m1_atlas_is_complete_and_has_fictional_coordinates(game):
    world, _ = game
    data = world_atlas(world)
    assert len(data["nodes"]) == len(world.waypoints)
    assert len(data["links"]) == len(world.by_edge)
    assert data["destinations"] == list(world.destinations)
    assert not data["external_or_device_location_used"]
    with pytest.raises(ExpeditionError):
        world_atlas(world, policy=NavigationPolicy(max_waypoints=2))


def test_m2_four_objective_routes_are_executed_by_game_state(game):
    world, player = game
    data = route_portfolio(world, player)
    assert len(data["routes"]) == 4
    assert data["executed"] >= 1
    assert all(row["won"] for row in data["routes"] if not row["blocked"])
    assert data["non_dominated_objectives"]
    assert not data["native_game_engine_executed"]


def test_m3_compass_and_sextant_are_source_geometry_not_device_gps(game):
    world, player = game
    chosen = next(x for x in route_portfolio(world, player)["routes"]
                  if not x["blocked"])
    data = virtual_instruments(world, chosen)
    assert len(data["readings"]) == len(chosen["edge_ids"])
    assert not data["real_gps_or_survey_device_used"]
    if data["readings"]:
        assert 0 <= data["readings"][0]["compass_bearing_deg"] < 360
    forged = deepcopy(chosen)
    forged["edge_ids"].append("forged_jump")
    with pytest.raises(ExpeditionError):
        virtual_instruments(world, forged)


def test_m4_exploration_replays_authoritative_game_journal(game):
    world, player = game
    chosen = next(x for x in route_portfolio(world, player)["routes"]
                  if not x["blocked"])
    record = exploration_journal(world, player, chosen)
    assert record["steps"]
    assert world.arrival in record["visited"]
    assert world.destinations[0] in world.by_id
    assert record["receipt_head"] == record["steps"][-1]["receipt_digest"]
    assert record == exploration_journal(world, player, chosen)


def test_m5_weather_itinerary_accounts_for_exact_executed_stamina(game):
    world, player = game
    chosen = next(x for x in route_portfolio(world, player)["routes"]
                  if not x["blocked"])
    report = environmental_itinerary(world, player, chosen)
    assert report["stamina_never_below_zero"]
    assert report["final_stamina"] >= 0
    assert not report["physical_forecast_or_native_safety_qualification"]
    for row in report["legs"]:
        assert row["stamina_before"] >= row["stamina_after"]


def test_m6_game_director_cannot_forge_quest_flags_or_moves(game):
    world, player = game
    chosen = next(x for x in route_portfolio(world, player)["routes"]
                  if not x["blocked"])
    projection = exploration_journal(world, player, chosen)
    report = contextual_director(world, projection)
    assert report["source_exploration_receipt"] == projection["receipt_digest"]
    assert all(not c["grants_inventory_or_quest_state"] for c in report["cues"])
    changed = deepcopy(projection)
    changed["steps"][0]["position"] = "fake_place"
    with pytest.raises(ExpeditionError):
        contextual_director(world, changed)


def test_m7_double_source_replay_seals_every_axis_and_rejects_tampering(game):
    world, player = game
    record = compile_navigation_seven(world, player)
    assert tuple(record) == AXES
    assert verify_navigation_seven(world, player, record)["verified"]
    assert not record["assurance"]["production_release_approved"]
    for axis in AXES:
        forged = deepcopy(record)
        forged[axis]["receipt_digest"] = "0"*64
        with pytest.raises(ExpeditionError, match="forged"):
            verify_navigation_seven(world, player, forged)


def test_m7_world_and_player_require_canonical_types(game):
    world, player = game
    with pytest.raises(ExpeditionError):
        compile_navigation_seven(None, player)
    with pytest.raises(ExpeditionError):
        compile_navigation_seven(world, None)
    with pytest.raises(ExpeditionError):
        compile_navigation_seven(world, player,
                                 policy=NavigationPolicy(max_steps=1))


def test_expanded_full_campaign_exports_real_navigation_receipts():
    candidate = compile_original_campaign(
        "nav_candidate", gdd_digest="f"*64, seed=37, islands=5,
    )
    path = "game/frontier/advanced_navigation.json"
    assert path in candidate["files"]
    data = json.loads(candidate["files"][path])
    assert data["assurance"] == candidate["advanced_navigation"]["assurance"]
    assert candidate["manifest"]["advanced_navigation_receipt"] == data["assurance"]["receipt_digest"]
    assert verify_original_campaign(
        candidate, project_id="nav_candidate", gdd_digest="f"*64,
        seed=37, islands=5,
    )["all_source_bytes_verified"]
    tampered = deepcopy(candidate)
    tampered["files"][path] += "\n"
    with pytest.raises(ExpeditionError, match="differs"):
        verify_original_campaign(
            tampered, project_id="nav_candidate", gdd_digest="f"*64,
            seed=37, islands=5,
        )
