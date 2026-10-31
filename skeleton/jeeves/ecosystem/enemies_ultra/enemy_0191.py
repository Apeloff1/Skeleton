"""Enemy ultra 0191.
"""
from __future__ import annotations

ID = "enemy_ultra_0191"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 191, "tier": 191 % 5}

def apply(context: str = "") -> dict:
    if not context and 191 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
