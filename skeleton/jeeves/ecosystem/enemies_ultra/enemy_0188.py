"""Enemy ultra 0188.
"""
from __future__ import annotations

ID = "enemy_ultra_0188"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 188, "tier": 188 % 5}

def apply(context: str = "") -> dict:
    if not context and 188 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
