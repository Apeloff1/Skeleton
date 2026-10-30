"""Enemy mega 0144.
"""
from __future__ import annotations

ID = "enemy_mega_0144"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 144, "tier": 144 % 5}

def apply(context: str = "") -> dict:
    if not context and 144 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
