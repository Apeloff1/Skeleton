"""Enemy ultra 0243.
"""
from __future__ import annotations

ID = "enemy_ultra_0243"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 243, "tier": 243 % 5}

def apply(context: str = "") -> dict:
    if not context and 243 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
