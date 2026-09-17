"""Token clock. Tokens do not tick every frame. Warp extracts once."""

from __future__ import annotations

from typing import Any


MAX_FRAMES = 256
TOKEN_PERIOD = 4


class TokenClockError(ValueError):
    """Token clock contract violation."""


def tick(*, frames: int, warps: int = 0) -> dict[str, Any]:
    if isinstance(frames, bool) or not isinstance(frames, int) or frames < 1:
        raise TokenClockError("frames must be a positive integer")
    if frames > MAX_FRAMES:
        raise TokenClockError("too many frames")
    if warps < 0 or warps > frames:
        raise TokenClockError("warp count invalid")
    tokens = frames // TOKEN_PERIOD
    extracts = 1 if warps else 0
    if warps and extracts != 1:
        raise TokenClockError("warp must extract once")
    return {
        "kind": "token_clock",
        "frames": frames,
        "tokens": tokens,
        "period": TOKEN_PERIOD,
        "every_frame": False,
        "extract_count": extracts,
        "warp_count": 1 if warps else 0,
        "stored_prose": 0,
    }
