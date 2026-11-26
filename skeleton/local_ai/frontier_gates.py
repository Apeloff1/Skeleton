"""
Enforce Skeleton frontier gates — import CI, stored_prose zero, secret scan, bench regression, occupied-PR review, Godot artifact plane.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

GATES = ["import_ci", "stored_prose_zero", "secret_scan", "bench", "occupied_pr", "godot_plane"]


def process(data: dict) -> dict:
    refused = admit("frontier_gates", data)
    if refused:
        return refused
    gate = data.get("gate")
    if gate is None:
        return stamp("frontier_gates", data, {"gates": GATES})
    if gate not in GATES:
        return {
            "ok": False,
            "error": "unknown gate",
            "card": "frontier_gates",
            "gates": list(GATES),
        }
    return stamp("frontier_gates", data, {"gates": GATES, "gate": gate})
