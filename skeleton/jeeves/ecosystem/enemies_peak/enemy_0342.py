"""Enemy peak 0342.
"""
from __future__ import annotations

ID = "enemy_peak_0342"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 342, "tier": 342 % 5}

def apply(context: str = "") -> dict:
    if not context and 342 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
