"""Crafting recipe 0061.
"""
from __future__ import annotations

RECIPE = "recipe_0061"

def inputs() -> list[str]:
    return [f"mat_a_{61%20}", f"mat_b_{61%15}"]

def craft(have: list[str]) -> dict:
    need = inputs()
    if not all(n in have for n in need):
        return {"ok": False, "reason": "missing", "need": need}
    return {"ok": True, "recipe": RECIPE, "output": f"item_{61}"}
