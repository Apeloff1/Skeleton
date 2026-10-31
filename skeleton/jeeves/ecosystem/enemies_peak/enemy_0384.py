"""Enemy peak 0384.
"""
from __future__ import annotations

ID = "enemy_peak_0384"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 384, "tier": 384 % 5}

def apply(context: str = "") -> dict:
    if not context and 384 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
