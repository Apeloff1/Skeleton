"""Original free-roam game-world routing: real multimodal state transitions."""
from __future__ import annotations

from dataclasses import asdict,replace
import json
import pytest

from skeleton.ai.webcrawler.dragon_route_taxonomy import (
    FAMILIES,MODES,ROUTE_SHAPES,ENVIRONMENT_FLAGS,capabilities,modality,
)
from skeleton.ai.webcrawler.dragon_route_world import (
    SCHEMA,MAX_EXPANSIONS,Place,Traverse,World,Traveller,
    Journey,plan,replay,portfolio,route_dictionary,verify_portfolio,
    validate_world,
)
from skeleton.ai.webcrawler.dragon_route_world_factory import (
    make_frontier,scenario_digest,structural_report,
)


def test_route_taxonomy_has_actual_mode_classification_not_160k_fake_game_titles():
    report=capabilities()
    assert report["schema"]=="skeleton.ai.dragon.route_taxonomy.v1"
    assert len(MODES)>=190
    assert len(FAMILIES)>=9
    assert all(MODES[x] in FAMILIES for x in MODES)
    for name in (
        "taxi","bus","high_speed_rail","airplane","passenger_jet",
        "ferry","cargo_ship","submarine","wind_tunnel","rain_route",
        "glider","portal","teleporter","magic_gate","orbital_shuttle",
        "deep_space_cruise","stargate","network_tunnel","dream_path",
        "wheelchair","elevator","horse","lava_bridge",
    ):
        assert name in MODES
        assert modality(name).native_specific_physics is False
    assert "secret_unlockable" in ROUTE_SHAPES
    assert "storm" in ENVIRONMENT_FLAGS
    with pytest.raises(ValueError):
        modality("brand_copyrighted_portal")


@pytest.mark.parametrize("weather",["clear","rain","windy","storm","snow","high_tide"])
def test_generated_original_world_is_bounded_connected_and_physically_playable(weather):
    world,hero=make_frontier(seed=2026,weather=weather)
    validate_world(world)
    assert world.original_work_attested
    assert world.source_origin=="generated_original"
    assert 30<=len(world.places)<=48
    assert 60<=len(world.connections)<=192
    assert len({x.id for x in world.connections})==len(world.connections)
    assert len({x.id for x in world.places})==len(world.places)
    solution,expanded,truncated=plan(world,hero,objective="fastest",
                                    expansion_cap=5000)
    assert solution is not None and solution.success
    assert solution.places[0]==world.start and solution.places[-1]==world.goal
    assert solution.length==len(solution.edges)
    assert solution.money_spent<=hero.cash
    assert solution.elapsed_minutes<=world.max_minutes
    assert solution.digest==replay(world,solution.edges,hero,objective="fastest").digest
    assert expanded>=1
    assert len(scenario_digest(world))==64


def test_taxi_and_public_transit_have_real_fares_and_timelines():
    world,hero=make_frontier()
    taxi=replay(world,("walk_to_bazaar","market_to_taxi","taxi_to_goal"),hero)
    assert taxi.success
    assert taxi.money_spent==45
    assert taxi.modes[-1]=="taxi"
    assert taxi.elapsed_minutes==29
    bus=replay(world,("walk_to_bazaar","market_to_bus","bus_to_goal"),hero)
    assert bus.money_spent==6
    assert bus.waiting_minutes>0
    assert bus.elapsed_minutes>bus.movement_minutes
    train=replay(world,("walk_to_bazaar","market_to_train","train_to_goal"),hero)
    assert train.money_spent==25
    assert train.modes[-1]=="high_speed_rail"


def test_free_roaming_real_cycles_and_deadend_clues_are_not_fake_shortcuts():
    world,hero=make_frontier()
    actual=replay(world,(
        "forest_entry","forest_to_meadow","meadow_to_river",
        "river_to_forest","forest_to_meadow","meadow_to_goal",
    ),hero,objective="wandering")
    assert actual.loops>=1
    assert "loop" in actual.shapes
    assert actual.visited_places<len(actual.places)
    assert "free_roam" in actual.shapes
    assert actual.success
    report=structural_report(world)
    assert "old_mine" in report["dead_end_places"]
    assert report["real_cycle_edges"]>=3
    assert report["actual_fastest_found"]
    assert report["secret_routes"]>=3
    assert report["timed_routes"]>=4
    assert report["weather_routes"]>=3


