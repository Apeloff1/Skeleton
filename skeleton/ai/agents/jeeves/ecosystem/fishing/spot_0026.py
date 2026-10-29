"""Fishing spot 0026.
"""
from __future__ import annotations

SPOT = "fish_0026"

def cast(skill: float = 0.5) -> dict:
    caught = skill > 0.4
    return {"ok": True, "spot": SPOT, "caught": caught, "item": "fish" if caught else None}
