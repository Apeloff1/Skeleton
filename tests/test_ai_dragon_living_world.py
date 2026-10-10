"""Playability is not the same as winnability in original Dragon worlds."""
from __future__ import annotations

from dataclasses import asdict,replace
import json
import pytest

from skeleton.ai.webcrawler.dragon_living_world import (
    SCHEMA, STYLE_NAMES, STYLE_RULES, LIFECYCLES, WORLD_ADDRESS_COUNT,
    VARIANTS_PER_ADDRESS,ADDRESSABLE_VARIATION_SLOTS,MAX_HISTORY,MAX_ABS_COORD,
    create_world,validate_world,catalog,initial_state,terrain,atmosphere,
    options,replay,take_action,describe,journal,LivingState,
)


def choices(world,state):
    return {entry["name"]:entry for entry in options(world,state)}


def test_catalog_has_32_real_rule_profiles_and_no_false_completed_games():
    report=catalog()
    assert report["schema"]=="skeleton.ai.dragon.living_world_catalog.v1"
    assert report["world_style_count"]>=32
    assert set(report["styles"])==set(STYLE_NAMES)
    assert len(set(STYLE_NAMES))==len(STYLE_NAMES)
    assert all(STYLE_RULES[key] for key in STYLE_NAMES)
    assert all(meta["playability_is_not_win_condition"]
               for meta in report["styles"].values())
    assert report["addressable_world_ids"]==1_600_000
    assert report["variants_per_world_id"]==10
    assert report["addressable_world_variant_slots"]==16_000_000
    assert "not 16m finished" in report["claims"]
    assert {"unending","postgame","multiple_endings","mandatory_completion",
            "permadeath","restartable_runs","optional_endings"}<=set(LIFECYCLES)


@pytest.mark.parametrize("style",[
    "creative_sandbox","survival_sandbox","persistent_survival",
    "living_ecosystem","endless_expedition","mutable_labyrinth",
    "rotating_tower","shifting_dungeon","colony_simulation",
    "city_builder","farming_life_sim","trading_world",
])
def test_unending_worlds_are_real_playable_games_without_any_final_boss(style):
    world=create_world(world_id=13,variant=7,style=style)
    assert world.lifecycle=="unending"
    assert not world.includes_goal
    assert world.allows_continuation
    start=initial_state(world)
    display=describe(world,start)
    assert display["playable"] and not display["has_completed_ending"]
    assert display["fixed_winning_condition_exists"] is False
    assert all(not entry["name"].startswith("ending_")
               for entry in display["options"])
    run=replay(world,("observe","forage","wait","rest","observe","forage"))
    assert run.turn==6
    assert run.alive
    assert run.endings_seen==()
    assert describe(world,run)["playable"]


@pytest.mark.parametrize("style",STYLE_NAMES)
def test_every_authored_world_genre_has_valid_real_playable_start(style):
    world=create_world(world_id=37,variant=8,style=style)
    validate_world(world)
    entry=initial_state(world)
    state=describe(world,entry)
    assert state["player"]["realm"]==0
    assert state["playable"]
    assert state["tile"]["authored_origin"].startswith("seeded_original")
    assert any(p["available"] for p in state["options"])
    safe=replay(world,("observe","forage","wait","rest"))
    assert safe.actions_played==4
    assert safe.turn==4
    assert safe.history_digest!=entry.history_digest
    assert safe==replay(world,("observe","forage","wait","rest"))


def test_persistent_open_world_story_really_continues_after_major_ending():
    world=create_world(world_id=47,style="open_world_story")
    assert world.lifecycle=="postgame"
    opening=initial_state(world)
    with pytest.raises(ValueError):
        take_action(world,opening,"ending_civic_union")
    history=("help_settlers","help_settlers","ending_civic_union")
    outcome=replay(world,history)
    assert outcome.endings_seen==("civic_union",)
    assert outcome.era==1
    assert outcome.allies>=5
    assert "era_civic_union" in outcome.world_changes
    assert "civic_trust" in outcome.world_changes
    display=describe(world,outcome)
    assert display["has_completed_ending"]
    assert display["postgame_active"]
    assert display["playable"]
    assert any(choice["name"]=="forage" for choice in display["options"])
    after=take_action(world,outcome,"forage")
    assert after.food>outcome.food
    assert after.era==1
    assert after.endings_seen==outcome.endings_seen
    assert after.history_digest!=outcome.history_digest


