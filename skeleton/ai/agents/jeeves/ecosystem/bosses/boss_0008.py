"""Boss 0008.
"""
from __future__ import annotations

BOSS = "boss_0008"

def phases(optical: float = 0.9) -> list[str]:
    out = ["intro", "mid", "finale"]
    if optical > 0.93:
        out.append("enrage")
    return out

def hp(optical: float = 0.9) -> int:
    return int(200 + 8 * 5 + optical * 50)
