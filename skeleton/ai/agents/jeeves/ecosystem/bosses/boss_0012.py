"""Boss 0012.
"""
from __future__ import annotations

BOSS = "boss_0012"

def phases(optical: float = 0.9) -> list[str]:
    out = ["intro", "mid", "finale"]
    if optical > 0.93:
        out.append("enrage")
    return out

def hp(optical: float = 0.9) -> int:
    return int(200 + 12 * 5 + optical * 50)
