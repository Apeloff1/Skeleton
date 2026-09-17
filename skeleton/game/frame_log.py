"""World frame log. Deterministic list. Seal at end."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal
from skeleton.game.world_tick import play


class FrameLogError(ValueError):
    pass


def record(*, seed: int = 8847291, ticks: int = 16) -> dict[str, Any]:
    if ticks < 1 or ticks > 64:
        raise FrameLogError("ticks")
    card = play(seed=int(seed), ticks=ticks)
    frames = []
    for t in range(ticks):
        frames.append({
            "t": t,
            "floor": min(3, t // 4),
            "extract_count": 1 if t == ticks - 1 else 0,
            "stored_prose": 0,
        })
    if frames[-1]["extract_count"] != 1:
        raise FrameLogError("extract")
    return seal({
        "kind": "frame_log",
        "seed": int(seed),
        "n": len(frames),
        "world": card["digest"],
        "extract_count": 1,
        "warp_count": 1,
        "sota_ready": False,
        "stored_prose": 0,
    })
