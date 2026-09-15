"""Retain vs consolidate — house operator under live pressure.

Cite https://arxiv.org/abs/2607.17545 as the decision split.
House mapping:
  consolidate → dream + trim (tight budget)
  retain      → pulse/new    (slack budget)
No paper operators (Merge/Abstract/Rewrite) are imported.
"""
from __future__ import annotations

from typing import Any, Dict


CITE = "https://arxiv.org/abs/2607.17545"


def choose(pressure: float, stale_n: int = 0, *, atoms: int = 0, atom_cap: int = 1) -> Dict[str, Any]:
    fill = float(atoms) / max(1, int(atom_cap))
    tight = float(pressure) >= 0.62 or fill >= 0.85 or int(stale_n) >= 4
    op = "consolidate" if tight else "retain"
    return {
        "kind": "budget-op",
        "op": op,
        "pressure": round(float(pressure), 4),
        "fill": round(fill, 4),
        "stale_n": int(stale_n),
        "cite": CITE,
        "stored_prose": 0,
    }


def walk_limit(tier: str, requested: int) -> int:
    cap = {"tiny": 3, "small": 4, "medium": 5, "large": 6, "max": 8}.get(str(tier), 4)
    try:
        from skeleton.kernel.profiles import live_overlay
        extra = live_overlay().get("walk_n")
        if extra:
            cap = min(cap, int(extra))
    except Exception:
        pass
    return max(1, min(cap, int(requested or cap)))
