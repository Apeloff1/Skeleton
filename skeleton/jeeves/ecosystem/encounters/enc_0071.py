"""Encounter 0071.
"""
from __future__ import annotations

ENC = "enc_0071"

def composition() -> list[str]:
    n = 1 + (71 % 4)
    return [f"enemy_{71}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
