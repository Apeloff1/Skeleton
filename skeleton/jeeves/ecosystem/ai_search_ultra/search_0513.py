"""AI Search ultra 0513.
"""
from __future__ import annotations

ID = "search_ultra_0513"

def describe() -> dict:
    return {"id": ID, "kind": "search", "advanced": True, "ultra": True}

def process(input_data: dict | None = None) -> dict:
    data = input_data or {}
    score = 0.55 + (513 % 30) * 0.01
    return {"ok": True, "id": ID, "score": round(score, 3), "processed": len(data)}

def refine(iteration: int = 1) -> dict:
    if iteration < 1:
        return {"ok": False, "reason": "bad_iteration"}
    return {"ok": True, "id": ID, "iteration": iteration, "improved": True}
