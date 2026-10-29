"""Forge 0022.
"""
from __future__ import annotations

FORGE = "forge_0022"

def craft(bar: str) -> dict:
    if not bar:
        return {"ok": False, "reason": "no_bar"}
    return {"ok": True, "forge": FORGE, "output": f"weapon_from_{bar}"}
