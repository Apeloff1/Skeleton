"""Integer resolution ladder for game art that can move down from a 64k tier.

Upscale stays in ``jeeves_game_upscale`` (nearest and Scale2x, palette
preserving). This module plans and applies integer box downscales. A declared
tier such as 65536 is a label on the ladder. Planning it does not allocate a
65536 by 65536 buffer.

Box averaging can produce channel values that were not in the source block.
That is the downscale contract. It is not neural super-resolution and it does
not qualify native console hardware.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "skeleton.game.scale_ladder.v1"
PROBE_SCHEMA = "skeleton.application.graphic_first_install_probe.v1"

# High 64k tier, then exact halvings down to a chunk-scale edge.
RESOLUTION_LADDER: tuple[int, ...] = (
    65536,
    32768,
    16384,
    8192,
    4096,
    2048,
    1024,
    512,
    256,
    128,
    64,
    32,
    16,
    8,
)

# One bounded pixel pass. Larger drops are a path of these divisors.
SINGLE_PASS_DIVISORS = frozenset({2, 4, 8, 16})
MAX_PIXELS = 1024 * 1024


class ScaleLadderError(ValueError):
    pass


def _tier(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScaleLadderError(f"{name} must be an integer tier")
    if value not in RESOLUTION_LADDER:
        raise ScaleLadderError(f"{name} is not on the resolution ladder")
    return value


def plan_downscale(source_tier: int, target_tier: int) -> dict[str, Any]:
    """Describe an integer-box drop between two ladder tiers.

    ``source_tier`` and ``target_tier`` are edge lengths in pixels. The
    returned divisor is ``source // target``. No pixel buffer is allocated.
    """
    source = _tier(source_tier, "source_tier")
    target = _tier(target_tier, "target_tier")
    if target >= source:
        raise ScaleLadderError("downscale target must be a lower ladder tier")
    if source % target != 0:
        raise ScaleLadderError("target tier must divide the source tier")
    divisor = source // target
    return {
        "schema": SCHEMA,
        "direction": "downscale",
        "technique": "integer-box",
        "source_tier": source,
        "target_tier": target,
        "divisor": divisor,
        "single_pass": divisor in SINGLE_PASS_DIVISORS,
        "allocates_full_tier_buffer": False,
        "model_super_resolution": False,
        "native_hardware_qualified": False,
        "bytes_planned": 0,
    }


def downscale_path(source_tier: int, target_tier: int) -> list[dict[str, Any]]:
    """Walk the ladder by exact halvings from source down to target.

    65536 to 16384 is two steps (32768, then 16384). Each step uses divisor 2.
    The list is a plan. It does not allocate tier-sized images.
    """
    source = _tier(source_tier, "source_tier")
    target = _tier(target_tier, "target_tier")
    plan_downscale(source, target)
    steps: list[dict[str, Any]] = []
    current = source
    while current > target:
        nxt = current // 2
        if nxt not in RESOLUTION_LADDER or nxt < target:
            raise ScaleLadderError("ladder gap: target is not a halving of source")
        steps.append(plan_downscale(current, nxt))
        current = nxt
    if current != target:
        raise ScaleLadderError("halving path did not reach the target tier")
    return steps


def downscale_rgba(pixels: bytes, width: int, height: int, divisor: int) -> bytes:
    """Average each ``divisor`` by ``divisor`` block into one RGBA pixel.

    ``divisor`` is 2, 4, 8, or 16. Width and height must divide evenly.
    The source must already fit in the shared pixel budget (1024 by 1024).
    Channel averages round half up and stay in 0..255.
    """
    if isinstance(divisor, bool) or not isinstance(divisor, int):
        raise ScaleLadderError("divisor must be an integer")
    if divisor not in SINGLE_PASS_DIVISORS:
        raise ScaleLadderError("single-pass divisor must be 2, 4, 8, or 16")
    if isinstance(width, bool) or not isinstance(width, int) or width < divisor:
        raise ScaleLadderError("width must be an integer divisible by the divisor")
    if isinstance(height, bool) or not isinstance(height, int) or height < divisor:
        raise ScaleLadderError("height must be an integer divisible by the divisor")
    if width % divisor != 0 or height % divisor != 0:
        raise ScaleLadderError("width and height must divide evenly by the divisor")
    if width * height > MAX_PIXELS:
        raise ScaleLadderError("source exceeds the bounded pixel budget; plan the tier instead")
    expected = width * height * 4
    if not isinstance(pixels, (bytes, bytearray)) or len(pixels) != expected:
        raise ScaleLadderError("RGBA buffer length must equal width * height * 4")

    out_w = width // divisor
    out_h = height // divisor
    count = divisor * divisor
    bias = count // 2
    src = memoryview(pixels)
    out = bytearray(out_w * out_h * 4)
    row_bytes = width * 4
    for oy in range(out_h):
        y0 = oy * divisor
        for ox in range(out_w):
            x0 = ox * divisor
            totals = [0, 0, 0, 0]
            for dy in range(divisor):
                row = (y0 + dy) * row_bytes + x0 * 4
                for dx in range(divisor):
                    pixel = row + dx * 4
                    totals[0] += src[pixel]
                    totals[1] += src[pixel + 1]
                    totals[2] += src[pixel + 2]
                    totals[3] += src[pixel + 3]
            base = (oy * out_w + ox) * 4
            out[base] = (totals[0] + bias) // count
            out[base + 1] = (totals[1] + bias) // count
            out[base + 2] = (totals[2] + bias) // count
            out[base + 3] = (totals[3] + bias) // count
    return bytes(out)


def first_install_graphic_probe() -> dict[str, Any]:
    """Read-only graphic capability report for a first install.

    Does not train, load weights, write checkpoints, or allocate a 64k buffer.
    """
    from skeleton.ai.game_builder.argon_chunk_field import FACTORS, argon_tier_plan

    example = plan_downscale(32768, 16384)
    if example["divisor"] != 2 or example["target_tier"] != 16384:
        raise ScaleLadderError("32k to 16k probe lost the divisor-2 contract")
    high = argon_tier_plan(65536, chunk_edge=32)
    return {
        "schema": PROBE_SCHEMA,
        "training_authorized": False,
        "promotion": False,
        "weights_loaded": False,
        "resolution_ladder": list(RESOLUTION_LADDER),
        "example_32k_to_16k": example,
        "halving_path_64k_to_16k": downscale_path(65536, 16384),
        "argon_64k_plan": high,
        "argon_factor_count": len(FACTORS),
        "upscale_owner": "skeleton.developer.jeeves_game_upscale",
        "downscale_owner": "skeleton.developer.jeeves_game_scale_ladder",
        "allocates_full_tier_buffer": False,
        "model_super_resolution": False,
        "native_hardware_qualified": False,
    }
