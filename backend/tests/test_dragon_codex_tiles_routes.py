"""Game-world artwork service: native bitplanes not invented ROM binaries."""
from __future__ import annotations
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route


def editor():
    return route._native_source_editor({
        "email":"codex-artist@example.test",
        "role":"editor","tenant_id":"original-hardware-game-art",
    })


@pytest.mark.parametrize("target,layout,size",[
    ("game_boy","gb_interleaved_2bpp",32),
    ("game_boy_color","gb_interleaved_2bpp",32),
    ("nes","nes_planar_2bpp",32),
    ("snes","snes_planar_4bpp",64),
    ("pc_windows","unverified_indexed_tile_reference",128),
])
def test_real_console_specific_world_art_is_encoded_and_independently_verified(target,layout,size):
    result=route.native_world_codex_tiles(
        route.NativeCodexTileRequest(index="0",target=target),
        owner=editor())
    assert result["ok"]
    assert result["source"]["native_layout"]==layout
    assert result["independent_format_verification"]["verified"]
    assert result["independent_format_verification"]["tiles"]==12
    assert result["source"]["target_id"]==target
    assert len(result["source"]["tile_hex"][0])==size
    assert len(result["source"]["tile_pixels"])==12
    assert not result["source"]["emitted_into_final_rom"]
    assert not result["source"]["hardware_verified"]
    assert "not a compiled ROM" in result["visual_claim"]


def test_game_world_graphic_styles_react_to_original_128_parameter_changes():
    root=route.native_world_codex_tiles(
        route.NativeCodexTileRequest(index="0",target="nes"),
        owner=editor())
    modified=route.native_world_codex_edit(
        route.NativeCodexWorldEditRequest(index="0",changes={
            "flora_succession":255,"sky_islands":188,
        }),owner=editor())["new_decimal_index"]
    after=route.native_world_codex_tiles(
        route.NativeCodexTileRequest(index=modified,target="nes"),
        owner=editor())
    assert after["source"]["tile_hex"]!=root["source"]["tile_hex"]
    assert after["source"]["digest"]!=root["source"]["digest"]


def test_sky_island_design_generates_real_extra_native_tile_bitplanes():
    from skeleton.ai.webcrawler.dragon_world_codex import edit,validate
    from skeleton.ai.webcrawler.dragon_codex_tiles import tile_pack,verify_tile_pack
    expanded=edit("0",{
        "sky_islands":220,
        "cloud_oceans":180,
        "skybridge_density":160,
        "floating_settlements":110,
        "thermal_updrafts":96,
        "wind_shear":75,
    })
    _,controls=validate(expanded)
    assert controls.level("sky_islands")==220
    assert expanded.decimal_index!="0"
    assert len(expanded.extension_values)==64
    for target,fmt in (("nes","nes_planar_2bpp"),("snes","snes_planar_4bpp")):
        pack=tile_pack(expanded,target)
        assert len(pack.named_tiles)==16
        assert {"sky_island","cloud_sea","sky_port","aerial_bridge"}.issubset(
            pack.named_tiles)
        assert pack.native_layout==fmt
        assert pack.all_tile_roundtrips_verified
        assert verify_tile_pack(expanded,pack)["verified"]
        assert not pack.emitted_into_final_rom
        assert not pack.hardware_verified


def test_world_tile_API_requires_authenticated_editor_role():
    path="/api/dragon-academy/native/production/worlds/codex/tiles"
    record=next(x for x in route.router.routes if x.path==path)
    assert any(dep.call is route._native_source_editor
               for dep in record.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.invalid",
            "role":"viewer","tenant_id":"original-hardware-game-art",
        })
    assert denied.value.status_code==403


def test_unknown_console_is_not_advertised_as_hardware_encoded_original_art():
    with pytest.raises(HTTPException) as denied:
        route.native_world_codex_tiles(
            route.NativeCodexTileRequest(index="0",target="custom_rom_clone"),
            owner=editor())
    assert denied.value.status_code==422


@pytest.mark.parametrize("payload",[
    {"index":123},{"index":"00"},{"target":"unlicensed/bios"},
    {"target":True},{"unused_asset_dump":"not_allowed"},
])
def test_world_tile_service_refuses_untrusted_asset_material(payload):
    with pytest.raises(ValidationError):
        route.NativeCodexTileRequest(**payload)
