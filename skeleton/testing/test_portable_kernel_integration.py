"""Real binary source-data receipts bridging editor targets and tile converters."""
from dataclasses import replace
from hashlib import sha256

import pytest

from skeleton.ai.game_builder import (
    compile_progressive_port_route, editor_platform_options,
)
from skeleton.ai.game_builder.portable_kernels import (
    encode_gb_2bpp, decode_gb_2bpp, frame_schedule, astar_path,
)
from skeleton.ai.game_builder.portable_kernels.asset_porting import (
    PortableAssetError, PortableTileBundle, compile_original_tile_bundle,
    verify_original_tile_roundtrip, emit_original_tile_source,
)


TILE = tuple(tuple((x + y) % 4 for x in range(8)) for y in range(8))
FULL_TILE = tuple(tuple((x + y*8) % 16 for x in range(8)) for y in range(8))
TARGETS = (
    "nintendo_game_boy", "nintendo_game_boy_color", "nintendo_famicom",
    "nintendo_snes", "sega_master_system", "sega_game_gear", "sega_mega_drive",
)


@pytest.mark.parametrize("target_id", TARGETS)
def test_editor_target_compiles_real_native_bytes_and_proves_roundtrip(target_id):
    catalog = {item["id"]: item for item in editor_platform_options()}
    codec = catalog[target_id]["portable_tile_codec"]
    tile = TILE if codec in ("gb_2bpp", "nes_2bpp") else FULL_TILE
    bundle = compile_original_tile_bundle(
        target_id, (tile, tile), acknowledged_original_source=True,
    )
    assert bundle.tile_count == 2
    assert bundle.tile_codec == codec
    assert len(bundle.native_bytes) == (32 if codec in ("gb_2bpp", "nes_2bpp") else 64)
    assert bundle.native_sha256 == sha256(bundle.native_bytes).hexdigest()
    assert verify_original_tile_roundtrip(bundle, (tile, tile))
    assert bundle.source_originality_acknowledged is True
    assert not bundle.independent_rights_cleared
    assert not bundle.native_binary_verified
    assert not bundle.release_authorized


def test_native_source_declarations_are_toolchain_specific_not_fake_roms():
    gb = compile_original_tile_bundle(
        "nintendo_game_boy", (TILE,), acknowledged_original_source=True,
    )
    nes = compile_original_tile_bundle(
        "nintendo_famicom", (TILE,), acknowledged_original_source=True,
    )
    assert "ORIGINAL_TILES:\n" in emit_original_tile_source(gb,syntax="rgbds")
    assert "db $" in emit_original_tile_source(gb,syntax="rgbds")
    assert ".byte $" in emit_original_tile_source(nes,syntax="ca65")
    c99 = emit_original_tile_source(gb, syntax="c99", symbol="spr_0")
    assert "static const uint8_t spr_0[16]" in c99
    assert "0x" in c99 and c99.endswith("};\n")
    with pytest.raises(PortableAssetError):
        emit_original_tile_source(gb,syntax="ca65")
    with pytest.raises(PortableAssetError):
        emit_original_tile_source(nes,syntax="rgbds")
    with pytest.raises(PortableAssetError):
        emit_original_tile_source(nes,syntax="c99",symbol="evil;injection")


def test_port_bundle_rejects_forged_release_or_unqualified_asset_sources():
    with pytest.raises(PermissionError):
        compile_original_tile_bundle("nintendo_game_boy",(TILE,),
                                     acknowledged_original_source=False)
    with pytest.raises(PortableAssetError):
        compile_original_tile_bundle("commodore_64",(TILE,),
                                     acknowledged_original_source=True)
    gb=compile_original_tile_bundle(
        "nintendo_game_boy",(TILE,),acknowledged_original_source=True,
    )
    for fields in (
        {"native_sha256": "0"*64},
        {"native_bytes": b"wrong"},
        {"release_authorized": True},
        {"native_binary_verified": True},
        {"independent_rights_cleared": True},
    ):
        with pytest.raises(PortableAssetError):
            replace(gb,**fields)


def test_portable_kernels_are_reachable_from_canonical_lazy_game_builder():
    from skeleton.ai import game_builder as api

    assert api.encode_gb_2bpp(TILE) == encode_gb_2bpp(TILE)
    assert api.decode_gb_2bpp(api.encode_gb_2bpp(TILE)) == TILE
    assert sum(api.frame_schedule(50,60,50)) == 60
    assert api.astar_path(("S.G",),(0,0),(2,0)) == ((0,0),(1,0),(2,0))
