"""Enemy scale2 0122.
"""
from __future__ import annotations

ID = "enemy_scale2_0122"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 122}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
