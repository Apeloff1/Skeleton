"""Encounter 0012.
"""
from __future__ import annotations

ENC = "enc_0012"

def composition() -> list[str]:
    n = 1 + (12 % 4)
    return [f"enemy_{12}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
