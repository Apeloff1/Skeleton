"""Enemy peak 0281.
"""
from __future__ import annotations

ID = "enemy_peak_0281"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 281, "tier": 281 % 5}

def apply(context: str = "") -> dict:
    if not context and 281 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
