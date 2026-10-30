"""Enemy advanced 0140.
"""
from __future__ import annotations

ID = "enemy_adv_0140"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 140}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
