"""Light 0031.
"""
from __future__ import annotations

LIGHT = "light_0031"

def intensity(optical: float = 0.9) -> float:
    return round(max(0.0, min(1.0, optical)), 3)

def color() -> str:
    return ["#fff", "#a78bfa", "#fbbf24", "#38bdf8"][31 % 4]
