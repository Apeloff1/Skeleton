"""Integer downscale ladder: plan 64k without allocating it, box-filter small buffers."""
from __future__ import annotations

import pytest

from skeleton.developer.jeeves_game_scale_ladder import (
    MAX_PIXELS,
    RESOLUTION_LADDER,
    ScaleLadderError,
    downscale_path,
    downscale_rgba,
    first_install_graphic_probe,
    plan_downscale,
)
from skeleton.developer.jeeves_game_upscale import _expand


def _solid(width: int, height: int, rgba: bytes) -> bytes:
    assert len(rgba) == 4
    return rgba * (width * height)


def test_ladder_starts_at_64k_and_halves():
    assert RESOLUTION_LADDER[0] == 65536
    assert RESOLUTION_LADDER[1] == 32768
    assert RESOLUTION_LADDER[2] == 16384
    for higher, lower in zip(RESOLUTION_LADDER, RESOLUTION_LADDER[1:]):
        assert higher == lower * 2


def test_plan_32k_downscales_to_16k_with_divisor_2():
    plan = plan_downscale(32768, 16384)
    assert plan["divisor"] == 2
    assert plan["technique"] == "integer-box"
    assert plan["source_tier"] == 32768
    assert plan["target_tier"] == 16384
    assert plan["single_pass"] is True
    assert plan["allocates_full_tier_buffer"] is False
    assert plan["model_super_resolution"] is False
    assert plan["native_hardware_qualified"] is False
    assert plan["bytes_planned"] == 0


def test_64k_to_16k_is_two_halving_steps():
    steps = downscale_path(65536, 16384)
    assert [step["target_tier"] for step in steps] == [32768, 16384]
    assert [step["divisor"] for step in steps] == [2, 2]
    assert all(step["bytes_planned"] == 0 for step in steps)


def test_plan_rejects_upscale_and_unknown_tiers():
    with pytest.raises(ScaleLadderError):
        plan_downscale(16384, 32768)
    with pytest.raises(ScaleLadderError):
        plan_downscale(32768, 32768)
    with pytest.raises(ScaleLadderError):
        plan_downscale(100, 50)
    with pytest.raises(ScaleLadderError):
        plan_downscale(True, 8)  # type: ignore[arg-type]


def test_box_downscale_32_to_16_averages_blocks():
    width = height = 32
    pixels = bytearray(_solid(width, height, b"\x00\x00\x00\xff"))
    # One 2x2 block at the origin mixes two colors evenly.
    for y in range(2):
        for x in range(2):
            base = (y * width + x) * 4
            if (x + y) % 2 == 0:
                pixels[base:base + 4] = b"\x00\x00\x00\xff"
            else:
                pixels[base:base + 4] = b"\x0a\x14\x1e\xff"
    out = downscale_rgba(bytes(pixels), width, height, 2)
    assert len(out) == 16 * 16 * 4
    assert out[0:4] == bytes((5, 10, 15, 255))
    assert out[4:8] == b"\x00\x00\x00\xff"


def test_nearest_upscale_then_box_downscale_is_identity():
    width = height = 8
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            pixels.extend((x * 20, y * 20, 40, 255))
    raw = bytes(pixels)
    up = _expand(raw, width, height, 2, "nearest")
    down = downscale_rgba(up, width * 2, height * 2, 2)
    assert down == raw


def test_scale2x_then_box_downscale_can_mix_colors():
    raw = b"\x00\x00\x00\xff" + b"\xff\x00\x00\xff" + b"\xff\x00\x00\xff" + b"\x00\x00\x00\xff"
    up = _expand(raw, 2, 2, 2, "scale2x")
    down = downscale_rgba(up, 4, 4, 2)
    assert down != raw


def test_downscale_rejects_bad_divisor_shape_and_unbounded_claim():
    raw = _solid(8, 8, b"\x01\x02\x03\xff")
    with pytest.raises(ScaleLadderError):
        downscale_rgba(raw, 8, 8, 3)
    with pytest.raises(ScaleLadderError):
        downscale_rgba(raw, 8, 7, 2)
    with pytest.raises(ScaleLadderError):
        downscale_rgba(b"", 2048, 1024, 2)
    assert 2048 * 1024 > MAX_PIXELS
