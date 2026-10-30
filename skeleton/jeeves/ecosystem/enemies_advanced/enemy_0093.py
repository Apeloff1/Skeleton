"""Enemy advanced 0093.
"""
from __future__ import annotations

ID = "enemy_adv_0093"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 93}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
