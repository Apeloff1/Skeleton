"""Four-billion exact original game prototype candidates: API gameplay evidence."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from routes import dragon_academy as route


def creator():
    return route._native_source_editor({
        "email":"original-prototype-forger@example.invalid",
        "tenant_id":"new-world-originals","role":"editor",
    })


@pytest.mark.parametrize("nucleus",[
    0,1,42,2026,1_000_000,16_777_215,2**31,2**32-1,
])
def test_original_game_candidate_endpoint_materializes_real_prototype_and_two_replays(nucleus):
    body=route.NativeOriginalPrototypeRequest(
        original_nucleus=nucleus,branch_seed=7,routes=2,steps=12)
    returned=route.native_original_game_prototype(body,owner=creator())
    assert returned["ok"]
    assert returned["verification"]["verified"]
    proposal=returned["original_prototype"]
    assert proposal["original_nucleus"]==nucleus
    assert proposal["available_mechanic_count"]==nucleus.bit_count()
    assert len(proposal["replayed_journeys"])==2
    assert proposal["living_world_actual_route_actions"]
    assert len(proposal["living_world_route_digest"])==64
    assert proposal["ready_for_individual_experiments"]
    assert not proposal["native_binary_built"]
    assert not proposal["independently_published"]
    assert proposal["release_blockers"]
    assert returned["verification"]["independent_publication_approved"] is False


def test_32bit_nucleus_with_endings_and_world_era_realizes_postgame_world():
    nucleus=sum(1<<(31-i) for i in (23,24,25,31))
    result=route.native_original_game_prototype(
        route.NativeOriginalPrototypeRequest(
            original_nucleus=nucleus,routes=2,steps=12),
        owner=creator())
    world=result["original_prototype"]
    assert world["world_style"]=="post_story_wasteland"
    assert world["world_lifecycle"]=="postgame"
    assert world["persistent_after_ending"]
    assert "postgame_repair" in world["active_mechanics"]
    assert "alternate_conclusions" in world["active_mechanics"]
    assert world["gameplay_program_index"]


def test_original_game_corpus_batch_verifies_each_distinct_mechanical_rulebook():
    group=route.native_original_game_prototype_batch(
        route.NativeOriginalPrototypeBatchRequest(
            start=64,count=6,routes=2,steps=12,branch_seed=3),
        owner=creator())
    assert group["ok"]
    assert group["requested_materialized"]==6
    assert group["nuclei_indexed"]==2**32
    assert group["distinct_executable_rulebooks"]==6
    assert group["individually_finished_games"]==0
    assert len(group["prototypes"])==6
    assert len({x["gameplay_program_index"] for x in group["prototypes"]})==6
    assert all(x["living_world_actual_route_actions"] for x in group["prototypes"])


def test_prototype_comparison_executes_differing_gameplay_instead_of_comparing_titles():
    result=route.native_original_game_prototypes_difference(
        route.NativeOriginalPrototypeCompareRequest(first=1,second=2),
        owner=creator())
    assert result["ok"]
    assert result["different_gameplay_rules"]
    assert result["witness"]["distinguishable"]
    assert result["witness"]["reason"]=="different_action_availability"


@pytest.mark.parametrize("path",[
    "/api/dragon-academy/native/production/worlds/originals/prototype",
    "/api/dragon-academy/native/production/worlds/originals/prototypes",
    "/api/dragon-academy/native/production/worlds/originals/prototypes/compare",
])
def test_original_prototypes_and_causal_difference_computation_are_editor_only(path):
    selected=next(endpoint for endpoint in route.router.routes
                  if endpoint.path==path)
    assert any(dep.call is route._native_source_editor
               for dep in selected.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.invalid",
            "tenant_id":"new-world-originals","role":"viewer",
        })
    assert denied.value.status_code==403


@pytest.mark.parametrize("bad",[
    {"original_nucleus":-1},
    {"original_nucleus":2**32},
    {"original_nucleus":True},
    {"branch_seed":-1},{"branch_seed":2**32},
    {"routes":0},{"routes":13},{"steps":3},{"steps":65},
    {"commercial_rom_path":"proprietary"},
])
def test_original_prototype_endpoint_fails_closed_for_unsupported_content_and_bounds(bad):
    with pytest.raises(ValidationError):
        route.NativeOriginalPrototypeRequest(**bad)


def test_original_corpus_batch_rejects_crossing_maximum_32bit_universe():
    with pytest.raises(HTTPException) as denied:
        route.native_original_game_prototype_batch(
            route.NativeOriginalPrototypeBatchRequest(
                start=2**32-1,count=2),
            owner=creator())
    assert denied.value.status_code==422
