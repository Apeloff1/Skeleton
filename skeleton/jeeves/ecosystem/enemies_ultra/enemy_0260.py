"""Enemy ultra 0260.
"""
from __future__ import annotations

ID = "enemy_ultra_0260"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 260, "tier": 260 % 5}

def apply(context: str = "") -> dict:
    if not context and 260 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
