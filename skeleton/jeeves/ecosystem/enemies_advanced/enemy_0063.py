"""Enemy advanced 0063.
"""
from __future__ import annotations

ID = "enemy_adv_0063"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 63}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
