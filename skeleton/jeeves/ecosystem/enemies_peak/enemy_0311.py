"""Enemy peak 0311.
"""
from __future__ import annotations

ID = "enemy_peak_0311"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 311, "tier": 311 % 5}

def apply(context: str = "") -> dict:
    if not context and 311 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
