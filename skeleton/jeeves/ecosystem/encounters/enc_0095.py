"""Encounter 0095.
"""
from __future__ import annotations

ENC = "enc_0095"

def composition() -> list[str]:
    n = 1 + (95 % 4)
    return [f"enemy_{95}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
