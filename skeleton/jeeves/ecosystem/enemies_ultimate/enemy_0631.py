"""Enemy ultimate 0631.
"""
from __future__ import annotations

ID = "enemy_ultimate_0631"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 631, "tier": 631 % 5}

def apply(context: str = "") -> dict:
    if not context and 631 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