def test_secret_unlock_is_actually_unavailable_without_deadend_clue_and_ruin_rune():
    world,hero=make_frontier()
    with pytest.raises(ValueError,match="locked or unsafe"):
        replay(world,("secret_from_clue","grotto_to_tunnel","tunnel_to_citadel"),hero)
    with pytest.raises(ValueError):
        replay(world,("forest_entry","forest_to_ruins","ruins_return",
                      "secret_from_clue","grotto_to_tunnel","tunnel_to_citadel"),hero)
    with pytest.raises(ValueError):
        replay(world,("mine_sidepath","mine_return","secret_from_clue",
                      "grotto_to_tunnel","tunnel_to_citadel"),hero)
    legal=replay(world,(
        "forest_entry","forest_to_ruins","ruins_return",
        "mine_sidepath","mine_return",
        "secret_from_clue","grotto_to_tunnel","tunnel_to_citadel",
    ),hero)
    assert legal.secret_edges>=3
    assert legal.unlockable_edges>=2
    assert legal.elapsed_minutes>100
    assert legal.loops>=1
    assert legal.success


def test_wind_rain_and_tide_weather_physics_do_not_generate_always_open_shortcuts():
    wind,recruit=make_frontier(weather="windy")
    wind_route=("cable_approach","cable_up","wind_shortcut")
    proof=replay(wind,wind_route,recruit)
    assert proof.success and proof.environmental_edges==1
    clear,_=make_frontier(weather="clear")
    with pytest.raises(ValueError):
        replay(clear,wind_route,recruit)
    rain,rain_hero=make_frontier(weather="rain")
    rainy=("walk_to_bazaar","market_to_rain","rain_flood_route")
    assert replay(rain,rainy,rain_hero).success
    with pytest.raises(ValueError):
        replay(clear,rainy,recruit)
    tide,mariner=make_frontier(weather="high_tide")
    assert replay(tide,("walk_to_bazaar","harbor_path","tidal_shortcut"),mariner).success
    with pytest.raises(ValueError):
        replay(clear,("walk_to_bazaar","harbor_path","tidal_shortcut"),recruit)


def test_real_air_plane_ferry_and_space_itineraries_consume_time_money_and_gates():
    world,hero=make_frontier(hour=8)
    plane=replay(world,(
        "walk_to_bazaar","airport_path","airplane_depart","airplane_arrive",
    ),hero)
    assert plane.success and "passenger_jet" in plane.modes
    assert plane.money_spent==86
    assert plane.waiting_minutes>=0
    ferry=replay(world,("walk_to_bazaar","harbor_path","ferry_to_goal"),hero)
    assert ferry.success and ferry.money_spent==15
    space=replay(world,(
        "spaceport_access","shuttle_to_orbit","orbit_to_moon","moon_to_citadel",
    ),hero)
    assert space.success and "orbital_shuttle" in space.modes
    assert "wormhole" in space.modes
    assert "world_transition" in space.shapes
    assert space.elapsed_minutes>180
    assert space.fuel_used==45
    assert space.mana_used==15
    assert space.money_spent>ferry.money_spent
    assert space.sights>0
    no_ticket=replace(hero,cash=50)
    with pytest.raises(ValueError):
        replay(world,space.edges,no_ticket)


def test_mystical_teleport_needs_real_ruin_rune_not_an_unconditional_global_fast_travel():
    world,hero=make_frontier()
    with pytest.raises(ValueError):
        replay(world,("magic_gateway",),hero)
    route=replay(world,(
        "forest_entry","forest_to_ruins","magic_circle_entry","magic_gateway",
    ),hero)
    assert route.success
    assert route.modes[-1]=="magic_gate"
    assert route.unlockable_edges>=2
    assert route.elapsed_minutes>60


def test_routing_requires_real_waypoints_modes_and_shapes():
    world,hero=make_frontier(weather="windy")
    result,states,truncated=plan(
        world,hero,objective="fastest",requires=("mode:glider",),
        expansion_cap=10000,
    )
    assert result is not None and "glider" in result.modes
    assert states>0
    result2,_,_=plan(
        world,hero,objective="balanced",requires=("shape:free_roam",),
        expansion_cap=10000,
    )
    assert result2 and "free_roam" in result2.shapes
    result3,_,_=plan(
        world,hero,objective="exploratory",requires=("family:air",),
        expansion_cap=15000,
    )
    assert result3 and any(MODES[x]=="air" for x in result3.modes)


