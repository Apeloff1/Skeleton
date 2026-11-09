"""Dish 0010.
"""
from __future__ import annotations

DISH = "dish_0010"

def cook(ingredients: list[str]) -> dict:
    if len(ingredients) < 2:
        return {"ok": False, "reason": "need_more"}
    return {"ok": True, "dish": DISH, "buff": "regen"}
