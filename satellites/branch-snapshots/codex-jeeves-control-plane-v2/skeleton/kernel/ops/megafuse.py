"""Mega-kernel epilogue — matmul + act + residual, one write.

Cite: MPK mega-kernel / cuBLASLt epilogue. Working row only.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.act import gelu
from skeleton.kernel.ops.matmul import matmul

Row = List[float]


def epilogue(x: Row, w: List[Row], residual: Row | None = None) -> Row:
    if w and len(w[0]) == len(x):
        y = matmul(w, [[xi] for xi in x])
        y = [row[0] if row else 0.0 for row in y]
    else:
        y = list(x)
    y = gelu(y)
    if residual is not None and len(residual) == len(y):
        y = [a + b for a, b in zip(y, residual)]
    bump(len(y))
    return y
