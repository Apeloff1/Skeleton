"""Learning 0018.
"""
from __future__ import annotations

LEARN = "learn_0018"

def update(weight: float, error: float, rate: float = 0.01) -> dict:
    new = weight - rate * error
    return {"ok": True, "learn": LEARN, "weight": round(new, 4)}
