"""Boss 0047.
"""
from __future__ import annotations

BOSS = "boss_0047"

def phases(optical: float = 0.9) -> list[str]:
    out = ["intro", "mid", "finale"]
    if optical > 0.93:
        out.append("enrage")
    return out

def hp(optical: float = 0.9) -> int:
    return int(200 + 47 * 5 + optical * 50)
