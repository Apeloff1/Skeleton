"""Weather: clear.
"""
from __future__ import annotations

NAME = "clear"

def intensity(optical: float = 0.9) -> float:
    return round(max(0.0, min(1.0, optical * 0.8)), 3)

def modifiers() -> dict:
    return {"visibility": 0.9 if NAME == "clear" else 0.6, "move_scale": 1.0 if NAME in ("clear", "fog") else 0.85}
