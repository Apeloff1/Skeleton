"""Quest advanced 0108.
"""
from __future__ import annotations

ID = "quest_adv_0108"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 108}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
