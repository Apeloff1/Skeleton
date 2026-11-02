"""Enemy eco_peak 0789.
"""
from __future__ import annotations

ID = "enemy_eco_peak_0789"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 789, "tier": 789 % 5}

def apply(context: str = "") -> dict:
    if not context and 789 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
