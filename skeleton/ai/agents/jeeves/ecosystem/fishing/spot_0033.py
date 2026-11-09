"""Fishing spot 0033.
"""
from __future__ import annotations

SPOT = "fish_0033"

def cast(skill: float = 0.5) -> dict:
    caught = skill > 0.4
    return {"ok": True, "spot": SPOT, "caught": caught, "item": "fish" if caught else None}
