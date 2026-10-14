"""Compositional world-scale API: actual game simulations at indexed addresses."""
from __future__ import annotations
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route
from skeleton.ai.webcrawler.dragon_living_world_lattice import (
    DESIGN_ADDRESS_COUNT,PROFILES,
)


def owner():
    return route._native_source_editor({
        "email":"original-lattice-creator@example.invalid",
        "tenant_id":"original-world-universe",
        "role":"editor",
    })


def test_world_creator_catalog_reports_real_3b_plus_generation_capacity_as_addresses():
    result=route.native_living_world_catalog(owner=owner())
    assert result["ok"]
    lattice=result["compositional_lattice"]
    assert lattice["reversibly_addressable_original_world_configurations"]==(
        DESIGN_ADDRESS_COUNT)
    assert DESIGN_ADDRESS_COUNT>1_800_000_000
    assert lattice["indexed_world_configuration_path_slots"]>18_000_000_000
    assert lattice["number_shipped_and_legally_cleared_in_this_report"]==0
    assert "no global novelty" in lattice["default_claim"]


@pytest.mark.parametrize("index",[
    0,1,1977,1234567,DESIGN_ADDRESS_COUNT-1,
])
def test_original_creator_can_materialize_a_real_choice_route_at_any_large_design_index(index):
    result=route.native_living_world_indexed_design(
        route.NativeIndexedLivingDesignRequest(
            design_index=index,route_slot=3,
        ),owner=owner())
    assert result["ok"]
    assert result["verification"]["verified"]
    assert result["design"]["index"]==index
    assert result["route"]["slot"]==3
    assert result["route"]["actions"]
    assert len(result["route"]["trace_digest"])==64
    assert not result["design"]["reviewed_finished_game"]


def test_even_a_nonwinning_design_index_remains_playable_without_false_final_ending():
    profile=next(i for i,item in enumerate(PROFILES)
                 if item==("creative_sandbox","unending"))
    result=route.native_living_world_indexed_design(
        route.NativeIndexedLivingDesignRequest(
            design_index=profile,route_slot=0,
        ),owner=owner())
    assert result["ok"]
    assert result["design"]["lifecycle"]=="unending"
    assert result["route"]["original_endings"]==[]
    assert not result["route"]["completed_world"]
    assert result["route"]["remains_playable"]


@pytest.mark.parametrize("bad",[
    {"design_index":True},{"design_index":-1},
    {"design_index":5_000_000_000},{"route_slot":10},
    {"route_slot":True},{"route_slot":-1},
    {"unknown_commercial_rom":"forbidden"},
])
def test_indexed_world_address_validation_fails_closed(bad):
    with pytest.raises(ValidationError):
        route.NativeIndexedLivingDesignRequest(**bad)


def test_valid_integer_beyond_lattice_count_is_not_a_fake_producible_world():
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_indexed_design(
            route.NativeIndexedLivingDesignRequest(
                design_index=DESIGN_ADDRESS_COUNT,
            ),owner=owner())
    assert denied.value.status_code==422


def test_large_original_world_variation_and_route_creation_requires_editor():
    path="/api/dragon-academy/native/production/worlds/indexed-design"
    entry=next(x for x in route.router.routes if x.path==path)
    assert any(dep.call is route._native_source_editor
               for dep in entry.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.invalid","role":"viewer",
            "tenant_id":"original-world-universe",
        })
    assert denied.value.status_code==403
