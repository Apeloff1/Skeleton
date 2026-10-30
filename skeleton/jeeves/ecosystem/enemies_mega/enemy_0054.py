"""Enemy mega 0054.
"""
from __future__ import annotations

ID = "enemy_mega_0054"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 54, "tier": 54 % 5}

def apply(context: str = "") -> dict:
    if not context and 54 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
