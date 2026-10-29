"""Advanced biome 0003.
"""
from __future__ import annotations

BIOME = "adv_biome_0003"

def climate() -> dict:
    return {"temp": round((3 % 20) / 20, 2), "moisture": round(((3*7) % 20) / 20, 2), "wind": round((3 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 3 % 3 == 0:
        base.append("ore")
    if 3 % 5 == 0:
        base.append("crystal")
    return base
