"""Enemy ultra 0115.
"""
from __future__ import annotations

ID = "enemy_ultra_0115"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 115, "tier": 115 % 5}

def apply(context: str = "") -> dict:
    if not context and 115 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
