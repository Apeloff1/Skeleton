"""Enemy eco_peak 0827.
"""
from __future__ import annotations

ID = "enemy_eco_peak_0827"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 827, "tier": 827 % 5}

def apply(context: str = "") -> dict:
    if not context and 827 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
