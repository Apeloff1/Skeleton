"""Enemy eco_peak 0027.
"""
from __future__ import annotations

ID = "enemy_eco_peak_0027"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 27, "tier": 27 % 5}

def apply(context: str = "") -> dict:
    if not context and 27 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
