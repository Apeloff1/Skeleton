"""Advanced biome 0097.
"""
from __future__ import annotations

BIOME = "adv_biome_0097"

def climate() -> dict:
    return {"temp": round((97 % 20) / 20, 2), "moisture": round(((97*7) % 20) / 20, 2), "wind": round((97 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 97 % 3 == 0:
        base.append("ore")
    if 97 % 5 == 0:
        base.append("crystal")
    return base
