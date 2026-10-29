"""Encounter 0054.
"""
from __future__ import annotations

ENC = "enc_0054"

def composition() -> list[str]:
    n = 1 + (54 % 4)
    return [f"enemy_{54}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
