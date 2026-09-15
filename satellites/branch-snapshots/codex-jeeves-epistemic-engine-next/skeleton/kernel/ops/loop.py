"""Looped transformer unroll — reuse one residual block R times.

Cite: Nanbeige 4.2 / recurrent depth. Params stay. Compute scales with R.
House path: working row only. Default R=2 (field: more than two often regresses).
"""
from __future__ import annotations

from typing import Callable, List, Optional

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend
from skeleton.kernel.ops.residual import residual
from skeleton.kernel.ops.rmsnorm import rmsnorm

Row = List[float]


def block(x: Row, kv: List[tuple] | None = None) -> Row:
    h = rmsnorm(x)
    o = attend(h, kv or [(h, h)])
    y = residual(x, o)
    bump(len(y))
    return y


def unroll(x: Row, *, r: int = 2, kv: List[tuple] | None = None,
           step: Optional[Callable[[Row], Row]] = None) -> dict:
    r = max(1, min(8, int(r)))
    h = list(x)
    fn = step or (lambda z: block(z, kv))
    for i in range(r):
        h = fn(h)
    bump(len(h))
    return {
        "kind": "loop-unroll",
        "r": r,
        "d": len(h),
        "h": h,
        "effective_depth": r,
        "stored_prose": 0,
    }
