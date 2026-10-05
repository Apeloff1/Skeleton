"""Adaptive quantization noise — QeRL-style channel noise that decays.

Cite: arXiv 2510.11696. Merges into RMS scale. Zero extra params.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.rmsnorm import rmsnorm

Row = List[float]


def aqnoise(x: Row, *, step: int = 0, amp: float = 0.05) -> dict:
    h = rmsnorm(x)
    decay = 1.0 / (1 + max(0, int(step)))
    a = max(0.0, float(amp)) * decay
    y = [v + a * (1.0 if i % 2 == 0 else -1.0) for i, v in enumerate(h)]
    bump(len(y))
    return {
        "kind": "aq-noise",
        "step": max(0, int(step)),
        "amp": a,
        "h": y,
        "params": 0,
        "stored_prose": 0,
    }
