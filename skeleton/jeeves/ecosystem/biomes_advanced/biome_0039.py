"""Advanced biome 0039.
"""
from __future__ import annotations

BIOME = "adv_biome_0039"

def climate() -> dict:
    return {"temp": round((39 % 20) / 20, 2), "moisture": round(((39*7) % 20) / 20, 2), "wind": round((39 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 39 % 3 == 0:
        base.append("ore")
    if 39 % 5 == 0:
        base.append("crystal")
    return base
