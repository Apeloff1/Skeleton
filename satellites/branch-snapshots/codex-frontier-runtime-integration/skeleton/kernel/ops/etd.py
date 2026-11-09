"""Encode–Think–Decode — recursive latent thoughts.

Cite: ETD arXiv 2510.07358. Encoder once, think-block k times, decode once.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def etd(x: Row, *, enc: int = 2, think: int = 2, dec: int = 2, k: int = 2) -> dict:
    y = list(x)
    for _ in range(max(1, enc)):
        y = block(y)
    for _ in range(max(1, k)):
        for _ in range(max(1, think)):
            y = block(y)
    for _ in range(max(1, dec)):
        y = block(y)
    bump(len(y))
    return {
        "kind": "etd",
        "shape": f"{enc}-{think}*{k}-{dec}",
        "effective": enc + think * k + dec,
        "h": y,
        "stored_prose": 0,
    }
