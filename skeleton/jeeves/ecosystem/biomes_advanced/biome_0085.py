"""Advanced biome 0085.
"""
from __future__ import annotations

BIOME = "adv_biome_0085"

def climate() -> dict:
    return {"temp": round((85 % 20) / 20, 2), "moisture": round(((85*7) % 20) / 20, 2), "wind": round((85 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 85 % 3 == 0:
        base.append("ore")
    if 85 % 5 == 0:
        base.append("crystal")
    return base
