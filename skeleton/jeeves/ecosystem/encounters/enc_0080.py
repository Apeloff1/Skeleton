"""Encounter 0080.
"""
from __future__ import annotations

ENC = "enc_0080"

def composition() -> list[str]:
    n = 1 + (80 % 4)
    return [f"enemy_{80}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
