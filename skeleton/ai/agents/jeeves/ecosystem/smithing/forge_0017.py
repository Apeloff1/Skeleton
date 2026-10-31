"""Forge 0017.
"""
from __future__ import annotations

FORGE = "forge_0017"

def craft(bar: str) -> dict:
    if not bar:
        return {"ok": False, "reason": "no_bar"}
    return {"ok": True, "forge": FORGE, "output": f"weapon_from_{bar}"}
