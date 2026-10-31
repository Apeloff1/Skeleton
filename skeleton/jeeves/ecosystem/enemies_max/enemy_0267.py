"""Enemy max 0267.
"""
from __future__ import annotations

ID = "enemy_max_0267"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 267, "tier": 267 % 5}

def apply(context: str = "") -> dict:
    if not context and 267 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
