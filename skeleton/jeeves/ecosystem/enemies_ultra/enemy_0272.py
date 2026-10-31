"""Enemy ultra 0272.
"""
from __future__ import annotations

ID = "enemy_ultra_0272"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 272, "tier": 272 % 5}

def apply(context: str = "") -> dict:
    if not context and 272 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