def test_original_multisolver_portfolio_has_actual_distinct_winning_journeys():
    world,hero=make_frontier()
    selected=portfolio(world,hero,max_routes=7,expansion_cap=3500)
    assert selected.schema==SCHEMA
    assert 2<=len(selected.routes)<=7
    assert len({journey.edges for journey in selected.routes})==len(selected.routes)
    assert any("taxi" in result.modes or "bus" in result.modes or
               "metro" in result.modes for result in selected.routes)
    assert all(replay(world,result.edges,hero,objective=result.objective).digest==
               result.digest for result in selected.routes)
    evidence=json.loads(json.dumps(route_dictionary(selected)))
    assert verify_portfolio(world,hero,evidence)["verified_routes"]==len(selected.routes)
    evidence["routes"][0]["money_spent"]+=1
    with pytest.raises(ValueError):
        verify_portfolio(world,hero,evidence)


def test_impractical_space_or_sea_paths_are_valid_even_when_significantly_longer():
    world,hero=make_frontier()
    fastest,_,_=plan(world,hero,objective="fastest")
    result,_,_=plan(world,hero,objective="impractical",minimum_minutes=180,
                    expansion_cap=15000)
    assert fastest is not None and result is not None
    assert result.elapsed_minutes>=180
    assert result.elapsed_minutes>fastest.elapsed_minutes
    assert result.success


@pytest.mark.parametrize("bad_world",[
    lambda w:replace(w,original_work_attested=False),
    lambda w:replace(w,source_origin="extracted_commercial_map"),
    lambda w:replace(w,start=w.goal),
    lambda w:replace(w,connections=w.connections+(w.connections[0],)),
    lambda w:replace(w,connections=(
        replace(w.connections[0],mode="unlicensed_game_vehicle"),)+w.connections[1:]),
    lambda w:replace(w,connections=(
        replace(w.connections[0],secret_token="",shapes=("secret",)),)+w.connections[1:]),
])
def test_illegal_provenance_impossible_edges_and_forged_secrets_fail_closed(bad_world):
    world,_=make_frontier()
    with pytest.raises((ValueError,PermissionError)):
        validate_world(bad_world(world))


@pytest.mark.parametrize("condition",[
    ("objective","secret_punishment"),
    ("minimum_minutes",-1),
    ("minimum_minutes",999999),
    ("expansion_cap",10),
    ("requires",("shape:unknown_shape",)),
    ("requires",("family:copyrighted_world",)),
])
def test_route_search_refuses_unbounded_or_unverifiable_planning_intent(condition):
    world,hero=make_frontier()
    with pytest.raises(ValueError):
        plan(world,hero,**{condition[0]:condition[1]})



def test_underwater_tunnels_pay_actual_bounded_oxygen_and_do_not_magic_refill():
    world,traveller=make_frontier(seed=1977)
    actions=("walk_to_bazaar","harbor_path","harbor_to_reef",
             "reef_to_gate","gate_to_goal")
    dive=replay(world,actions,traveller)
    assert dive.success
    assert dive.oxygen_used==37
    assert dive.fuel_used==0 and dive.mana_used==0
    assert "dive" in dive.modes
    exhausted=replace(traveller,oxygen=36)
    with pytest.raises(ValueError,match="locked or unsafe"):
        replay(world,actions,exhausted)
    with pytest.raises(ValueError):
        replay(world,actions,replace(traveller,oxygen=-1))


def test_space_travel_and_arcane_shortcuts_require_actual_fuel_and_mana():
    world,hero=make_frontier(seed=1977)
    flight=("spaceport_access","shuttle_to_orbit",
            "orbit_to_moon","moon_to_citadel")
    for resource in ("fuel","mana"):
        with pytest.raises(ValueError):
            replay(world,flight,replace(hero,**{resource:0}))
    magic=("forest_entry","forest_to_ruins",
           "magic_circle_entry","magic_gateway")
    assert replay(world,magic,hero).mana_used==12
    with pytest.raises(ValueError):
        replay(world,magic,replace(hero,mana=11))


def test_original_multimodal_free_roaming_reports_live_resource_visibility():
    world,hero=make_frontier(seed=1977)
    route=("walk_to_bazaar","harbor_path","harbor_to_reef")
    at_reef=experience(world,hero,path=route)
    assert at_reef["remaining_oxygen"]==60
    assert at_reef["remaining_fuel"]==60
    assert at_reef["remaining_mana"]==60
    dive=next(x for x in at_reef["options"] if x["edge"]=="reef_to_gate")
    assert dive["available"] is True
    assert dive["oxygen"]==22
    underwater=experience(world,hero,path=route+("reef_to_gate",))
    assert underwater["remaining_oxygen"]==38
    assert underwater["world_position"]=="submerged_gate"
    drained=experience(world,replace(hero,oxygen=20),path=route)
    blocked=next(x for x in drained["options"] if x["edge"]=="reef_to_gate")
    assert not blocked["available"]
    assert blocked["access"]=="oxygen_required"
