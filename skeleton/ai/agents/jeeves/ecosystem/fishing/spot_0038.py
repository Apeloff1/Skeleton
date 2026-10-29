"""Fishing spot 0038.
"""
from __future__ import annotations

SPOT = "fish_0038"

def cast(skill: float = 0.5) -> dict:
    caught = skill > 0.4
    return {"ok": True, "spot": SPOT, "caught": caught, "item": "fish" if caught else None}
