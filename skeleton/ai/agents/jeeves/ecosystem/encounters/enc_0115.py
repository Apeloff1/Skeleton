"""Encounter 0115.
"""
from __future__ import annotations

ENC = "enc_0115"

def composition() -> list[str]:
    n = 1 + (115 % 4)
    return [f"enemy_{115}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
