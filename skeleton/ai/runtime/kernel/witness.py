"""Witness — one card for fence, hold, hot, coverage, last orch."""
from __future__ import annotations

from typing import Any, Dict


def card() -> Dict[str, Any]:
    from skeleton.kernel.bank import boot, get
    from skeleton.kernel.coverage import card as cov
    from skeleton.kernel.hot import rank
    from skeleton.kernel.persist import load

    boot()
    hold = get("hold")
    fence = get("sfence")
    last = load()
    return {
        "kind": "kernel-witness",
        "hold": hold.card() if hold is not None and hasattr(hold, "card") else {},
        "fence": fence.card() if fence is not None and hasattr(fence, "card") else {},
        "hot": rank().get("hot") or [],
        "coverage": cov().get("pct_obl"),
        "last_n": last.get("n") or 0,
        "last_runs": last.get("runs") or 0,
        "gov": __import__("skeleton.kernel.persist", fromlist=["load_gov"]).load_gov(),
        "stored_prose": 0,
    }
