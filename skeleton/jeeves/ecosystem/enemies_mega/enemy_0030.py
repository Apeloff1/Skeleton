"""Enemy mega 0030.
"""
from __future__ import annotations

ID = "enemy_mega_0030"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 30, "tier": 30 % 5}

def apply(context: str = "") -> dict:
    if not context and 30 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
