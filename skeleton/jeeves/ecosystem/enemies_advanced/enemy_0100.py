"""Enemy advanced 0100.
"""
from __future__ import annotations

ID = "enemy_adv_0100"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 100}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
