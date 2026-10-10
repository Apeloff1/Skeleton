"""Real durable authenticated Dragon living world saves and optimistic conflicts."""
from __future__ import annotations
import sqlite3
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route
from skeleton.ai.webcrawler.dragon_living_world_checkpoint import SECRET_SETTING

CONFIG_KEY="original-world-db-hmac-key-safe-tests-2026-10-11-long-enough"


@pytest.fixture(autouse=True)
def configure(monkeypatch,tmp_path):
    monkeypatch.setenv(SECRET_SETTING,CONFIG_KEY)
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH",str(tmp_path/"dragon-worlds.sqlite"))


def person(email="creator@example.invalid",tenant="unique-original-worlds"):
    return route._native_source_editor({
        "email":email,"tenant_id":tenant,"role":"editor",
    })


def world_fields():
    return {
        "world_id":2026,"variation":3,
        "style":"open_world_story","lifecycle":"postgame",
    }


def grant(owner):
    return route.native_living_world_checkpoint_advance(
        route.NativeLivingCheckpointRequest(**world_fields(),moves=[
            "help_settlers","help_settlers","ending_civic_union",
        ]),owner=owner)


def test_real_db_saves_story_endings_then_restores_signed_playable_postgame_world():
    creator=person()
    first=grant(creator)
    stored=route.native_living_world_store(route.NativeLivingStoreRequest(
        **world_fields(),slot=0,token=first["new_checkpoint"],
    ),owner=creator)
    assert stored["ok"]
    assert stored["status"]=="durably_saved_original_game_state"
    assert stored["version"]==1
    listing=route.native_living_world_saves(owner=creator)
    assert len(listing["saves"])==1
    assert listing["saves"][0]["slot"]==0
    restored=route.native_living_world_restore(route.NativeLivingRestoreRequest(
        **world_fields(),slot=0),owner=creator)
    assert restored["ok"]
    assert restored["history_digest"]==first["current_history_digest"]
    assert restored["state"]["endings_seen"]==["civic_union"]
    assert len(restored["new_checkpoint"])>100
    next=route.native_living_world_checkpoint_advance(
        route.NativeLivingCheckpointRequest(
            **world_fields(),token=restored["new_checkpoint"],
            moves=["forage","observe"],
        ),owner=creator)
    assert next["current"]["postgame_active"]
    assert next["current"]["player"]["actions_played"]==5
    assert next["current"]["player"]["era"]==1


def test_durable_endpoint_blocks_stale_overwrite_of_world_narrative_outcome():
    creator=person()
    first=grant(creator)
    stored=route.native_living_world_store(route.NativeLivingStoreRequest(
        **world_fields(),slot=0,token=first["new_checkpoint"],
    ),owner=creator)
    later=route.native_living_world_checkpoint_advance(
        route.NativeLivingCheckpointRequest(
            **world_fields(),token=first["new_checkpoint"],
            moves=["forage"],
        ),owner=creator)
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_store(route.NativeLivingStoreRequest(
            **world_fields(),slot=0,token=later["new_checkpoint"],
        ),owner=creator)
    assert denied.value.status_code==409
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_store(route.NativeLivingStoreRequest(
            **world_fields(),slot=0,token=later["new_checkpoint"],
            replace_existing=True,expected_digest="0"*64,
        ),owner=creator)
    assert denied.value.status_code==409
    accepted=route.native_living_world_store(route.NativeLivingStoreRequest(
        **world_fields(),slot=0,token=later["new_checkpoint"],
        replace_existing=True,
        expected_digest=first["current_history_digest"],
    ),owner=creator)
    assert accepted["version"]==2


def test_durable_save_does_not_leak_across_creators_or_worlds():
    a=person()
    b=person(email="another@example.invalid",tenant="other-original-worlds")
    issued=grant(a)
    route.native_living_world_store(route.NativeLivingStoreRequest(
        **world_fields(),token=issued["new_checkpoint"],
    ),owner=a)
    assert route.native_living_world_saves(owner=b)["saves"]==[]
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_restore(route.NativeLivingRestoreRequest(
            **world_fields()),owner=b)
    assert denied.value.status_code==404
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_restore(route.NativeLivingRestoreRequest(
            world_id=2027,variation=3,style="open_world_story",
            lifecycle="postgame"),owner=a)
    assert denied.value.status_code==403


@pytest.mark.parametrize("endpoint",[
    "/api/dragon-academy/native/production/worlds/store",
    "/api/dragon-academy/native/production/worlds/restore",
    "/api/dragon-academy/native/production/worlds/saves",
])
def test_world_saves_require_editor_or_admin_role(endpoint):
    route_definition=next(x for x in route.router.routes if x.path==endpoint)
    assert any(dep.call is route._native_source_editor
               for dep in route_definition.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.invalid",
            "tenant_id":"original-worlds","role":"viewer",
        })
    assert denied.value.status_code==403


@pytest.mark.parametrize("invalid",[
    {"slot":10},{"slot":-1},{"slot":True},
    {"token":"not-a-real-signature"},{"token":7},
    {"replace_existing":"true"},{"replace_existing":1},
    {"expected_digest":"untrusted"},
])
def test_world_save_request_rejects_coercion_or_invalid_snapshot_parameters(invalid):
    data={**world_fields(),"slot":0,"token":"a"*120,**invalid}
    with pytest.raises(ValidationError):
        route.NativeLivingStoreRequest(**data)


def test_durable_database_is_operator_configured_not_in_memory_by_default(monkeypatch):
    creator=person()
    token=grant(creator)["new_checkpoint"]
    monkeypatch.delenv("SKL_DRAGON_PRACTICE_DB_PATH",raising=False)
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_store(route.NativeLivingStoreRequest(
            **world_fields(),token=token,
        ),owner=creator)
    assert denied.value.status_code==503
