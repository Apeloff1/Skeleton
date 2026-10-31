"""Enemy peak 0338.
"""
from __future__ import annotations

ID = "enemy_peak_0338"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 338, "tier": 338 % 5}

def apply(context: str = "") -> dict:
    if not context and 338 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
