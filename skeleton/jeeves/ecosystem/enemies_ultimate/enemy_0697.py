"""Enemy ultimate 0697.
"""
from __future__ import annotations

ID = "enemy_ultimate_0697"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 697, "tier": 697 % 5}

def apply(context: str = "") -> dict:
    if not context and 697 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
