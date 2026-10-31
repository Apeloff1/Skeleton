"""Encounter 0133.
"""
from __future__ import annotations

ENC = "enc_0133"

def composition() -> list[str]:
    n = 1 + (133 % 4)
    return [f"enemy_{133}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
