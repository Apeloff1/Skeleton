"""Farm plot 0044.
"""
from __future__ import annotations

PLOT = "plot_0044"

def plant(seed: str) -> dict:
    if not seed:
        return {"ok": False, "reason": "no_seed"}
    return {"ok": True, "plot": PLOT, "seed": seed, "days": 3}

def harvest() -> dict:
    return {"ok": True, "plot": PLOT, "yield": 2}
