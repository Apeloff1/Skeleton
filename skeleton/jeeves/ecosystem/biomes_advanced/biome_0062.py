"""Advanced biome 0062.
"""
from __future__ import annotations

BIOME = "adv_biome_0062"

def climate() -> dict:
    return {"temp": round((62 % 20) / 20, 2), "moisture": round(((62*7) % 20) / 20, 2), "wind": round((62 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 62 % 3 == 0:
        base.append("ore")
    if 62 % 5 == 0:
        base.append("crystal")
    return base
