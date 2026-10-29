"""Advanced biome 0093.
"""
from __future__ import annotations

BIOME = "adv_biome_0093"

def climate() -> dict:
    return {"temp": round((93 % 20) / 20, 2), "moisture": round(((93*7) % 20) / 20, 2), "wind": round((93 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 93 % 3 == 0:
        base.append("ore")
    if 93 % 5 == 0:
        base.append("crystal")
    return base
