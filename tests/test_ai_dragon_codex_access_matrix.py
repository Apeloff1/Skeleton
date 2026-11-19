"""Chronological, seasonal and era-conditioned world access is actual gameplay."""
from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_world_codex import (
    AXIS_NAMES,DOMAINS,edit,unrank,
)
from skeleton.ai.webcrawler.dragon_codex_access_matrix import (
    SCHEMA,ACCESS_TYPES,Gateway,
    create_passage_state,inspect_gate,available_gates,
    take_access_action,replay_access,attempt_unlock,
)


def test_128_original_access_contracts_have_distinct_structural_sources():
    origin=unrank("0")
    first=create_passage_state(origin)
    gates=available_gates(origin,first)
    assert len(gates)==128
    assert len({item.id for item in gates})==128
    assert {item.source_axis for item in gates}==set(AXIS_NAMES)
    assert len({item.route_type for item in gates})==16
    assert all(item.optional_path for item in gates)
    assert all(not item.mandatory_game_ending for item in gates)
    # A fresh world can be blocked by either mastery or a required era.
    # Keep the API's typed reasons rather than flattening distinct gates.
    assert all(item.reason in ("training_required","era_change_required")
               for item in gates)
    assert all(item.next_possible_turn is not None for item in gates)
    assert all(not item.accessible_now for item in gates)


@pytest.mark.parametrize("domain",DOMAINS)
def test_delayed_passages_apply_real_world_skill_and_seasonal_time_constraints(domain):
    start=unrank("0")
    possible=available_gates(start,create_passage_state(start),domain=domain)
    assert len(possible)==8
    for row in possible:
        assert row.source_domain==domain
        assert len(row.required_mastery)==2
        assert all(n>=1 for n in row.required_mastery)
        assert row.period>=2
        assert row.season_window in (0,1,2,3)
        with pytest.raises(ValueError):
            take_access_action(start,create_passage_state(start),row.id)


def test_constructive_original_optional_passage_is_traversed_from_real_progress():
    source=unrank("0")
    gate="access_elevation_tectonics"
    proof=attempt_unlock(source,gate,horizon=96)
    assert proof["schema"]==SCHEMA
    assert proof["found_within_budget"]
    assert proof["actions"][-1]==gate
    journey=replay_access(source,tuple(proof["actions"]))
    assert journey.access_digest==proof["actual_replay_digest"]
    assert gate in journey.traversed
    assert gate in journey.discovered
    assert (journey.world.player.base.x,
            journey.world.player.base.y)==(1,1)
    assert journey.world.player.base.turn==len(proof["actions"])


def test_higher_skill_and_historical_era_can_delay_or_deny_optional_route():
    source=edit("0",{
        "era_length":255,
        "historical_drift":255,
        "future_visibility":255,
    })
    start=create_passage_state(source)
    gate=inspect_gate(source,start,"access_era_length")
    assert gate.required_era==2
    assert not gate.era_earned
    assert not gate.accessible_now
    with pytest.raises(ValueError):
        take_access_action(source,start,gate.id)
    # All three gating dimensions are exposed, not masked by a fake route.
    assert gate.required_mastery[0]>=1
    assert gate.earliest_turn>=3
    assert gate.season_window in range(4)
    result=attempt_unlock(source,gate.id,horizon=96)
    assert result["not_a_global_unwinnability_claim"]
    if result["found_within_budget"]:
        run=replay_access(source,tuple(result["actions"]))
        assert run.world.era>=2
        assert gate.id in run.traversed
    else:
        assert not result["actions"]


def test_normal_world_is_not_falsely_unsolvable_when_optional_path_cannot_open_in_short_window():
    source=edit("0",{
        "elevation_tectonics":255,"plate_migration":255,
    })
    report=attempt_unlock(source,"access_elevation_tectonics",horizon=8)
    assert not report["found_within_budget"]
    assert report["actions"]==[]
    assert report["not_a_global_unwinnability_claim"]
    # This is still a playable world, despite a path not proved in 8 moves.
    state=create_passage_state(source)
    after=take_access_action(source,state,"wait_world")
    assert after.world.player.base.turn==1
    assert after.access_digest!=state.access_digest


def test_optional_secret_world_routes_are_implemented_not_unbounded_labels():
    source=unrank("0")
    gate=inspect_gate(source,create_passage_state(source),
                      "access_skill_gate_depth")
    assert gate.route_type=="secret_passage"
    assert gate.source_domain=="access"
    assert gate.id=="access_skill_gate_depth"
    assert gate.displacement[0]!=0 and gate.displacement[1]!=0
    assert gate.optional_path
    assert not gate.mandatory_game_ending


@pytest.mark.parametrize("bad",[
    "", "access_", "access_missing_route","study_fake_feature",
])
def test_optional_access_api_refuses_unimplemented_route_and_action(bad):
    source=unrank("0")
    start=create_passage_state(source)
    if bad.startswith("access_"):
        with pytest.raises(ValueError):
            inspect_gate(source,start,bad)
    else:
        with pytest.raises(ValueError):
            take_access_action(source,start,bad)


def test_source_access_playback_rejects_more_than_96_actions():
    source=unrank("0")
    with pytest.raises(ValueError):
        replay_access(source,("wait_world",)*97)
    with pytest.raises(ValueError):
        replay_access(source,["wait_world"])


def test_several_different_original_optional_passages_really_change_destinations():
    source=unrank("0")
    ids=(
        "access_elevation_tectonics",
        "access_ocean_depth",
        "access_story_branching",
    )
    real=[]
    for gate in ids:
        outcome=attempt_unlock(source,gate)
        if outcome["found_within_budget"]:
            play=replay_access(source,tuple(outcome["actions"]))
            real.append((
                play.world.player.base.x,
                play.world.player.base.y,
                play.access_digest,
            ))
    assert len(real)>=2
    assert len({x[2] for x in real})==len(real)
    assert len({x[:2] for x in real})>=2
