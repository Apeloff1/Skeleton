"""Enemy ultra 0171.
"""
from __future__ import annotations

ID = "enemy_ultra_0171"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 171, "tier": 171 % 5}

def apply(context: str = "") -> dict:
    if not context and 171 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
