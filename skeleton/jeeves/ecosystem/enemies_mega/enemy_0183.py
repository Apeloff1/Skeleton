"""Enemy mega 0183.
"""
from __future__ import annotations

ID = "enemy_mega_0183"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 183, "tier": 183 % 5}

def apply(context: str = "") -> dict:
    if not context and 183 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
