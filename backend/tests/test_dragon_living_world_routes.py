"""Authenticated app-facing living worlds: no victory requirement and real endings."""
from __future__ import annotations
import json
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route
from skeleton.ai.webcrawler.dragon_living_world import (
    create_world,replay,catalog,WORLD_ADDRESS_COUNT,
)


def owner():
    return route._native_source_editor({
        "email":"maker@example.invalid","tenant_id":"original-game-worlds",
        "role":"editor",
    })


def test_world_catalog_describes_playable_genres_and_virtual_address_not_shipped_games():
    report=route.native_living_world_catalog(owner=owner())
    assert report["ok"]
    assert report["world_style_count"]>=32
    assert report["addressable_world_ids"]==1_600_000
    assert report["addressable_world_variant_slots"]==16_000_000
    assert "mutable_labyrinth" in report["styles"]
    assert report["styles"]["creative_sandbox"]["default_lifecycle"]=="unending"
    assert report["styles"]["open_world_story"]["default_lifecycle"]=="postgame"
    assert "not 16m finished" in report["claims"]


def test_non_winnable_sandbox_preview_is_still_playable_with_real_resources_and_actions():
    body=route.NativeLivingWorldRequest(
        world_id=1977,variation=4,style="creative_sandbox",
        lifecycle="unending",
    )
    displayed=route.native_living_world_preview(body,owner=owner())
    assert displayed["ok"]
    assert displayed["player"]["playable"]
    assert not displayed["player"]["fixed_winning_condition_exists"]
    assert not displayed["player"]["has_completed_ending"]
    assert len(displayed["tiles"])==25
    assert displayed["world"]["world_id"]==1977
    assert displayed["world"]["variant"]==4
    assert len(displayed["world"]["world_fingerprint"])==64
    assert not any(x["name"].startswith("ending_")
                   for x in displayed["player"]["options"])
    session=route.native_living_world_play(
        route.NativeLivingPlayRequest(
            world_id=1977,variation=4,style="creative_sandbox",
            lifecycle="unending",
            moves=["observe","forage","build","rest"],
        ),
        owner=owner(),
    )
    assert session["ok"]
    assert session["current"]["playable"]
    assert not session["current"]["has_completed_ending"]
    assert session["current"]["player"]["shelter"]==1
    assert "settlement_built" in session["current"]["player"]["world_changes"]
    assert len(session["surroundings"])==25


def test_narrative_world_ending_does_not_force_player_out_of_exploration():
    history=["help_settlers","help_settlers","ending_civic_union","forage"]
    body=route.NativeLivingPlayRequest(
        world_id=123,style="open_world_story",
        lifecycle="postgame",moves=history,
    )
    state=route.native_living_world_play(body,owner=owner())
    assert state["current"]["postgame_active"]
    assert state["current"]["playable"]
    assert state["current"]["player"]["era"]==1
    assert state["current"]["player"]["endings_seen"]==["civic_union"]
    assert "era_civic_union" in state["current"]["player"]["world_changes"]
    assert state["current"]["player"]["turn"]==4
    assert any(x["name"]=="forage" for x in state["current"]["options"])


def test_native_original_changing_maze_server_recomputes_real_wall_choices():
    body=route.NativeLivingWorldRequest(
        world_id=1977,variation=3,style="mutable_labyrinth",lifecycle="unending",
    )
    initial=route.native_living_world_preview(body,owner=owner())
    north=next(x for x in initial["player"]["options"] if x["name"]=="north")
    assert north["available"]
    played=route.native_living_world_play(route.NativeLivingPlayRequest(
        world_id=1977,variation=3,style="mutable_labyrinth",lifecycle="unending",
        moves=["north","wait"],
    ),owner=owner())
    assert played["current"]["player"]["y"]==-1
    assert played["current"]["environment"]["maze_phase"]==2
    assert played["current"]["playable"]


