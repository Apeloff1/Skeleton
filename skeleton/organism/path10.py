"""10× path card — gap, rate, MHC clip.

G starts at 1. Target 10. toward = (G-1)/9. Rate is last growth
if the organism recorded it, else 0. No forecast theater.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def path_card(org, *, last_growth: Optional[float] = None) -> Dict[str, Any]:
    g = float(org.G)
    target = float(getattr(org, "TARGET", 10.0) or 10.0)
    gap = max(0.0, target - g)
    toward = float(org.toward)
    steps = max(1, int(org.steps or 0))
    per_step = (g - 1.0) / steps
    return {
        "kind": "path-10x",
        "G": round(g, 6),
        "target": target,
        "gap": round(gap, 6),
        "toward_10x_pct": round(toward, 2),
        "steps": int(org.steps or 0),
        "mean_step": round(per_step, 6),
        "last_growth": round(float(last_growth or 1.0), 6),
        "mix": __import__("skeleton.organism.context_step", fromlist=["mix_card"]).mix_card(getattr(org, "root", None)),
        "observe": __import__("skeleton.organism.observe", fromlist=["card"]).card(getattr(org, "root", None)),
        "stored_prose": 0,
    }
