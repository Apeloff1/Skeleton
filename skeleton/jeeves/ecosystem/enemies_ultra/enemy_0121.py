"""Enemy ultra 0121.
"""
from __future__ import annotations

ID = "enemy_ultra_0121"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 121, "tier": 121 % 5}

def apply(context: str = "") -> dict:
    if not context and 121 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
