"""Real GB/NES two-bit plane asset encoding, roundtrip and sprite mapping."""
from hashlib import sha256
import pytest
from skeleton.ai.webcrawler.dragon_retro_assets import (
    BITMAPS,asset_tiles,compile_tile,decode_tile,gb_assembly,
    nes_assembly,enrich_gb_asm,enrich_nes_asm,
)
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic


def test_all_original_bitmaps_are_distinct_and_hardware_bitplane_roundtrip():
    assert len(BITMAPS)>=8
    tiles=asset_tiles()
    assert len(tiles)==len(BITMAPS)
    assert len({t.digest for t in tiles})==len(tiles)
    for tile in tiles:
        assert len(tile.gb)==16 and len(tile.nes)==16
        assert decode_tile(tile.gb,target="gb")==BITMAPS[tile.name]
        assert decode_tile(tile.nes,target="nes")==BITMAPS[tile.name]
    assert tiles[0].gb!=tiles[0].nes


def test_bad_pixel_art_cannot_inject_rom_source():
    with pytest.raises(ValueError):
        compile_tile("name",("00000000",)*7)
    with pytest.raises(ValueError):
        compile_tile("bad\nEVIL",("00000000",)*8)
    with pytest.raises(ValueError):
        compile_tile("art",("1111111X",)*8)
    with pytest.raises(ValueError):
        decode_tile(b"hi",target="gb")
    with pytest.raises(ValueError):
        decode_tile(b"1"*16,target="../../")


def test_real_cartridge_assembly_receives_original_tiles_and_animated_dragon():
    args={"title":"Dragon Game","style":"arcade_score_attack",
          "candidate_id":sha256(b"dragon-assets").hexdigest(),
          "mechanics":(Mechanic.MOVEMENT,Mechanic.EXPLORATION),"authorized":True}
    gb=render_native_project(target_id="game_boy",**args)
    asm=gb.files["src/main.asm"]
    assert "AnimFrame: ds 1" in asm and "    inc [hl]" in asm
    assert asm.count("db $")>=16
    assert "ld [DRAGON_OAM+6], a" in asm
    assert "original dragon_blink" in asm
    assert gb.files["dragon-pixel-art.json"].endswith("\n")
    nes=render_native_project(target_id="nes",**args)
    assert "original dragon_flap" in nes.files["src/main.s"]
    assert ".res $2000-128,0" in nes.files["src/main.s"]
    assert "    sta $0205" in nes.files["src/main.s"]
    assert ".segment \"CHARS\"" in nes.files["src/main.s"]


def test_patchers_fail_closed_on_foreign_rom_templates():
    with pytest.raises(ValueError):
        enrich_gb_asm("anything")
    with pytest.raises(ValueError):
        enrich_nes_asm("anything")
    assert "Tiles:" in gb_assembly()
    assert ".res $2000-" in nes_assembly()
