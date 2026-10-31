"""Encounter 0094.
"""
from __future__ import annotations

ENC = "enc_0094"

def composition() -> list[str]:
    n = 1 + (94 % 4)
    return [f"enemy_{94}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
