"""Playable multi-realm frontier travel: routing, weather, GDD-linked replay."""

from dataclasses import replace
import copy

import pytest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionAction, ExpeditionEpisode, ExpeditionError,
    ExpeditionWeather, ExpeditionWorld, TravelEdge, Traveler, Waypoint,
    alternative_routes, assess_travel, find_route, verify_route,
    world_export, _digest,
)
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile, author_archipelago, playtest_archipelago,
)

SOURCE = "f"*64


def world(weather=None):
    nodes=(
        Waypoint("harbor",0,0,0,"settlement",safe_rest=True),
        Waypoint("cliff",10,0,12,"sky_island",quest_flag="charted",safe_rest=True),
        Waypoint("sky",20,0,17,"sky_island",collectible="artifact"),
        Waypoint("ridge",25,0,17,"sky_island",safe_rest=True),
        Waypoint("exit",30,0,17,"sky_island"),
        Waypoint("reef",0,10,-10,"underwater",safe_rest=True),
        Waypoint("spire",0,15,0,"ruins",landmark="original spire"),
    )
    edges=(
        TravelEdge("launch","harbor","cliff","updraft",20,20,10,
                   requires=("glider",),grants=("air_chart",)),
        TravelEdge("bridge","cliff","sky","rope_bridge",10,18,5,scenic_score=30),
        TravelEdge("ridge_path","sky","ridge","walk",5,6,2,
                   requires=("charted",),scenic_score=20),
        TravelEdge("goal_path","ridge","exit","walk",5,6,2),
        TravelEdge("airship","harbor","sky","airship",21,13,1,
                   requires=("pilot",)),
        TravelEdge("spire_road","harbor","spire","walk",15,35,5,
                   one_way=False),
        TravelEdge("gateway","spire","exit","portal",20,3,0,
                   requires=("portal_key",)),
        TravelEdge("dive","harbor","reef","dive",14,30,10,
                   requires=("dive_gear",)),
        TravelEdge("swim_home","reef","harbor","swim",14,20,8),
        TravelEdge("return_glide","cliff","harbor","glide",23,8,2,
                   requires=("glider",)),
    )
    return ExpeditionWorld(
        "original_realm",SOURCE,nodes,edges,"harbor",("exit",),
        weather or ExpeditionWeather(),
    )


def player(*, modes=None, flags=(), stamina=1000, equipment=()):
    return Traveler(
        permitted_modes=frozenset(modes or (
            "walk","rope_bridge","updraft","glide","airship",
            "portal","dive","swim","climb",
        )),
        flags=frozenset(flags),equipment=frozenset(equipment),
        max_stamina=stamina,skill=.5,
    )


def test_source_world_and_route_digest_are_deterministic():
    a=world(); b=world()
    assert a.digest==b.digest
    assert len(a.digest)==64
    assert world_export(a)==world_export(b)
    assert world_export(a)["content"].find('"device_location_used":false')!=-1


@pytest.mark.parametrize("objective",("fastest","safest","energy","scenic"))
def test_all_four_objective_routes_are_executable(objective):
    w=world()
    p=player(flags=("glider","pilot","portal_key"))
    route=find_route(w,p,"exit",objective=objective)
    assert route.source=="harbor"
    assert route.destination=="exit"
    assert route.world_digest==w.digest
    assert route.edge_ids
    assert route.waypoints[-1]=="exit"
    play=verify_route(w,p,route)
    assert play["verified"]
    assert play["final_state"]["won"]
    assert len(play["step_receipts"])==len(route.edge_ids)
    assert len(play["receipt_head"])==64


def test_route_uses_first_arrival_quest_flag_for_later_connection():
    w=world()
    p=player(flags=("glider",))
    route=find_route(w,p,"exit")
    assert route.edge_ids==("launch","bridge","ridge_path","goal_path")
    replay=verify_route(w,p,route)
    assert replay["final_state"]["won"]
    assert "charted" in replay["final_state"]["flags"]
    assert "artifact" in replay["final_state"]["inventory"]


def test_locked_portal_cannot_be_taken_without_real_quest_or_equipment_flag():
    w=world()
    p=player(modes=("walk","portal"),flags=())
    with pytest.raises(ExpeditionError,match="no traversable route"):
        find_route(w,p,"exit")
    with_key=player(modes=("walk","portal"),flags=("portal_key",))
    route=find_route(w,with_key,"exit")
    assert route.edge_ids==("spire_road","gateway")
    assert verify_route(w,with_key,route)["final_state"]["won"]


def test_undirected_footpath_materializes_source_bound_reverse_edge():
    w=world()
    assert w.by_edge["spire_road.reverse"].source=="spire"
    assert w.by_edge["spire_road.reverse"].target=="harbor"
    ep=ExpeditionEpisode(w,player(modes=("walk",)))
    ep.step(ExpeditionAction("travel","spire_road"))
    ep.step(ExpeditionAction("travel","spire_road.reverse"))
    assert ep.position=="harbor"
    assert len(ep.receipts)==2