def test_narrative_choices_are_persistent_irreversible_civic_vs_wild_alignments():
    world=create_world(world_id=3,style="post_story_wasteland")
    civic=replay(world,("help_settlers","help_settlers"))
    wild=replay(world,("help_wilds","help_wilds"))
    assert civic.faction_civic==2 and civic.faction_wild==-2
    assert wild.faction_wild==2 and wild.faction_civic==-2
    assert choices(world,civic)["ending_civic_union"]["available"]
    assert not choices(world,wild)["ending_civic_union"]["available"]
    assert choices(world,wild)["ending_wilderness_guardian"]["available"]
    assert civic.world_changes!=wild.world_changes
    assert civic.history_digest!=wild.history_digest
    civic_end=take_action(world,civic,"ending_civic_union")
    wild_end=take_action(world,wild,"ending_wilderness_guardian")
    assert civic_end.settlement_level>wild_end.settlement_level
    assert wild_end.wood>civic_end.wood


def test_multiple_distinct_endings_can_coexist_and_keep_world_playable():
    world=create_world(world_id=0,style="branching_campaign")
    run=replay(world,(
        "help_settlers","help_settlers","ending_civic_union",
        "help_wilds","help_wilds","help_wilds","help_wilds",
        "ending_wilderness_guardian",
    ))
    assert set(run.endings_seen)=={"civic_union","wilderness_guardian"}
    assert run.era==2
    assert describe(world,run)["playable"]
    assert describe(world,run)["postgame_active"]
    assert all(item["name"]!="ending_civic_union"
               for item in options(world,run))


def test_story_mandatory_goal_really_terminates_normal_play_after_ending():
    world=create_world(world_id=123,style="strategy_frontier")
    assert world.lifecycle=="mandatory_completion"
    goal=replay(world,("help_settlers","help_settlers","ending_civic_union"))
    state=describe(world,goal)
    assert state["has_completed_ending"]
    assert not state["playable"]
    assert set(x["name"] for x in state["options"])=={"restart_run"}
    with pytest.raises(ValueError):
        take_action(world,goal,"forage")
    assert take_action(world,goal,"restart_run").run==1


@pytest.mark.parametrize("style",["mutable_labyrinth","rotating_tower",
                                   "shifting_dungeon","time_loop_maze",
                                   "living_castle"])
def test_twisting_maze_actually_changes_open_routes_as_player_moves(style):
    world=create_world(world_id=1977,variant=3,style=style)
    assert world.shifting_routes
    initial=initial_state(world)
    states=[]
    for tick in range(8):
        at=replace(initial,turn=tick)
        open_dirs={item["name"] for item in options(world,at)
                   if item["available"] and
                   item["name"] in ("north","east","south","west")}
        assert open_dirs
        assert ("north","east","south","west")[tick%4] in open_dirs
        states.append(open_dirs)
    assert len({frozenset(state) for state in states})>=2
    stepped=take_action(world,initial,"north")
    assert stepped.turn==1
    assert (stepped.x,stepped.y)==(0,-1)
    assert stepped.history_digest!=initial.history_digest
    # The player may pause to let doors rotate: no mandatory fixed goal.
    repeated=replay(world,("wait","wait","wait","wait","rest"))
    assert repeated.turn==5 and repeated.alive


def test_shifting_maze_exposes_reasons_for_closed_dynamic_wall():
    world=create_world(world_id=1937,style="mutable_labyrinth")
    state=initial_state(world)
    blocked=[x for x in options(world,state)
             if x["name"] in ("north","east","south","west")
             and not x["available"]]
    assert blocked
    assert all(x["reason"]=="moving_wall" for x in blocked)


def test_multi_realm_worlds_have_actual_portals_and_reversible_realm_hopping():
    world=create_world(world_id=99,style="multiple_world_platform",variant=3)
    assert 3<=world.realms<=12
    baseline=initial_state(world)
    assert all(not v["available"] for v in options(world,baseline)
               if v["name"].startswith("portal_"))
    ready=take_action(world,baseline,"observe")
    available={v["name"]:v for v in options(world,ready)
               if v["name"].startswith("portal_")}
    assert "portal_1" in available and available["portal_1"]["available"]
    hopped=take_action(world,ready,"portal_1")
    assert hopped.realm==1 and (hopped.x,hopped.y)==(0,0)
    assert hopped.chapter>ready.chapter
    assert choices(world,hopped)["portal_0"]["available"]
    returned=take_action(world,hopped,"portal_0")
    assert returned.realm==0
    assert returned.history_digest!=baseline.history_digest


def test_survival_crafting_farming_trade_mining_and_research_are_actual_state_transitions():
    world=create_world(world_id=77,style="colony_simulation")
    first=replay(world,("mine","mine","forage","build","farm"))
    assert first.ore>=4
    assert first.shelter==1
    assert first.settlement_level==1
    assert "settlement_built" in first.world_changes
    assert "farm_established" in first.world_changes
    assert first.food>0
    settled=take_action(world,first,"trade")
    assert settled.trade==1
    assert settled.ore==first.ore-1
    evolved=take_action(world,take_action(world,settled,"forage"),"craft")
    assert evolved.research==1
    assert evolved.crystal>=1


