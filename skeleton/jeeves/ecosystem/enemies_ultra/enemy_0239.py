"""Enemy ultra 0239.
"""
from __future__ import annotations

ID = "enemy_ultra_0239"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 239, "tier": 239 % 5}

def apply(context: str = "") -> dict:
    if not context and 239 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
