"""Enemy advanced 0103.
"""
from __future__ import annotations

ID = "enemy_adv_0103"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 103}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
