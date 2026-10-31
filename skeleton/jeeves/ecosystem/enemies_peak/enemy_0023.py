"""Enemy peak 0023.
"""
from __future__ import annotations

ID = "enemy_peak_0023"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 23, "tier": 23 % 5}

def apply(context: str = "") -> dict:
    if not context and 23 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
