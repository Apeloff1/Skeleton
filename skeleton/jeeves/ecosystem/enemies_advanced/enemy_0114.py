"""Enemy advanced 0114.
"""
from __future__ import annotations

ID = "enemy_adv_0114"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 114}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
