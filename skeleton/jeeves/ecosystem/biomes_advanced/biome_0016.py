"""Advanced biome 0016.
"""
from __future__ import annotations

BIOME = "adv_biome_0016"

def climate() -> dict:
    return {"temp": round((16 % 20) / 20, 2), "moisture": round(((16*7) % 20) / 20, 2), "wind": round((16 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 16 % 3 == 0:
        base.append("ore")
    if 16 % 5 == 0:
        base.append("crystal")
    return base
