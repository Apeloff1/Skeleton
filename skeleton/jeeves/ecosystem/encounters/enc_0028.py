"""Encounter 0028.
"""
from __future__ import annotations

ENC = "enc_0028"

def composition() -> list[str]:
    n = 1 + (28 % 4)
    return [f"enemy_{28}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
