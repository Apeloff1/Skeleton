"""Character peak 0443.
"""
from __future__ import annotations

ID = "character_peak_0443"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 443, "tier": 443 % 5}

def apply(context: str = "") -> dict:
    if not context and 443 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
