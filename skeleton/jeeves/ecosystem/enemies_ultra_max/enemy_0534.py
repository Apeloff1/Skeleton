"""Enemy ultra_max 0534.
"""
from __future__ import annotations

ID = "enemy_ultra_max_0534"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 534, "tier": 534 % 5}

def apply(context: str = "") -> dict:
    if not context and 534 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
