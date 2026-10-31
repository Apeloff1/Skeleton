"""Enemy ultra 0137.
"""
from __future__ import annotations

ID = "enemy_ultra_0137"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 137, "tier": 137 % 5}

def apply(context: str = "") -> dict:
    if not context and 137 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
