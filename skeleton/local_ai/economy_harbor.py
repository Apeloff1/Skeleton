"""
Catalog economy as cards only. Bag, harbor, lineage weights. Weight sum equals 1.
Bag ops reversible. No currency network.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

WEIGHTS = {"bag": 0.4, "harbor": 0.3, "lineage": 0.3}


def sum_weights() -> float:
    return sum(WEIGHTS.values())


def process(data: dict) -> dict:
    refused = admit("economy_harbor", data)
    if refused:
        return refused
    total = sum_weights()
    if abs(total - 1.0) > 1e-9:
        return {"ok": False, "error": "weights do not sum to 1", "card": "economy_harbor"}
    if "weights" in data:
        return {
            "ok": False,
            "error": "weights are fixed",
            "card": "economy_harbor",
            "weights": dict(WEIGHTS),
        }
    return stamp("economy_harbor", data, {"weights": WEIGHTS, "sum": total})
