"""Enemy mega 0206.
"""
from __future__ import annotations

ID = "enemy_mega_0206"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 206, "tier": 206 % 5}

def apply(context: str = "") -> dict:
    if not context and 206 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
