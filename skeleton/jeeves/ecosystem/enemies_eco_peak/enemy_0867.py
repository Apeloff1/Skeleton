"""Enemy eco_peak 0867.
"""
from __future__ import annotations

ID = "enemy_eco_peak_0867"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 867, "tier": 867 % 5}

def apply(context: str = "") -> dict:
    if not context and 867 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
