"""Boss 0077.
"""
from __future__ import annotations

BOSS = "boss_0077"

def phases(optical: float = 0.9) -> list[str]:
    out = ["intro", "mid", "finale"]
    if optical > 0.93:
        out.append("enrage")
    return out

def hp(optical: float = 0.9) -> int:
    return int(200 + 77 * 5 + optical * 50)
