"""Advanced biome 0073.
"""
from __future__ import annotations

BIOME = "adv_biome_0073"

def climate() -> dict:
    return {"temp": round((73 % 20) / 20, 2), "moisture": round(((73*7) % 20) / 20, 2), "wind": round((73 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 73 % 3 == 0:
        base.append("ore")
    if 73 % 5 == 0:
        base.append("crystal")
    return base
