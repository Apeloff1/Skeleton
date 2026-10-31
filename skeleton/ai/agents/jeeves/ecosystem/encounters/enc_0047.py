"""Encounter 0047.
"""
from __future__ import annotations

ENC = "enc_0047"

def composition() -> list[str]:
    n = 1 + (47 % 4)
    return [f"enemy_{47}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
