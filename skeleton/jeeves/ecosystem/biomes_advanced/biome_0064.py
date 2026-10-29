"""Advanced biome 0064.
"""
from __future__ import annotations

BIOME = "adv_biome_0064"

def climate() -> dict:
    return {"temp": round((64 % 20) / 20, 2), "moisture": round(((64*7) % 20) / 20, 2), "wind": round((64 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 64 % 3 == 0:
        base.append("ore")
    if 64 % 5 == 0:
        base.append("crystal")
    return base
