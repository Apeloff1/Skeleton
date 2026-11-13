"""Encounter 0008.
"""
from __future__ import annotations

ENC = "enc_0008"

def composition() -> list[str]:
    n = 1 + (8 % 4)
    return [f"enemy_{8}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
