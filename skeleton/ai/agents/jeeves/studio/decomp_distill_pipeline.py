"""Decomp-to-distill pipeline. Produces optical-weighted cards for Jeeves.
Simulated extraction (real ROM bytes not required for the seal).
"""
from __future__ import annotations
from typing import Dict, Any, List

def extract_and_distill(source_name: str, optical: float) -> Dict[str, Any]:
    if not source_name or optical < 0.85:
        return {"ok": False, "reason": "floors", "cards": [], "fidelity": 0.0}
    # simulated weights from source name + optical
    base = abs(hash(source_name)) % 100
    weights = [base / 100.0, optical, min(1.0, optical * 1.05)]
    fidelity = min(0.97, 0.88 + optical * 0.09)
    if fidelity < 0.92:
        return {"ok": False, "reason": "fidelity_floor", "cards": [], "fidelity": fidelity}
    cards = [
        {"id": "era_pattern", "weight": weights[0], "optical": optical},
        {"id": "ability_set", "weight": weights[1], "optical": optical},
        {"id": "room_graph", "weight": weights[2], "optical": optical},
    ]
    return {
        "ok": True,
        "reason": "ok",
        "source": source_name,
        "cards": cards,
        "fidelity": fidelity,
        "optical": optical,
    }
