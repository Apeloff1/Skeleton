"""Boss 0083.
"""
from __future__ import annotations

BOSS = "boss_0083"

def phases(optical: float = 0.9) -> list[str]:
    out = ["intro", "mid", "finale"]
    if optical > 0.93:
        out.append("enrage")
    return out

def hp(optical: float = 0.9) -> int:
    return int(200 + 83 * 5 + optical * 50)
