"""Original functional world visual assets across authentic GB/NES/SNES layouts."""
from __future__ import annotations
from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_world_codex import edit,unrank
from skeleton.ai.webcrawler.dragon_codex_tiles import (
    SCHEMA,TILES,PALETTE_4,PALETTE_16,SUPPORTED_NATIVE_LAYOUTS,
    REFERENCE_FORMAT,encode_tile,decode_tile,tile_pack,verify_tile_pack,
)


@pytest.mark.parametrize("target,format,bytes_per_tile",[
    ("game_boy","gb_interleaved_2bpp",16),
    ("game_boy_color","gb_interleaved_2bpp",16),
    ("nes","nes_planar_2bpp",16),
    ("snes","snes_planar_4bpp",32),
    ("pc_linux","unverified_indexed_tile_reference",64),
    ("pc_windows","unverified_indexed_tile_reference",64),
])
def test_world_genome_emits_actual_original_target_tile_bytes(target,format,bytes_per_tile):
    source=edit("0",{
        "flora_succession":255,"ocean_depth":193,
        "secret_density":122,"portal_alignment":208,
        "story_branching":143,
    })
    pack=tile_pack(source,target)
    assert pack.schema==SCHEMA
    assert pack.target_id==target
    assert pack.native_layout==format
    assert len(pack.named_tiles)==len(TILES)==12
    assert all(len(bytes.fromhex(tile))==bytes_per_tile
               for tile in pack.tile_hex)
    assert all(decode_tile(bytes.fromhex(raw),format)==pixel
               for raw,pixel in zip(pack.tile_hex,pack.tile_pixels))
    assert len(set(pack.artwork_hashes))>=10
    assert not pack.emitted_into_final_rom
    assert not pack.hardware_verified
    assert verify_tile_pack(source,pack)["verified"]
    assert tile_pack(source,target)==pack


def test_game_boy_interleaved_bitplanes_differ_from_nes_planar_byte_layout():
    source=unrank("0")
    gb=tile_pack(source,"game_boy")
    nes=tile_pack(source,"nes")
    assert gb.tile_pixels==nes.tile_pixels
    assert gb.tile_hex!=nes.tile_hex
    assert gb.native_layout!=nes.native_layout
    assert gb.compatible_format_encoder
    assert nes.compatible_format_encoder
    assert gb.indexed_colors==nes.indexed_colors==4


def test_snes_original_world_tiles_have_real_4bpp_planar_layers():
    source=edit("0",{
        "storm_fronts":255,"portal_alignment":190,
        "settlement_decay":255,
    })
    art=tile_pack(source,"snes")
    assert art.indexed_colors==16
    assert art.palette==PALETTE_16
    assert any(pixel>3 for tile in art.tile_pixels
               for row in tile for pixel in row)
    assert all(len(bytes.fromhex(raw))==32 for raw in art.tile_hex)
    assert verify_tile_pack(source,art)["tiles"]==12


def test_unsupported_native_encoding_is_explicit_reference_not_imaginary_rom_ready():
    for target in ("ps1","xbox_original","pc_linux"):
        art=tile_pack(unrank("0"),target)
        assert art.native_layout==REFERENCE_FORMAT
        assert not art.compatible_format_encoder
        assert not art.emitted_into_final_rom
        assert not art.hardware_verified
        assert all(len(bytes.fromhex(raw))==64 for raw in art.tile_hex)


def test_actual_world_genes_change_source_controlled_game_visuals():
    base=tile_pack(unrank("0"),"game_boy")
    changed=tile_pack(edit("0",{
        "flora_succession":255,"portal_alignment":100,
    }),"game_boy")
    assert base.tile_hex!=changed.tile_hex
    assert base.digest!=changed.digest
    assert base.original_world_digest!=changed.original_world_digest
    assert changed==tile_pack(edit("0",{
        "flora_succession":255,"portal_alignment":100,
    }),"game_boy")


def test_native_gb_nes_snes_tile_decoders_refuse_invalid_bitplanes():
    bitmap=tuple(tuple((x+y)%4 for x in range(8)) for y in range(8))
    for layout in ("gb_interleaved_2bpp","nes_planar_2bpp"):
        encoded=encode_tile(bitmap,layout)
        assert len(encoded)==16
        assert decode_tile(encoded,layout)==bitmap
    for layout in ("gb_interleaved_2bpp","nes_planar_2bpp",
                   "snes_planar_4bpp"):
        with pytest.raises(ValueError):
            decode_tile(b"undersized",layout)
    with pytest.raises(ValueError):
        encode_tile(bitmap,"unlicensed_custom_console_rom")


def test_tampered_original_art_pixels_or_target_format_are_rejected():
    source=unrank("0")
    art=tile_pack(source,"nes")
    forged=replace(art,tile_hex=("00"*16,)+art.tile_hex[1:])
    with pytest.raises(ValueError):
        verify_tile_pack(source,forged)
    forged=replace(art,hardware_verified=True)
    with pytest.raises(ValueError):
        verify_tile_pack(source,forged)
