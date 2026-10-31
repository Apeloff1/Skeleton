"""Encounter 0105.
"""
from __future__ import annotations

ENC = "enc_0105"

def composition() -> list[str]:
    n = 1 + (105 % 4)
    return [f"enemy_{105}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
