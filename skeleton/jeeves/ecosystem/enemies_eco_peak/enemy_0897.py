"""Enemy eco_peak 0897.
"""
from __future__ import annotations

ID = "enemy_eco_peak_0897"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 897, "tier": 897 % 5}

def apply(context: str = "") -> dict:
    if not context and 897 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
