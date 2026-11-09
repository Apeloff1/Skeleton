"""Adversarial quality and procedural diversity gates for original route worlds."""
from __future__ import annotations
from dataclasses import replace
import json
import pytest

from skeleton.ai.webcrawler.dragon_route_world import (
    Place,Traverse,World,Traveller,plan,replay,experience,validate_world,
)
from skeleton.ai.webcrawler.dragon_route_world_factory import (
    make_frontier,scenario_digest,
)
from skeleton.ai.webcrawler.dragon_route_world_variants import (
    OPTIONS,mutate_original_world,original_variant_receipt,
)
from skeleton.ai.webcrawler.dragon_route_world_assurance import (
    SCHEMA,audit_world,demand_viable_world,climate_suite,
)


@pytest.mark.parametrize("weather",["clear","rain","windy","storm","snow","high_tide"])
def test_every_weather_world_has_real_goal_path_no_unrewarded_deadends_or_secret_leaks(weather):
    world,traveller=make_frontier(seed=1977,weather=weather)
    audited=audit_world(world,traveller,max_search=4000)
    assert audited.schema==SCHEMA
    assert audited.places==len(world.places)
    assert audited.transitions==len(world.connections)
    assert audited.topology_reachable==len(world.places)
    assert audited.topology_goal_recoverable==len(world.places)
    assert audited.unreachable_places==()
    assert audited.no_topological_goal_escape==()
    assert audited.unrewarded_dead_ends==()
    assert audited.initial_visible_secrets==()
    assert audited.fully_executable_original_goal_route
    assert audited.loops>=3
    assert audited.weather_restricted_connections>=3
    assert audited.timetabled_connections>=4
    assert "taxi" in audited.real_public_transport_modes
    assert "rain_route" in audited.real_environmental_modes
    assert "orbital_shuttle" in audited.fictional_and_space_modes
    assert "magic_gate" in audited.fictional_and_space_modes
    proof=demand_viable_world(world,traveller)
    assert proof["schema"]==SCHEMA


def test_original_world_rejects_regions_accessible_by_no_actual_route():
    world,traveller=make_frontier()
    corrupted=replace(world,places=world.places+(
        Place("isolated_copy_free_region",scenic_value=40),))
    result=audit_world(corrupted,traveller)
    assert "isolated_copy_free_region" in result.unreachable_places
    assert "isolated_copy_free_region" in result.no_topological_goal_escape
    with pytest.raises(ValueError,match="accessibility"):
        demand_viable_world(corrupted,traveller)


def test_deadends_need_motivating_reward_or_real_recovery():
    world,traveller=make_frontier()
    nodes=tuple(
        replace(site,gifts=(),scenic_value=0,money_pickup=0,energy_refill=0)
        if site.id=="old_mine" else site for site in world.places
    )
    degraded=replace(world,places=nodes)
    report=audit_world(degraded,traveller)
    assert "old_mine" in report.unrewarded_dead_ends
    with pytest.raises(ValueError):
        demand_viable_world(degraded,traveller)


def test_undiscovered_secret_does_not_get_spoiled_by_a_global_route_menu():
    world,traveller=make_frontier()
    initial=experience(world,traveller)
    assert not any(choice["edge"]=="secret_from_clue"
                   for choice in initial["options"])
    exposed=replace(world,places=tuple(
        replace(node,gifts=node.gifts+("forgotten_cipher",))
        if node.id==world.start else node for node in world.places
    ))
    # Discovery is already learned at start: this is now visible, rather
    # than being reported as undiscovered. Gate still needs the real rune.
    report=audit_world(exposed,traveller)
    assert "secret_from_clue" in report.initial_visible_secrets
    with pytest.raises(ValueError):
        demand_viable_world(exposed,traveller)


def test_cyclic_weather_free_roam_can_escape_mountains_without_wind():
    world,traveller=make_frontier(weather="clear")
    current=experience(world,traveller,path=(
        "cable_approach","cable_up","peak_view","deck_back",
        "cable_down","cable_backtrack",
    ))
    assert current["world_position"]=="crossroads"
    assert current["elapsed_minutes"]>0
    assert "cable_backtrack" in current["played_edges"]
    assert current["remaining_cash"]<traveller.cash


def test_seeded_route_variants_change_real_world_network_and_measured_costs():
    digests=[]
    counts=[]
    for seed in (0,1,2,3,4,5,1977,2026,2**32-1):
        world,_=make_frontier(seed=seed,weather="clear")
        validate_world(world)
        digests.append(scenario_digest(world))
        counts.append(len(world.connections))
        assert len(world.connections)<=192
        assert any(edge.id.startswith("guild_") or
                   edge.id.startswith("open_") or
                   edge.id.startswith("metro_market_")
                   for edge in world.connections if edge.id in
                   {option[0] for option in OPTIONS}) or len(world.connections)>=60
    assert len(set(digests))==len(digests)
    assert all(count>=60 for count in counts)


def test_route_variants_do_not_conflate_billions_of_seeds_with_delivered_games():
    baseline,_=make_frontier(seed=1977)
    variant=original_variant_receipt(baseline,seed=37)
    assert variant["schema"]=="skeleton.ai.dragon.original_world_variants.v1"
    assert variant["source_world_sha256"]!=variant["derived_world_sha256"]
    assert "not equivalent to completed game titles" in variant["limits"]
    assert all(id in {edge.id for edge in mutate_original_world(
        baseline,seed=37).connections} for id in variant["original_optional_routes"])


def test_multi_weather_validation_has_no_hidden_pretense_of_real_world_aviation():
    suite=climate_suite(seed=1977,hour=8)
    assert suite["schema"]==SCHEMA
    assert len(suite["scenarios"])==6
    assert suite["all_six_weather_states_reach_goal"]
    assert all(x["goal_reached"] for x in suite["scenarios"])
    assert all(not x["unreachable"] and not x["no_escape"]
               for x in suite["scenarios"])
    assert "no detailed meteorological physics" in suite["claim"]


def test_current_game_source_does_not_claim_full_resource_softlock_certification():
    world,traveller=make_frontier()
    quality=audit_world(world,traveller)
    assert "resource softlocks" in quality.certification
    assert "specific vehicle physics" in quality.certification
