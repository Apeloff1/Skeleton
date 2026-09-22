"""Test-time R schedule — ramp then halt.

1 → 2 → maybe 3. Never a cold jump to 8.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.budgetr import cap
from skeleton.kernel.ops.overthink import should_stop
from skeleton.kernel.ops.loop import block

Row = List[float]


def schedule(*, profile: str = "mobile", hard: bool = False) -> List[int]:
    c = cap(profile)
    steps = [1]
    if c >= 2:
        steps.append(2)
    if hard and c >= 3:
        steps.append(3)
    bump(len(steps))
    return steps


def run(x: Row, *, profile: str = "mobile", hard: bool = False) -> dict:
    h = list(x)
    used = 0
    for r in schedule(profile=profile, hard=hard):
        nxt = block(h)
        used = r
        if r > 1 and should_stop(h, nxt):
            h = nxt
            break
        h = nxt
    bump(len(h))
    return {
        "kind": "r-schedule",
        "used": used,
        "profile": profile,
        "h": h,
        "stored_prose": 0,
    }
