"""Enemy ultimate 0714.
"""
from __future__ import annotations

ID = "enemy_ultimate_0714"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 714, "tier": 714 % 5}

def apply(context: str = "") -> dict:
    if not context and 714 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
