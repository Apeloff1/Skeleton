"""Enemy supreme 0677.
"""
from __future__ import annotations

ID = "enemy_supreme_0677"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 677, "tier": 677 % 5}

def apply(context: str = "") -> dict:
    if not context and 677 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
