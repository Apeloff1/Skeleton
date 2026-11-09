"""Encounter 0103.
"""
from __future__ import annotations

ENC = "enc_0103"

def composition() -> list[str]:
    n = 1 + (103 % 4)
    return [f"enemy_{103}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
