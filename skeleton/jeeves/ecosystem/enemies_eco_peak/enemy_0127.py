"""Enemy eco_peak 0127.
"""
from __future__ import annotations

ID = "enemy_eco_peak_0127"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 127, "tier": 127 % 5}

def apply(context: str = "") -> dict:
    if not context and 127 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
