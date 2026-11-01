"""Character ultimate 0821.
"""
from __future__ import annotations

ID = "character_ultimate_0821"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 821, "tier": 821 % 5}

def apply(context: str = "") -> dict:
    if not context and 821 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
