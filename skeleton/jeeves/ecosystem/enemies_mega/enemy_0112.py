"""Enemy mega 0112.
"""
from __future__ import annotations

ID = "enemy_mega_0112"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 112, "tier": 112 % 5}

def apply(context: str = "") -> dict:
    if not context and 112 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
