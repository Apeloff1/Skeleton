"""Enemy advanced 0001.
"""
from __future__ import annotations

ID = "enemy_adv_0001"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
