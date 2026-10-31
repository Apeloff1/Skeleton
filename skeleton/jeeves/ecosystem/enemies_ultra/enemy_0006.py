"""Enemy ultra 0006.
"""
from __future__ import annotations

ID = "enemy_ultra_0006"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 6, "tier": 6 % 5}

def apply(context: str = "") -> dict:
    if not context and 6 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
