"""Ten actual replayed world-route strategies per lazy original world address."""
from __future__ import annotations
from dataclasses import replace
import json
import pytest

from skeleton.ai.webcrawler.dragon_living_world import (
    create_world,replay,initial_state,
    WORLD_ADDRESS_COUNT,VARIANTS_PER_ADDRESS,STYLE_NAMES,
)
from skeleton.ai.webcrawler.dragon_living_world_routes import (
    SCHEMA,POLICIES,RECIPES,materialize_route,verify_route,portfolio,indexed_route,
)


@pytest.mark.parametrize("style",[
    "creative_sandbox","survival_sandbox","mutable_labyrinth",
    "rotating_tower","open_world_story","post_story_wasteland",
    "branching_campaign","multiple_world_platform","city_builder",
    "colony_simulation","trading_world","science_exploration",
])
def test_eight_real_strategies_are_playable_in_worlds_without_forced_win(style):
    world=create_world(world_id=2026,variant=3,style=style)
    report=portfolio(world,limit=8)
    assert report["schema"]==SCHEMA
    assert report["sampled"]==8
    assert 1<=report["distinct_replayed_action_sequences"]<=8
    assert len(report["samples"])==8
    assert report["addressable_route_slot_count"]==10
    for number,entry in enumerate(report["samples"]):
        trace=materialize_route(world,number)
        assert entry["slot"]==number
        assert entry["objective"]==POLICIES[number]
        assert tuple(entry["actions"])==trace.actions
        assert entry["ending_replay_digest"]==replay(
            world,trace.actions).history_digest
        assert entry["trace_digest"]==trace.trace_digest
        assert len(trace.endpoints)==len(trace.actions)+1
        assert verify_route(world,trace)["verified"]
        if world.lifecycle=="unending":
            assert not trace.original_endings
            assert not trace.completed_world
            assert trace.remains_playable


def test_ten_path_slots_each_generate_reproducible_real_player_decisions():
    for style in ("mutable_labyrinth","survival_sandbox","open_world_story"):
        world=create_world(world_id=WORLD_ADDRESS_COUNT-1,
                           variant=VARIANTS_PER_ADDRESS-1,style=style)
        routes=[indexed_route(world.world_id,world.variant,n,style=style)
                for n in range(10)]
        assert len(routes)==10
        assert all(v.world_fingerprint==world.world_fingerprint for v in routes)
        assert all(v.actions for v in routes)
        assert all(replay(world,v.actions).history_digest==
                   v.ending_replay_digest for v in routes)
        assert len({v.trace_digest for v in routes})==10
        assert len({v.actions for v in routes})>=6
        assert routes==[
            indexed_route(world.world_id,world.variant,n,style=style)
            for n in range(10)
        ]


def test_original_faction_path_alternatives_have_real_distinct_endings_and_consequences():
    world=create_world(world_id=2048,style="open_world_story")
    civic=materialize_route(world,7)
    wilderness=materialize_route(world,6)
    assert "civic_union" in civic.original_endings
    assert "wilderness_guardian" in wilderness.original_endings
    assert civic.ending_replay_digest!=wilderness.ending_replay_digest
    assert civic.persistent_changes!=wilderness.persistent_changes
    assert civic.remains_playable and wilderness.remains_playable
    assert replay(world,civic.actions).era>=1
    assert replay(world,wilderness.actions).era>=1


def test_non_winning_sandbox_still_has_genuinely_executable_routes_and_no_fabricated_ending():
    world=create_world(world_id=2,style="creative_sandbox")
    for path_id in range(10):
        output=materialize_route(world,path_id)
        assert output.sample_budget==12+path_id
        assert len(output.actions)==output.sample_budget
        assert not output.original_endings
        assert not output.completed_world
        assert output.remains_playable
        assert output.chapters_seen>=0
        assert verify_route(world,output)["world_still_playable"]


def test_replay_custody_rejects_false_ending_resources_or_modification_to_route():
    world=create_world(world_id=42,style="branching_campaign")
    original=materialize_route(world,7)
    with pytest.raises(ValueError):
        verify_route(world,replace(original,completed_world=True,
                                   original_endings=("invented_ending",)))
    with pytest.raises(ValueError):
        verify_route(world,replace(original,actions=original.actions[:-1]))
    with pytest.raises(ValueError):
        verify_route(world,replace(original,ending_replay_digest="0"*64))
    with pytest.raises(ValueError):
        verify_route(world,replace(original,trace_digest="a"*64))
    with pytest.raises(ValueError):
        verify_route(create_world(world_id=43,style="branching_campaign"),original)


@pytest.mark.parametrize("slot",[-1,10,True])
def test_indexed_gameplay_route_rejects_invalid_alternative_slot(slot):
    world=create_world(world_id=4)
    with pytest.raises(ValueError):
        materialize_route(world,slot)


@pytest.mark.parametrize("value",[0,3,49,True,-1])
def test_alternative_samplers_refuse_unbounded_or_invalid_decision_budget(value):
    world=create_world(world_id=0)
    with pytest.raises(ValueError):
        materialize_route(world,4,steps=value)


def test_portfolio_cannot_claim_to_have_materialized_sixteen_million_paths():
    world=create_world(world_id=7,variant=7,style="mutable_labyrinth")
    report=portfolio(world)
    assert report["sampled"]==10
    assert report["addressable_route_slot_count"]==10
    assert "untested address space not certified" in report["claim"]
    assert report["world_has_ending"] is False
    assert len(json.dumps(report))<100_000
    with pytest.raises(ValueError):
        portfolio(world,limit=11)
