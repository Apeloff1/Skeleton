"""AI Search 0591.
"""
from __future__ import annotations

ID = "search_adv_0591"

def describe() -> dict:
    return {"id": ID, "kind": "search", "advanced": True}

def process(input_data: dict | None = None) -> dict:
    data = input_data or {}
    score = 0.5 + (591 % 30) * 0.01
    return {"ok": True, "id": ID, "score": round(score, 3), "processed": len(data)}

def refine(iteration: int = 1) -> dict:
    if iteration < 1:
        return {"ok": False, "reason": "bad_iteration"}
    return {"ok": True, "id": ID, "iteration": iteration, "improved": True}
