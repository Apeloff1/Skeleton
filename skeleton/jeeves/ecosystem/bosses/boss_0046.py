"""Boss 0046.
"""
from __future__ import annotations

BOSS = "boss_0046"

def phases(optical: float = 0.9) -> list[str]:
    out = ["intro", "mid", "finale"]
    if optical > 0.93:
        out.append("enrage")
    return out

def hp(optical: float = 0.9) -> int:
    return int(200 + 46 * 5 + optical * 50)