def test_native_original_multiple_realm_world_requires_discovery_before_portal():
    base={"world_id":97,"variation":2,
          "style":"multiple_world_platform","lifecycle":"optional_endings"}
    opening=route.native_living_world_preview(route.NativeLivingWorldRequest(
        **base),owner=owner())
    assert opening["world"]["realms"]>=3
    assert all(not option["available"]
               for option in opening["player"]["options"]
               if option["name"].startswith("portal_"))
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_play(route.NativeLivingPlayRequest(
            **base,moves=["portal_1"]),owner=owner())
    assert denied.value.status_code==422
    travelled=route.native_living_world_play(route.NativeLivingPlayRequest(
        **base,moves=["observe","portal_1","portal_0"]),
        owner=owner())
    assert travelled["current"]["player"]["realm"]==0
    assert travelled["current"]["player"]["chapter"]>=3


def test_alternative_paths_exposed_as_replay_verified_original_game_histories():
    body=route.NativeLivingWorldRequest(
        world_id=11,variation=3,style="branching_campaign",
        lifecycle="multiple_endings",
    )
    offerings=route.native_living_world_alternatives(body,owner=owner())
    assert offerings["ok"]
    assert offerings["sampled"]==10
    assert offerings["distinct_replayed_action_sequences"]>=6
    assert len(offerings["samples"])==10
    civic=offerings["samples"][7]
    assert "civic_union" in civic["original_endings"]
    single=route.native_living_world_route(route.NativeLivingRouteRequest(
        world_id=11,variation=3,style="branching_campaign",
        lifecycle="multiple_endings",slot=7),owner=owner())
    assert single["ok"]
    assert single["verification"]["verified"]
    assert single["route"]["trace_digest"]==civic["trace_digest"]
    assert single["route"]["world_fingerprint"]==offerings["world_fingerprint"]


def test_journal_replays_authored_living_world_source_instead_of_minting_fake_ending():
    base={"world_id":51,"variation":1,"style":"open_world_story"}
    history=["help_settlers","help_settlers","ending_civic_union","observe"]
    original=route.native_living_world_journal(route.NativeLivingJournalRequest(
        **base,moves=history),owner=owner())
    assert original["ok"]
    assert original["replay_verified"]
    assert len(original["steps"])==4
    assert original["steps"][2]["endings_seen"]==["civic_union"]
    correct=original["final"]["player"]["history_digest"]
    again=route.native_living_world_journal(route.NativeLivingJournalRequest(
        **base,moves=history,expected_final_digest=correct),owner=owner())
    assert again["final"]["player"]["history_digest"]==correct
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_journal(route.NativeLivingJournalRequest(
            **base,moves=history,expected_final_digest="0"*64),
            owner=owner())
    assert denied.value.status_code==422


@pytest.mark.parametrize("endpoint",[
    "/api/dragon-academy/native/production/worlds/preview",
    "/api/dragon-academy/native/production/worlds/play",
    "/api/dragon-academy/native/production/worlds/alternatives",
    "/api/dragon-academy/native/production/worlds/route",
    "/api/dragon-academy/native/production/worlds/journal",
])
def test_live_world_creation_and_expensive_route_work_requires_editor_permissions(endpoint):
    selected=next(x for x in route.router.routes if x.path==endpoint)
    assert any(x.call is route._native_source_editor
               for x in selected.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.invalid","tenant_id":"original-game-worlds",
            "role":"viewer",
        })
    assert denied.value.status_code==403


@pytest.mark.parametrize("invalid",[
    {"world_id":True},{"world_id":-1},{"world_id":WORLD_ADDRESS_COUNT},
    {"variation":True},{"variation":10},{"variation":-1},
    {"style":"Nintendo™"},{"style":"copyrighted title"},
    {"lifecycle":"illegal expression"},{"unexpected_rom_upload":"fake"},
])
def test_living_world_input_prevalidation_rejects_injected_metadata_or_fake_addresses(invalid):
    with pytest.raises(ValidationError):
        route.NativeLivingWorldRequest(**invalid)


@pytest.mark.parametrize("bad",[
    {"moves":["north"]*193},
    {"moves":"move east"},
    {"moves":["arbitrary code"]},
    {"moves":[123]},
])
def test_living_world_action_history_must_be_bounded_and_typed(bad):
    if bad["moves"]==["arbitrary code"]:
        validated=route.NativeLivingPlayRequest(**bad)
        with pytest.raises(HTTPException):
            route.native_living_world_play(validated,owner=owner())
    else:
        with pytest.raises(ValidationError):
            route.NativeLivingPlayRequest(**bad)
