"""Crafting recipe 0010.
"""
from __future__ import annotations

RECIPE = "recipe_0010"

def inputs() -> list[str]:
    return [f"mat_a_{10%20}", f"mat_b_{10%15}"]

def craft(have: list[str]) -> dict:
    need = inputs()
    if not all(n in have for n in need):
        return {"ok": False, "reason": "missing", "need": need}
    return {"ok": True, "recipe": RECIPE, "output": f"item_{10}"}
