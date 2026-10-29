"""Advanced biome 0098.
"""
from __future__ import annotations

BIOME = "adv_biome_0098"

def climate() -> dict:
    return {"temp": round((98 % 20) / 20, 2), "moisture": round(((98*7) % 20) / 20, 2), "wind": round((98 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 98 % 3 == 0:
        base.append("ore")
    if 98 % 5 == 0:
        base.append("crystal")
    return base
