"""Enemy mega 0049.
"""
from __future__ import annotations

ID = "enemy_mega_0049"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 49, "tier": 49 % 5}

def apply(context: str = "") -> dict:
    if not context and 49 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
