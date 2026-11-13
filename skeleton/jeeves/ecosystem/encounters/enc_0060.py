"""Encounter 0060.
"""
from __future__ import annotations

ENC = "enc_0060"

def composition() -> list[str]:
    n = 1 + (60 % 4)
    return [f"enemy_{60}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
