"""Quest advanced 0007.
"""
from __future__ import annotations

ID = "quest_adv_0007"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 7}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
