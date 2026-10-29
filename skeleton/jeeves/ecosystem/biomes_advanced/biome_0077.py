"""Advanced biome 0077.
"""
from __future__ import annotations

BIOME = "adv_biome_0077"

def climate() -> dict:
    return {"temp": round((77 % 20) / 20, 2), "moisture": round(((77*7) % 20) / 20, 2), "wind": round((77 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 77 % 3 == 0:
        base.append("ore")
    if 77 % 5 == 0:
        base.append("crystal")
    return base
