"""QK-Normed MLA — RMS on Q/K without materializing full keys.

Cite: arXiv 2606.16310. One inverse-RMS scalar per token.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.mla import mla
from skeleton.kernel.ops.rmsnorm import rmsnorm

Row = List[float]
Slot = Tuple[Row, Row]


def _inv_rms(x: Row) -> float:
    if not x:
        return 1.0
    m = math.sqrt(sum(v * v for v in x) / len(x) + 1e-6)
    return 1.0 / m


def qkmla(q: Row, kv: List[Slot]) -> dict:
    qn = rmsnorm(q)
    scaled: List[Slot] = []
    for k, v in kv:
        s = _inv_rms(k)
        scaled.append(([s * x for x in k], v))
    o = mla(qn, scaled)
    bump(len(o) if isinstance(o, list) else 1)
    return {
        "kind": "qk-mla",
        "h": o if isinstance(o, list) else qn,
        "kv_n": len(kv),
        "full_key": 0,
        "stored_prose": 0,
    }
