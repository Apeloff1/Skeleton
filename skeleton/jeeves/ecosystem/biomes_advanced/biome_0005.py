"""Advanced biome 0005.
"""
from __future__ import annotations

BIOME = "adv_biome_0005"

def climate() -> dict:
    return {"temp": round((5 % 20) / 20, 2), "moisture": round(((5*7) % 20) / 20, 2), "wind": round((5 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 5 % 3 == 0:
        base.append("ore")
    if 5 % 5 == 0:
        base.append("crystal")
    return base