def test_bad_jump_and_wrong_direction_cannot_modify_state():
    w=world()
    ep=ExpeditionEpisode(w,player(flags=("glider",)))
    before=ep.snapshot()
    with pytest.raises(ExpeditionError,match="connected outgoing"):
        ep.step(ExpeditionAction("travel","goal_path"))
    with pytest.raises(ExpeditionError,match="connected outgoing"):
        ep.step(ExpeditionAction("travel","not_a_real_edge"))
    assert ep.snapshot()==before


def test_stamina_is_actually_spent_and_shortage_blocks_route():
    w=world()
    low=player(flags=("glider",),stamina=1)
    with pytest.raises(ExpeditionError,match="no traversable route"):
        find_route(w,low,"exit")
    ep=ExpeditionEpisode(w,low)
    with pytest.raises(ExpeditionError,match="insufficient"):
        ep.step(ExpeditionAction("travel","launch"))
    assert ep.position=="harbor"
    assert ep.stamina==1


def test_rest_only_at_authored_safe_sites_and_recovers_energy():
    ep=ExpeditionEpisode(world(),player(flags=("glider",)))
    ep.step(ExpeditionAction("travel","launch"))
    energy=ep.stamina
    outcome=ep.step(ExpeditionAction("rest"))
    assert ep.stamina>energy
    assert outcome["events"][0].startswith("rested:")
    ep.step(ExpeditionAction("travel","bridge"))
    before=ep.snapshot()
    with pytest.raises(ExpeditionError,match="no authored rest"):
        ep.step(ExpeditionAction("rest"))
    assert ep.snapshot()==before


def test_weather_changes_stamina_duration_risk_and_traction():
    clear=world(ExpeditionWeather())
    storm=world(ExpeditionWeather(
        wind_x_mps=-22,vertical_mps=-8,turbulence=.8,rain=1,
        visibility=.5,temperature_c=-5,
    ))
    p=player(flags=("glider",))
    a=assess_travel(clear,clear.by_edge["launch"],p)
    b=assess_travel(storm,storm.by_edge["launch"],p)
    assert b.stamina>a.stamina
    assert b.duration_s>a.duration_s
    assert b.traction<a.traction


def test_blind_aerial_travel_requires_real_instrument_capability():
    fog=world(ExpeditionWeather(visibility=.08))
    p=player(flags=("glider",))
    assert not assess_travel(fog,fog.by_edge["launch"],p).allowed
    with pytest.raises(ExpeditionError,match="no traversable route"):
        find_route(fog,p,"exit")
    equipped=player(flags=("glider",),equipment=("instrument_navigation",))
    assert assess_travel(fog,fog.by_edge["launch"],equipped).allowed


def test_resource_weight_raises_actual_traversal_cost():
    w=world()
    light=player(flags=("glider",))
    heavy=Traveler(
        permitted_modes=light.permitted_modes,flags=light.flags,
        max_stamina=1000,carried_kg=29,capacity_kg=30,skill=light.skill,
    )
    a=assess_travel(w,w.by_edge["launch"],light)
    b=assess_travel(w,w.by_edge["launch"],heavy)
    assert b.stamina>a.stamina and b.duration_s>a.duration_s


def test_different_authored_routes_are_not_duplicate_placeholders():
    w=world()
    p=player(flags=("glider","pilot","portal_key"))
    paths=alternative_routes(w,p,"exit",limit=8)
    assert len(paths)>=2
    assert len({p.edge_ids for p in paths})==len(paths)
    assert all(verify_route(w,p,path)["final_state"]["won"] for path in paths)


def test_episode_save_restore_replays_actual_immutable_actions():
    w=world()
    p=player(flags=("glider",))
    original=ExpeditionEpisode(w,p)
    for action in ("launch","bridge"):
        original.step(ExpeditionAction("travel",action))
    original.step(ExpeditionAction("inspect"))
    snapshot=original.snapshot()
    replay=ExpeditionEpisode.restore(w,p,snapshot)
    assert replay.snapshot()==snapshot
    assert replay.position==original.position
    assert replay.inventory=={"artifact"}
    assert len(replay.receipts)==3


def test_tampered_action_or_game_state_fails_replay_even_with_new_checksum():
    w=world()
    p=player(flags=("glider",))
    ep=ExpeditionEpisode(w,p)
    ep.step(ExpeditionAction("travel","launch"))
    original=ep.snapshot()
    forged=copy.deepcopy(original)
    forged["actions"][0]["edge_id"]="airship"
    forged["snapshot_digest"]=_digest({k:v for k,v in forged.items() if k!="snapshot_digest"})
    with pytest.raises(ExpeditionError):
        ExpeditionEpisode.restore(w,p,forged)
    forged=copy.deepcopy(original)
    forged["state_digest"]="f"*64
    with pytest.raises(ExpeditionError,match="checksum"):
        ExpeditionEpisode.restore(w,p,forged)


