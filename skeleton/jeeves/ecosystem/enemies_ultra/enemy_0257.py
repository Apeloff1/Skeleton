"""Enemy ultra 0257.
"""
from __future__ import annotations

ID = "enemy_ultra_0257"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 257, "tier": 257 % 5}

def apply(context: str = "") -> dict:
    if not context and 257 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
