"""YaRN / NTK / xPos — obscure RoPE stretch family.

Scale the base, not the body. No position table write.
"""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.rope import rope

Row = List[float]


def yarn(x: Row, pos: int, *, scale: float = 4.0, base: float = 10000.0) -> Row:
    s = max(1.0, float(scale))
    stretched = int(pos / s)
    out = rope(x, stretched)
    bump(len(out))
    return out


def ntk(x: Row, pos: int, *, alpha: float = 2.0) -> Row:
    a = max(1.0, float(alpha))
    return yarn(x, pos, scale=a)


def xpos(x: Row, pos: int, *, gamma: float = 0.4) -> Row:
    rot = rope(x, pos)
    g = max(0.0, min(1.0, float(gamma)))
    decay = math.exp(-g * abs(int(pos)))
    out = [v * decay for v in rot]
    bump(len(out))
    return out
