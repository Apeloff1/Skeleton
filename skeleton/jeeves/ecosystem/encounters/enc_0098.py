"""Encounter 0098.
"""
from __future__ import annotations

ENC = "enc_0098"

def composition() -> list[str]:
    n = 1 + (98 % 4)
    return [f"enemy_{98}_{k}" for k in range(n)]

def difficulty(optical: float = 0.9) -> float:
    return round(0.5 + optical * 0.5, 3)
