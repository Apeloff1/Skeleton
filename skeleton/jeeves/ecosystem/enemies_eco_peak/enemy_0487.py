"""Enemy eco_peak 0487.
"""
from __future__ import annotations

ID = "enemy_eco_peak_0487"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 487, "tier": 487 % 5}

def apply(context: str = "") -> dict:
    if not context and 487 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
