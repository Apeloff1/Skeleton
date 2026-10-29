"""Advanced biome 0057.
"""
from __future__ import annotations

BIOME = "adv_biome_0057"

def climate() -> dict:
    return {"temp": round((57 % 20) / 20, 2), "moisture": round(((57*7) % 20) / 20, 2), "wind": round((57 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 57 % 3 == 0:
        base.append("ore")
    if 57 % 5 == 0:
        base.append("crystal")
    return base
