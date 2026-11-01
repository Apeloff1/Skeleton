"""Enemy ultimate 0609.
"""
from __future__ import annotations

ID = "enemy_ultimate_0609"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 609, "tier": 609 % 5}

def apply(context: str = "") -> dict:
    if not context and 609 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
