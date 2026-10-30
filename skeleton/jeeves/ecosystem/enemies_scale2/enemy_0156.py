"""Enemy scale2 0156.
"""
from __future__ import annotations

ID = "enemy_scale2_0156"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 156}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
