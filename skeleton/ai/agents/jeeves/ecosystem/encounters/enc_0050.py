"""Encounter 0050.
"""
from __future__ import annotations

ENC = "enc_0050"

def composition() -> list[str]:
    n = 1 + (50 % 4)
    return [f"enemy_{50}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
