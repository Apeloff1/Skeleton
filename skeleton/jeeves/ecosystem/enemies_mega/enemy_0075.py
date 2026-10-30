"""Enemy mega 0075.
"""
from __future__ import annotations

ID = "enemy_mega_0075"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 75, "tier": 75 % 5}

def apply(context: str = "") -> dict:
    if not context and 75 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
