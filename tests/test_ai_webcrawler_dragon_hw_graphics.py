"""Native 4bpp hardware encoding, cartridge budgets and working GBA art output."""
from __future__ import annotations
from hashlib import sha256
import json
import pytest
from skeleton.ai.webcrawler.dragon_hw_graphics import (
    LAYOUTS,encode_tile,decode_tile,encode_assets,atlas_data,atlas_header,source_manifest,
)
from skeleton.ai.webcrawler.dragon_hardware_budget import (
    LIMITS,budget_for,analyze_project_budget,
)
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic


ALL=(
    "game_boy","game_boy_color","nes","master_system","game_gear",
    "snes","genesis","game_boy_advance","commodore_64","dos_vga",
    "ps1","xbox_original","pc_linux","pc_windows","pc_macos","steam_deck",
)

@pytest.mark.parametrize("layout",LAYOUTS)
def test_genuine_hardware_4bit_planes_and_roundtrip(layout):
    pixels=(
        "01234567","89abcdef","00112233","44556677",
        "8899aabb","ccddeeff","12345678","fedcba98",
    )
    native=encode_tile(pixels,layout)
    assert len(native)==32
    assert decode_tile(native,layout)==pixels
    assert atlas_data(layout)
    header=atlas_header(layout)
    assert "#define DRAGON_TILE_COUNT 8" in header
    assert "dragon_native_tiles[" in header
    assert source_manifest(layout)["atlas_sha256"]==sha256(atlas_data(layout)).hexdigest()

def test_four_targets_differ_in_memory_layout():
    pixels=("01234567",)*8
    outputs=[encode_tile(pixels,k) for k in LAYOUTS]
    assert len(set(outputs))==4
    assert all(len(out)==32 for out in outputs)


@pytest.mark.parametrize("layout",LAYOUTS)
def test_invalid_asset_layout_rejected(layout):
    with pytest.raises(ValueError):
        encode_tile(("F"*8,)*7,layout)
    with pytest.raises(ValueError):
        encode_tile(("GGGGGGGG",)*8,layout)
    with pytest.raises(ValueError):
        decode_tile(b"invalid",layout)
    with pytest.raises(ValueError):
        encode_assets(layout,extras={"../evil":("0"*8,)*8})
    with pytest.raises(ValueError):
        encode_assets(layout,extras={("extra"+str(i)):("0"*8,)*8 for i in range(64)})
    with pytest.raises(ValueError):
        atlas_header(layout,name="}; system('malware')")


@pytest.mark.parametrize("target",ALL)
def test_hardware_budget_documented_even_for_source_only_targets(target):
    b=budget_for(target)
    assert b.max_source_bundle_bytes>=120000
    assert b.graphics_ram_bytes>0
    assert b.nominal_rom_bank_bytes>0
    assert b.max_sprite_tiles>0
    assert b.confidence=="conservative_source_estimate_only"


@pytest.mark.parametrize("target,expected",[
    ("snes","snes_planar4"),
    ("genesis","genesis_nibbles"),
    ("game_boy_advance","gba_nibbles"),
    ("master_system","sega_vdp_planar4"),
    ("game_gear","sega_vdp_planar4"),
])
def test_era_specific_packed_hardware_art_in_native_zip(target,expected):
    p=render_native_project(title="Dragon Original Pixel Art",
        target_id=target,style="arcade_score_attack",
        candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True)
    artwork=json.loads(p.files["dragon-hardware-art.json"])
    assert artwork["layout"]==expected
    assert artwork["tile_bytes"]==32
    assert artwork["tile_count"]>=8
    budget=json.loads(p.files["dragon-hardware-budget.json"])
    assert budget["target"]==target
    assert budget["status"]=="source_budget_checked_only"
    assert budget["declared_asset_bytes"]==32*artwork["tile_count"]
    assert budget["sprite_asset_ratio"]<1.0
    if target=="game_boy_advance":
        code=p.files["src/main.c"]
        assert '#include "dragon_original_tiles.h"' in code
        assert "static void draw_dragon(int x,int y)" in code
        assert "dragon_native_tiles[yy*4+xx/2]" in code
        assert "draw_dragon(x,y)" in code
        assert "-Iinclude" in p.files["Makefile"]


def test_hardware_source_auditor_refuses_wrong_layout_and_overlimit():
    legit=source_manifest("snes_planar4")
    with pytest.raises(ValueError,match="does not match"):
        analyze_project_budget("game_boy_advance",{
            "src/main.c":"int main(void){}",
            "dragon-hardware-art.json":json.dumps(legit),
        })
    forged=dict(source_manifest("gba_nibbles"))
    forged["tile_count"]=99999
    with pytest.raises(ValueError):
        analyze_project_budget("game_boy_advance",{
            "src/main.c":"int main(void){}",
            "dragon-hardware-art.json":json.dumps(forged),
        })
    with pytest.raises(ValueError):
        analyze_project_budget("snes",{"src/main.c":"a"*121000})
    with pytest.raises(ValueError):
        budget_for("xbox_series")
