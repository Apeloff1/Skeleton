"""Enemy eco_peak 0861.
"""
from __future__ import annotations

ID = "enemy_eco_peak_0861"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 861, "tier": 861 % 5}

def apply(context: str = "") -> dict:
    if not context and 861 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
