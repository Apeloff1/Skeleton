"""Quest advanced 0087.
"""
from __future__ import annotations

ID = "quest_adv_0087"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 87}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
