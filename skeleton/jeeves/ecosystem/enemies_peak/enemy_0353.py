"""Enemy peak 0353.
"""
from __future__ import annotations

ID = "enemy_peak_0353"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 353, "tier": 353 % 5}

def apply(context: str = "") -> dict:
    if not context and 353 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
