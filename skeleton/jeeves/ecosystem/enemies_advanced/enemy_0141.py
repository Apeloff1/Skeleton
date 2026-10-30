"""Enemy advanced 0141.
"""
from __future__ import annotations

ID = "enemy_adv_0141"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 141}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
