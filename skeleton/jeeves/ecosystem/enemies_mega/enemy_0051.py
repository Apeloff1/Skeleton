"""Enemy mega 0051.
"""
from __future__ import annotations

ID = "enemy_mega_0051"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 51, "tier": 51 % 5}

def apply(context: str = "") -> dict:
    if not context and 51 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
