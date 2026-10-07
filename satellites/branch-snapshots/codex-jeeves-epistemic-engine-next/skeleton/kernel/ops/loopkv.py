"""Per-loop KV policy.

share  — Huginn: write once
fresh  — rewrite every pass (expensive)
hybrid — write on pass 1 and last only
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend
from skeleton.kernel.ops.rmsnorm import rmsnorm

Row = List[float]
Slot = Tuple[Row, Row]


def policy(mode: str, r: int) -> List[str]:
    r = max(1, int(r))
    m = str(mode or "share")
    if m == "fresh":
        return ["write"] * r
    if m == "hybrid":
        return ["write"] + ["read"] * max(0, r - 2) + (["write"] if r > 1 else [])
    return ["write"] + ["read"] * (r - 1)


def run(x: Row, *, r: int = 2, mode: str = "share") -> dict:
    plan = policy(mode, r)
    h = rmsnorm(x)
    kv: List[Slot] = [(h, h)]
    writes = 0
    for act in plan:
        h = rmsnorm(h)
        if act == "write":
            kv = [(h, h)]
            writes += 1
        h = attend(h, kv)
    bump(len(h))
    return {
        "kind": "loop-kv",
        "mode": mode,
        "plan": plan,
        "writes": writes,
        "h": h,
        "stored_prose": 0,
    }
