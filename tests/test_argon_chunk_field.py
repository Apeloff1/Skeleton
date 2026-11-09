"""Argon character chunks keep closed factors when the grid is merged or planned at 64k."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.argon_chunk_field import (
    FACTORS,
    ArgonChunkError,
    argon_tier_plan,
    build_argon_field,
    coherence_digest,
    downscale_argon,
    raster_argon,
)
from skeleton.developer.jeeves_game_scale_ladder import (
    downscale_rgba,
    first_install_graphic_probe,
)

SHEET = {
    "skin_tone": "sand",
    "eye_color": "sea",
    "hair_color": "umber",
    "hair_style": "braid",
    "brow": "umber",
    "lips": "rose",
    "clothing_primary": "olive",
    "clothing_secondary": "moss",
    "clothing_trim": "gold",
    "cloth": "linen",
    "leather": "belt",
    "metal": "buckle",
    "wear": "mended",
    "item_kind": "lantern",
    "item_color": "copper",
    "palette_name": "hearth",
    "outline": "ink",
    "pattern": "hem",
    "accessory": "scarf",
    "body_region": "torso",
}


def test_digest_ignores_grid_size():
    fine = build_argon_field(SHEET, chunks_x=8, chunks_y=4)
    coarse = build_argon_field(SHEET, chunks_x=4, chunks_y=4)
    assert len(fine["chunks"]) == 32
    assert len(coarse["chunks"]) == 16
    assert fine["coherence_digest"] == coarse["coherence_digest"]
    assert fine["coherence_digest"] == coherence_digest(fine["variables"])


def test_layout_rows_and_full_factor_copy():
    field = build_argon_field(SHEET, chunks_x=4, chunks_y=4)
    roles = {(chunk["x"], chunk["y"]): chunk["role"] for chunk in field["chunks"]}
    assert roles[(0, 0)] == "hair"
    assert roles[(1, 1)] == "eye"
    assert roles[(0, 2)] == "skin"
    assert roles[(1, 3)] == "item"
    assert roles[(0, 3)] == "item"
    for chunk in field["chunks"]:
        assert set(chunk["variables"]) == set(FACTORS)
        assert chunk["variables"] == field["variables"]
        assert len(chunk["micro"]) == 4
        assert len(chunk["micro"][0]) == 4


def test_downscale_keeps_digest_and_every_factor():
    field = build_argon_field(SHEET, chunks_x=4, chunks_y=4)
    merged = downscale_argon(field)
    assert merged["chunks_x"] == 2
    assert merged["chunks_y"] == 2
    assert merged["coherence_digest"] == field["coherence_digest"]
    assert merged["variables"] == field["variables"]
    assert len(merged["chunks"]) == 4
    for chunk in merged["chunks"]:
        assert chunk["variables"] == SHEET
        for name in FACTORS:
            assert chunk["variables"][name] == SHEET[name]
    # The eye row outranks hair in the top-left 2x2 block.
    top_left = next(chunk for chunk in merged["chunks"] if chunk["x"] == 0 and chunk["y"] == 0)
    assert top_left["role"] == "eye"


def test_unknown_color_and_odd_grid_fail_closed():
    broken = dict(SHEET)
    broken["eye_color"] = "neon"
    with pytest.raises(ArgonChunkError):
        build_argon_field(broken, chunks_x=4, chunks_y=4)
    with pytest.raises(ArgonChunkError):
        build_argon_field(SHEET, chunks_x=3, chunks_y=4)
    with pytest.raises(ArgonChunkError):
        build_argon_field(SHEET, chunks_x=4, chunks_y=3)


def test_64k_plan_does_not_allocate_and_raster_downscales():
    plan = argon_tier_plan(65536, chunk_edge=32)
    assert plan["chunks_along_edge"] == 2048
    assert plan["chunk_count"] == 2048 * 2048
    assert plan["allocates_buffer"] is False
    assert plan["factor_count"] == len(FACTORS)
    field = build_argon_field(SHEET, chunks_x=2, chunks_y=4)
    pixels, width, height = raster_argon(field, chunk_edge=8)
    assert (width, height) == (16, 32)
    assert len(pixels) == width * height * 4
    smaller = downscale_rgba(pixels, width, height, 2)
    assert len(smaller) == 8 * 16 * 4


def test_first_install_graphic_probe_is_read_only():
    report = first_install_graphic_probe()
    assert report["training_authorized"] is False
    assert report["promotion"] is False
    assert report["weights_loaded"] is False
    assert report["example_32k_to_16k"]["divisor"] == 2
    assert report["example_32k_to_16k"]["source_tier"] == 32768
    assert report["example_32k_to_16k"]["target_tier"] == 16384
    assert report["argon_64k_plan"]["chunks_along_edge"] == 2048
    assert report["argon_factor_count"] == 20
    assert report["allocates_full_tier_buffer"] is False
    assert report["resolution_ladder"][0] == 65536
