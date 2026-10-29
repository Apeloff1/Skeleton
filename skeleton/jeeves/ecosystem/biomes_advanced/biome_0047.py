"""Advanced biome 0047.
"""
from __future__ import annotations

BIOME = "adv_biome_0047"

def climate() -> dict:
    return {"temp": round((47 % 20) / 20, 2), "moisture": round(((47*7) % 20) / 20, 2), "wind": round((47 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 47 % 3 == 0:
        base.append("ore")
    if 47 % 5 == 0:
        base.append("crystal")
    return base
