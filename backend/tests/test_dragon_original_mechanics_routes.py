"""Originals Forge API: actual gameplay differences at multi-quintillion indices."""
from __future__ import annotations
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route
from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
    PROGRAM_COUNT,MECHANIC_IDS,binary_nucleus,program_from_levels,
)


def editor():
    return route._native_source_editor({
        "email":"originals-forge@example.invalid",
        "tenant_id":"world-forge-originals","role":"editor",
    })


def test_catalog_exposes_real_32_mechanics_and_no_fake_18_quintillion_finished_games():
    result=route.native_original_mechanics_catalog(owner=editor())
    assert result["ok"]
    assert result["actual_mechanic_verbs"]==32
    assert result["mechanically_separable_binary_nuclei"]==16_777_216
    assert int(result["exact_original_rule_program_address_count"])==4**32
    assert result["finished_unique_cleared_games"]==0
    assert len(result["mechanics"])==32
    assert len(result["playable_route_intents"])==16
    assert len({x["id"] for x in result["mechanics"]})==32


def test_creator_can_materialize_and_play_a_mechanically_original_world_nucleus():
    chosen=route.native_original_mechanics_nucleus(
        route.NativeOriginalMechanicNucleusRequest(original_nucleus=2**24-1),
        owner=editor(),
    )
    assert chosen["ok"]
    assert chosen["program"]["mechanics_available"]==24
    assert chosen["number_of_finished_games_claimed"]==0
    seed=chosen["program"]["decimal_index"]
    preview=route.native_original_mechanics_preview(
        route.NativeOriginalMechanicRequest(program_index=seed),
        owner=editor(),
    )
    assert preview["ok"] and preview["program"]["decimal_index"]==seed
    assert preview["causal_gameplay_proofs"]["available_original_mechanics"]==24
    assert len(preview["causal_gameplay_proofs"]["mechanic_execution_witnesses"])==32
    assert len([x for x in preview["playable_actions"]
                if x["available"] and x["id"].startswith("practice_")])==24
    played=route.native_original_mechanics_play(
        route.NativeOriginalMechanicPlayRequest(
            program_index=seed,moves=[
                "practice_terraced_trails",
                "practice_river_navigation",
                "join_terraced_trails_river_navigation",
            ],
        ),owner=editor())
    assert played["ok"]
    assert played["current_game_state"]["turn"]==3
    assert played["current_game_state"]["unlocked_joins"]==[
        "join_terraced_trails_river_navigation"]
    assert played["playable_after_endings"]


def test_exact_quintillion_index_materializes_real_original_causal_gameplay():
    top=route.native_original_mechanics_preview(
        route.NativeOriginalMechanicRequest(program_index=str(PROGRAM_COUNT-1)),
        owner=editor(),
    )
    assert top["ok"]
    assert top["program"]["mechanics_available"]==32
    assert top["program"]["decimal_index"]==str(PROGRAM_COUNT-1)
    assert len(top["program"]["source_digest"])==64
    assert all(w["available"] for w in
               top["causal_gameplay_proofs"]["mechanic_execution_witnesses"])
    finished=route.native_original_mechanics_play(
        route.NativeOriginalMechanicPlayRequest(
            program_index=str(PROGRAM_COUNT-1),
            moves=["practice_alternate_conclusions",
                   "practice_postgame_repair",
                   "practice_world_era_cycles"],
        ),owner=editor())
    assert finished["current_game_state"]["era"]>=6
    assert finished["current_game_state"]["endings"]
    assert finished["available_actions"]


def test_two_programs_are_compared_by_actual_resource_actions_and_world_impact():
    first=route.native_original_mechanics_difference(
        route.NativeOriginalMechanicCompareRequest(first="0",second="1"),
        owner=editor(),
    )
    assert first["ok"] and first["distinguishable"]
    assert first["reason"]=="different_action_availability"
    assert first["right"]["available"]
    second=route.native_original_mechanics_difference(
        route.NativeOriginalMechanicCompareRequest(first="1",second="2"),
        owner=editor(),
    )
    assert second["reason"]=="different_executable_cost_rewards_and_world_progress"
    assert second["left"]["world_evolution_after"]!=second["right"]["world_evolution_after"]


