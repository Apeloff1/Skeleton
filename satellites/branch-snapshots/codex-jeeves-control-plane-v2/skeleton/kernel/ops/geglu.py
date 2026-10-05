"""GeGLU / ReGLU — gated extra activations. Superfluous next to SwiGLU."""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.act import gelu, relu

Row = List[float]


def geglu(x: Row, gate: Row) -> Row:
    g = gelu(gate)
    out = [a * b for a, b in zip(x, g)]
    bump(len(out))
    return out


def reglue(x: Row, gate: Row) -> Row:
    g = relu(gate)
    out = [a * b for a, b in zip(x, g)]
    bump(len(out))
    return out


def sqrelu(xs: Row) -> Row:
    out = [(v * v) if v > 0 else 0.0 for v in xs]
    bump(len(out))
    return out


def silu(xs: Row) -> Row:
    out = [v / (1.0 + math.exp(-v)) if abs(v) < 20 else (v if v > 0 else 0.0) for v in xs]
    bump(len(out))
    return out
