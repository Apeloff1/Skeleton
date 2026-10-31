"""Enemy peak 0346.
"""
from __future__ import annotations

ID = "enemy_peak_0346"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 346, "tier": 346 % 5}

def apply(context: str = "") -> dict:
    if not context and 346 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
