"""Authenticated and bounded original multi-route world APIs."""
from __future__ import annotations
from io import BytesIO
from zipfile import ZipFile
import hashlib,json
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from routes import dragon_academy as route

PATHS=(
    "/api/dragon-academy/native/production/routes/taxonomy",
    "/api/dragon-academy/native/production/routes/preview",
    "/api/dragon-academy/native/production/routes/play",
    "/api/dragon-academy/native/production/routes/source-bundle",
)

def owner():
    return route._principal({
        "email":"maker@example.invalid","tenant_id":"tenant-original",
        "role":"editor",
    })


def test_original_world_capability_api_has_registry_not_fake_game_title_count():
    report=route.native_world_route_taxonomy(owner=owner())
    assert report["ok"]
    assert report["modality_count"]>=190
    assert "air" in report["families"]
    assert "water" in report["families"]
    assert "space" in report["families"]
    assert "fictional" in report["families"]
    assert "sailboat" in report["families"]["water"]
    assert "secret_unlockable" in report["shapes"]


def test_creator_can_play_original_world_step_by_step_and_discover_secret_prerequisites():
    request=route.NativeRoutePlayRequest(seed=1977,weather="clear",hour=8)
    start=route.native_world_route_play(request,owner=owner())
    assert start["ok"]
    assert start["world_position"]=="crossroads"
    assert start["completed"] is False
    assert "map" in start["known_tokens"]
    assert not any(x["edge"]=="secret_from_clue" for x in start["options"])
    first=route.native_world_route_play(route.NativeRoutePlayRequest(
        seed=1977,moves=["walk_to_bazaar"]),owner=owner())
    assert first["world_position"]=="bazaar"
    assert "fare_card" in first["known_tokens"]
    assert "raincoat" in first["known_tokens"]
    game=route.native_world_route_play(route.NativeRoutePlayRequest(
        seed=1977,moves=[
            "walk_to_bazaar","market_to_taxi","taxi_to_goal",
        ]),owner=owner())
    assert game["completed"]
    assert game["world_position"]=="citadel"
    assert game["remaining_cash"]==195
    assert game["elapsed_minutes"]==29
    assert game["options"]==[]


def test_original_world_route_api_does_not_allow_player_to_forge_gate_unlock():
    with pytest.raises(HTTPException) as denied:
        route.native_world_route_play(route.NativeRoutePlayRequest(
            moves=["secret_from_clue"]),owner=owner())
    assert denied.value.status_code==422
    with pytest.raises(HTTPException) as denied:
        route.native_world_route_play(route.NativeRoutePlayRequest(
            moves=["spaceport_access","shuttle_to_orbit","gate_to_goal"]),
            owner=owner())
    assert denied.value.status_code==422


def test_world_route_api_weather_restrictions_require_real_climate():
    path=["walk_to_bazaar","market_to_rain","rain_flood_route"]
    with pytest.raises(HTTPException):
        route.native_world_route_play(route.NativeRoutePlayRequest(
            weather="clear",moves=path),owner=owner())
    wet=route.native_world_route_play(route.NativeRoutePlayRequest(
        weather="rain",moves=path),owner=owner())
    assert wet["completed"]


def test_original_route_preview_shows_executable_alternates_and_true_dead_ends():
    review=route.native_world_route_preview(route.NativeRoutePreviewRequest(
        seed=2026,weather="windy",max_routes=6,
        search_budget=1200,include_long=True,
    ),owner=owner())
    assert review["ok"] and review["source_only"]
    assert len(review["world_digest"])==64
    assert review["world"]["places"]>=30
    assert review["world"]["routes"]>=60
    assert "old_mine" in review["world"]["dead_end_places"]
    assert review["world"]["secret_routes"]>=3
    routes=review["routes"]["routes"]
    assert len(routes)>=2 and len(routes)<=6
    assert len(set(tuple(item["edges"]) for item in routes))==len(routes)
    assert all(item["success"] is True for item in routes)
    assert review["player"]["world_position"]=="crossroads"


def test_native_multimodal_game_zip_requires_original_rights_and_editor_approval():
    with pytest.raises(HTTPException) as denied:
        route.native_world_route_source_bundle(
            route.NativeRouteSourceRequest(seed=37,original_work_attested=True),
            owner=owner(),
        )
    assert denied.value.status_code==403
    source=route.native_world_route_source_bundle(
        route.NativeRouteSourceRequest(seed=1977,weather="rain",
            original_work_attested=True,approved=True),owner=owner(),
    )
    assert source.media_type=="application/zip"
    assert source.headers["cache-control"]=="private, no-store"
    assert source.headers["x-dragon-claim"]=="original-source-only-native-C99-not-compiled"
    assert source.headers["x-content-sha256"]==hashlib.sha256(source.body).hexdigest()
    assert 1000<len(source.body)<=1_500_000
    with ZipFile(BytesIO(source.body)) as file:
        assert set(file.namelist())=={
            "src/main.c","include/dragon_route_world.h",
            "dragon-original-route-proof.json","Makefile","README.md",
        }
        manifest=json.loads(file.read("dragon-original-route-proof.json"))
        assert manifest["schema"]=="skeleton.ai.dragon.original_native_route_game.v1"
        assert manifest["world"]["environment"]==["rain"]
        assert any(p["name"]=="rain" for p in manifest["probes"])
        assert file.read("src/main.c").startswith(b"/* Original world routes")
        assert b"run_probes" in file.read("src/main.c")
        assert b"dragon_connections" in file.read("include/dragon_route_world.h")


@pytest.mark.parametrize("path",PATHS[1:])
def test_multiobjective_route_execution_endpoints_require_editor_permissions(path):
    target=next(x for x in route.router.routes if x.path==path)
    assert any(dep.call is route._native_source_editor
               for dep in target.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.invalid",
            "tenant_id":"tenant-original","role":"viewer",
        })
    assert denied.value.status_code==403


@pytest.mark.parametrize("data",[
    {"seed":-1},{"seed":True},{"seed":2**32},
    {"weather":"magic_no_cost_free_roam"},{"weather":""},
    {"hour":-1},{"hour":24},{"hour":True},
    {"moves":["secret_from_clue"]*81},
    {"moves":123},
    {"unexpected_external_rom":"anything"},
])
def test_world_route_request_rejects_coercions_and_untrusted_raw_inputs(data):
    with pytest.raises(ValidationError):
        route.NativeRoutePlayRequest(**data)


@pytest.mark.parametrize("shape",[
    {"max_routes":25},{"max_routes":True},
    {"search_budget":99999},{"search_budget":50},
    {"include_long":"false"},
])
def test_original_route_preview_limits_solver_budget_and_parallel_output(shape):
    with pytest.raises(ValidationError):
        route.NativeRoutePreviewRequest(**shape)
