"""Enemy mega 0065.
"""
from __future__ import annotations

ID = "enemy_mega_0065"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 65, "tier": 65 % 5}

def apply(context: str = "") -> dict:
    if not context and 65 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
