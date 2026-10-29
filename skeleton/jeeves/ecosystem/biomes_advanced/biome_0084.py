"""Advanced biome 0084.
"""
from __future__ import annotations

BIOME = "adv_biome_0084"

def climate() -> dict:
    return {"temp": round((84 % 20) / 20, 2), "moisture": round(((84*7) % 20) / 20, 2), "wind": round((84 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 84 % 3 == 0:
        base.append("ore")
    if 84 % 5 == 0:
        base.append("crystal")
    return base
