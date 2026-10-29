"""Advanced biome 0044.
"""
from __future__ import annotations

BIOME = "adv_biome_0044"

def climate() -> dict:
    return {"temp": round((44 % 20) / 20, 2), "moisture": round(((44*7) % 20) / 20, 2), "wind": round((44 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 44 % 3 == 0:
        base.append("ore")
    if 44 % 5 == 0:
        base.append("crystal")
    return base
