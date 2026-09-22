"""Activations. GELU / ReLU / tanh. Infer path, no dropout."""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump


def relu(xs: List[float]) -> List[float]:
    out = [v if v > 0 else 0.0 for v in xs]
    bump(len(out))
    return out


def tanh_act(xs: List[float]) -> List[float]:
    out = [math.tanh(v) for v in xs]
    bump(len(out))
    return out


def gelu(xs: List[float]) -> List[float]:
    # tanh approximation
    out = []
    for v in xs:
        t = math.tanh(math.sqrt(2 / math.pi) * (v + 0.044715 * v * v * v))
        out.append(0.5 * v * (1.0 + t))
    bump(len(out))
    return out
