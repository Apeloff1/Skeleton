"""Advanced biome 0038.
"""
from __future__ import annotations

BIOME = "adv_biome_0038"

def climate() -> dict:
    return {"temp": round((38 % 20) / 20, 2), "moisture": round(((38*7) % 20) / 20, 2), "wind": round((38 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 38 % 3 == 0:
        base.append("ore")
    if 38 % 5 == 0:
        base.append("crystal")
    return base