def test_ending_replay_journal_has_real_authenticated_source_chain_per_choice():
    world=create_world(world_id=12345,variant=6,style="open_world_story")
    actions=("help_settlers","help_settlers","ending_civic_union",
             "observe","forage","wait")
    record=journal(world,actions)
    assert record["replay_verified"]
    assert len(record["steps"])==len(actions)
    assert len({entry["digest"] for entry in record["steps"]})==len(actions)
    assert record["steps"][2]["endings_seen"]==["civic_union"]
    assert record["final"]["postgame_active"]
    assert record["final"]["player"]["world_changes"]
    assert record["world_fingerprint"]==world.world_fingerprint
    assert json.loads(json.dumps(record))["schema"]==SCHEMA


@pytest.mark.parametrize("world_id,variant",[
    (0,0),(1,9),(9999,5),(WORLD_ADDRESS_COUNT-1,VARIANTS_PER_ADDRESS-1),
])
def test_lazily_addressed_worlds_recreate_identical_original_terrain(world_id,variant):
    world=create_world(world_id=world_id,variant=variant)
    same=create_world(world_id=world_id,variant=variant)
    assert world==same
    assert len(world.world_fingerprint)==64
    for realm in (0,world.realms-1):
        before=terrain(world,realm,10_001,-10_001)
        after=terrain(same,realm,10_001,-10_001)
        assert before==after
    assert world.seed==same.seed
    assert describe(world,initial_state(world))["playable"]


@pytest.mark.parametrize("invalid",[
    {"world_id":-1},{"world_id":WORLD_ADDRESS_COUNT},{"world_id":True},
    {"variant":-1},{"variant":VARIANTS_PER_ADDRESS},{"variant":True},
    {"style":"copied_commercial_game"},{"lifecycle":"every_world_must_win"},
    {"style":"city_builder","lifecycle":"permadeath"},
])
def test_invalid_world_address_style_or_incompatible_game_lifecycle_fails_closed(invalid):
    with pytest.raises(ValueError):
        create_world(**invalid)


def test_game_engine_refuses_forged_worlds_unavailable_actions_and_raw_state():
    world=create_world(world_id=1977,style="mutable_labyrinth")
    state=initial_state(world)
    with pytest.raises(ValueError):
        validate_world(replace(world,world_id=1999))
    with pytest.raises(PermissionError):
        validate_world(replace(world,original_work_attested=False))
    with pytest.raises(ValueError):
        take_action(world,state,"ending_civic_union")
    with pytest.raises(ValueError):
        take_action(world,state,"run arbitrary command")
    with pytest.raises(ValueError):
        replay(world,("wait",)*(MAX_HISTORY+1))
    with pytest.raises(ValueError):
        terrain(world,0,MAX_ABS_COORD+1,0)
    with pytest.raises(ValueError):
        take_action(world,replace(state,health=-1),"wait")



def test_hardcore_survival_world_can_end_player_run_without_ending_game_universe():
    world=create_world(world_id=404,style="hardcore_roguelike")
    assert world.lifecycle=="permadeath"
    journey=replay(world,("wait",)*70)
    assert not journey.alive
    assert journey.health==0
    assert not describe(world,journey)["playable"]
    assert set(x["name"] for x in options(world,journey))=={"restart_run"}
    recovered=take_action(world,journey,"restart_run")
    assert recovered.alive
    assert recovered.run==1
    assert recovered.legacy==1
    assert recovered.history_digest!=initial_state(world).history_digest


def test_original_negative_coordinate_discovery_is_encoded_safely_and_replays():
    world=create_world(world_id=1977,style="mutable_labyrinth")
    north=replay(world,("north","observe"))
    assert north.y==-1
    assert north.discoveries
    assert all("-" not in key and key.startswith("r0_")
               for key in north.discoveries)
    assert "m1" in north.discoveries[0]
    assert north==replay(world,("north","observe"))


def test_changing_world_climate_and_time_do_not_require_a_final_victory():
    world=create_world(world_id=1937,style="living_ecosystem")
    before=initial_state(world)
    early=atmosphere(world,before)
    late=replay(world,("wait",)*33)
    later=atmosphere(world,late)
    assert early["season"]!=later["season"]
    assert early["maze_phase"]!=later["maze_phase"]
    assert later["epoch"]>early["epoch"]
    assert describe(world,late)["playable"]
    assert not world.includes_goal


def test_survival_endurance_can_be_continued_without_forced_ending():
    world=create_world(world_id=93,style="persistent_survival")
    state=replay(world,("forage","wait","rest")*40)
    assert state.alive and state.turn==120
    assert state.food>0
    assert not state.endings_seen
    assert describe(world,state)["playable"]
