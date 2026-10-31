"""Enemy ultra 0265.
"""
from __future__ import annotations

ID = "enemy_ultra_0265"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 265, "tier": 265 % 5}

def apply(context: str = "") -> dict:
    if not context and 265 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
