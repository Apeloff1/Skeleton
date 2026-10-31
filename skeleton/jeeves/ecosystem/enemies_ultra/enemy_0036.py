"""Enemy ultra 0036.
"""
from __future__ import annotations

ID = "enemy_ultra_0036"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 36, "tier": 36 % 5}

def apply(context: str = "") -> dict:
    if not context and 36 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