def test_snapshot_different_weather_or_source_is_rejected():
    w=world()
    p=player(flags=("glider",))
    snap=ExpeditionEpisode(w,p).snapshot()
    with pytest.raises(ExpeditionError,match="different world"):
        ExpeditionEpisode.restore(world(ExpeditionWeather(rain=.4)),p,snap)
    with pytest.raises(ExpeditionError,match="traveler source"):
        ExpeditionEpisode.restore(w,player(flags=("glider","extra")),snap)


def test_terminal_victory_is_final_and_no_postgame_mutation():
    w=world()
    ep=ExpeditionEpisode(w,player(flags=("portal_key",),modes=("walk","portal")))
    ep.step(ExpeditionAction("travel","spire_road"))
    result=ep.step(ExpeditionAction("travel","gateway"))
    assert result["won"] and result["done"]
    with pytest.raises(ExpeditionError,match="finished expedition"):
        ep.step(ExpeditionAction("inspect"))


def test_invalid_world_edges_are_rejected_by_authoritative_graph():
    with pytest.raises(ExpeditionError,match="unsupported movement mode"):
        TravelEdge("bad","harbor","sky","fly",1,1,1)
    with pytest.raises(ExpeditionError,match="loop"):
        TravelEdge("bad","harbor","harbor","walk",1,1,1)


def test_missing_link_duplicate_node_and_impossible_updraft_fail():
    nodes=(Waypoint("a",0,0,0,"ground"),Waypoint("b",0,0,1,"sky_island"))
    with pytest.raises(ExpeditionError,match="duplicate"):
        ExpeditionWorld("foo",SOURCE,(nodes[0],nodes[0]),
                        (TravelEdge("road","a","b","walk",1,1,1),),"a",("a",))
    with pytest.raises(ExpeditionError,match="missing waypoint"):
        ExpeditionWorld("foo",SOURCE,nodes,
                        (TravelEdge("road","a","c","walk",1,1,1),),"a",("b",))
    with pytest.raises(ExpeditionError,match="updraft"):
        ExpeditionWorld("foo",SOURCE,nodes,
                        (TravelEdge("bad","b","a","updraft",1,1,1),),"a",("b",))


@pytest.mark.parametrize("n",(-1,0,257,1.2,True))
def test_archipelago_generation_fails_on_invalid_island_counts(n):
    with pytest.raises(ExpeditionError,match="islands"):
        ArchipelagoProfile(seed=3,islands=n)


@pytest.mark.parametrize("n",(3,7,12,24))
def test_original_sky_archipelago_is_seeded_playable_and_multirealm(n):
    profile=ArchipelagoProfile(seed=74219,islands=n)
    a=author_archipelago("sky_world",SOURCE,profile)
    b=author_archipelago("sky_world",SOURCE,profile)
    assert a.digest==b.digest
    assert a.destinations==(f"island_{n:03d}",)
    assert len(a.waypoints)>n
    assert {"sky_island","cavern","underwater","ruins"}.issubset(
        {c.kind for c in a.waypoints}
    )
    proof=playtest_archipelago(a,max_routes=4)
    assert proof["all_ended_at_destination"]
    assert proof["routes_executed"]>=2
    assert len(proof["receipt_digest"])==64


def test_archipelago_seed_actually_changes_layout_not_just_metadata():
    a=author_archipelago("game",SOURCE,ArchipelagoProfile(seed=1))
    b=author_archipelago("game",SOURCE,ArchipelagoProfile(seed=2))
    assert a.digest!=b.digest
    assert a.by_id["island_001"].x_m!=b.by_id["island_001"].x_m


def test_archipelago_optional_realms_can_be_disabled_without_breaking_goal():
    a=author_archipelago("game",SOURCE,ArchipelagoProfile(
        seed=3,include_underwater=False,include_portals=False,caverns=0,
    ))
    assert all(w.kind!="underwater" for w in a.waypoints)
    assert all(e.mode!="portal" for e in a.edges)
    assert playtest_archipelago(a)["all_ended_at_destination"]


def test_player_requires_real_capability_for_vertical_link():
    a=author_archipelago("game",SOURCE,ArchipelagoProfile(seed=3))
    p=player(modes=("walk","rope_bridge"),stamina=1000)
    with pytest.raises(ExpeditionError,match="no traversable route"):
        find_route(a,p,a.destinations[0])


@pytest.mark.parametrize("seed",(0,1,55,1234,2**32))
def test_generated_world_replay_is_fully_deterministic(seed):
    profile=ArchipelagoProfile(seed=seed,islands=8)
    a=author_archipelago("replay",SOURCE,profile)
    first=playtest_archipelago(a,max_routes=3)
    second=playtest_archipelago(
        author_archipelago("replay",SOURCE,profile),max_routes=3,
    )
    assert first==second
