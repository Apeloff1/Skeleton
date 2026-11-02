"""Enemy eco_peak 0742.
"""
from __future__ import annotations

ID = "enemy_eco_peak_0742"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 742, "tier": 742 % 5}

def apply(context: str = "") -> dict:
    if not context and 742 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
