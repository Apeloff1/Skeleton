"""Enemy mega 0024.
"""
from __future__ import annotations

ID = "enemy_mega_0024"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 24, "tier": 24 % 5}

def apply(context: str = "") -> dict:
    if not context and 24 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