def test_game_forger_produces_sixteen_actual_played_story_variants_with_proofs():
    body=route.NativeOriginalCampaignPortfolioRequest(
        program_index=str(PROGRAM_COUNT-1),count=16,
        branch_seed=2026,steps=28,
    )
    result=route.native_original_campaign_portfolio(body,owner=editor())
    assert result["ok"]
    assert result["sampled"]==16
    assert result["distinct_observed_action_sequences"]>=3
    assert result["programs_materialized_as_finished_games"]==0
    assert len(result["experiences"])==16
    single=route.native_original_campaign_playthrough(
        route.NativeOriginalCampaignRequest(
            program_index=str(PROGRAM_COUNT-1),
            branch_seed=2026,route_intent=2,steps=28,
        ),owner=editor())
    assert single["ok"]
    assert single["verification"]["verified"]
    assert single["journey"]["trace_digest"]==result["experiences"][2]["trace_digest"]
    assert single["journey"]["intent"]=="long_impractical_detour"


def test_exact_level_editor_can_construct_solved_semantically_distinct_program():
    levels=[0]*32
    levels[24]=3
    levels[25]=1
    expected=program_from_levels(tuple(levels))
    preview=route.native_original_mechanics_preview(
        route.NativeOriginalMechanicRequest(levels=levels),owner=editor())
    assert preview["program"]["decimal_index"]==expected.decimal_index
    assert preview["program"]["mechanics_available"]==2
    assert preview["causal_gameplay_proofs"]["mechanic_execution_witnesses"][24][
        "level"]==3
    assert preview["causal_gameplay_proofs"]["mechanic_execution_witnesses"][25][
        "level"]==1
    assert not preview["program"]["is_finished_game"]


@pytest.mark.parametrize("endpoint",[
    "/api/dragon-academy/native/production/worlds/originals/preview",
    "/api/dragon-academy/native/production/worlds/originals/play",
    "/api/dragon-academy/native/production/worlds/originals/compare",
    "/api/dragon-academy/native/production/worlds/originals/nucleus",
    "/api/dragon-academy/native/production/worlds/originals/campaign",
    "/api/dragon-academy/native/production/worlds/originals/campaigns",
])
def test_original_game_compiler_and_gameplay_are_editor_only(endpoint):
    entry=next(x for x in route.router.routes if x.path==endpoint)
    assert any(dep.call is route._native_source_editor
               for dep in entry.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.invalid","tenant_id":"world-forge-originals",
            "role":"viewer",
        })
    assert denied.value.status_code==403


@pytest.mark.parametrize("bad",[
    {"program_index":"18446744073709551616"},
    {"program_index":"00001"},{"program_index":"-1"},
    {"program_index":"1e18"},
    {"levels":[0]*31},{"levels":[4]*32},
    {"levels":[True]*32},
    {"levels":[0]*32,"program_index":"1"},
    {"unlicensed_game_rom":"not allowed"},
])
def test_original_world_compiler_rejects_invalid_sources_and_forged_options(bad):
    try:
        body=route.NativeOriginalMechanicRequest(**bad)
    except ValidationError:
        return
    with pytest.raises(HTTPException) as denied:
        route.native_original_mechanics_preview(body,owner=editor())
    assert denied.value.status_code==422


def test_original_game_action_must_exist_in_current_implemented_rule_profile():
    empty=route.NativeOriginalMechanicPlayRequest(
        moves=["practice_terraced_trails"])
    with pytest.raises(HTTPException) as denied:
        route.native_original_mechanics_play(empty,owner=editor())
    assert denied.value.status_code==422
