"""Dish 0038.
"""
from __future__ import annotations

DISH = "dish_0038"

def cook(ingredients: list[str]) -> dict:
    if len(ingredients) < 2:
        return {"ok": False, "reason": "need_more"}
    return {"ok": True, "dish": DISH, "buff": "regen"}
