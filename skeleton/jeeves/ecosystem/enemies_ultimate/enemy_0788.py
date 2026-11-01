"""Enemy ultimate 0788.
"""
from __future__ import annotations

ID = "enemy_ultimate_0788"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 788, "tier": 788 % 5}

def apply(context: str = "") -> dict:
    if not context and 788 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
